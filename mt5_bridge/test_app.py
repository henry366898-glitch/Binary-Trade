"""
MT5 Bridge — Test / Diagnostic FastAPI App
==========================================
Runs alongside bridge.py on the Windows machine.
Connects to the bridge WebSocket, caches live ticks,
and exposes them via REST + a live browser monitor.

Start:  python test_app.py
        — or via PM2: see ecosystem.config.js

Endpoints:
  GET  /           → HTML live tick monitor (open in browser)
  GET  /health     → JSON health check + connected symbols
  GET  /ticks      → JSON snapshot of every symbol's latest tick
  GET  /tick/{sym} → JSON for one symbol  (e.g. /tick/EURUSD)
  WS   /ws         → WebSocket — streams ticks to the browser page
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
# Connect to the bridge on loopback (even though bridge listens on 0.0.0.0)
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "9000"))
TEST_PORT   = int(os.getenv("TEST_PORT",   "9001"))

# ── State ─────────────────────────────────────────────────────────────────────
# symbol → latest tick dict (kept in memory, updated by bridge_reader)
latest_ticks: dict[str, dict] = {}
# browser WebSocket clients subscribed to live ticks
browser_clients: set[WebSocket] = set()
# track bridge connection state for /health
_bridge_connected = False
_bridge_error: str | None = None


# ── Background task: connect to bridge and relay ticks ────────────────────────
async def bridge_reader():
    global _bridge_connected, _bridge_error
    uri = f"ws://{BRIDGE_HOST}:{BRIDGE_PORT}"
    backoff = 1

    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                _bridge_connected = True
                _bridge_error = None
                backoff = 1  # reset on successful connect
                print(f"[test_app] ✓ Connected to bridge at {uri}", flush=True)

                async for raw in ws:
                    try:
                        tick = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    if tick.get("type") == "tick":
                        latest_ticks[tick["symbol"]] = tick

                        # broadcast to all browser WS clients
                        dead: set[WebSocket] = set()
                        for client in list(browser_clients):
                            try:
                                await client.send_text(raw)
                            except Exception:
                                dead.add(client)
                        browser_clients.difference_update(dead)

        except Exception as exc:
            _bridge_connected = False
            _bridge_error = str(exc)
            wait = min(backoff, 30)
            print(f"[test_app] ✗ Bridge error: {exc} — retry in {wait}s", flush=True)
            await asyncio.sleep(wait)
            backoff = min(backoff * 2, 30)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(bridge_reader())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MT5 Bridge Test",
    description="Diagnostic UI and REST snapshot for the MT5 WebSocket bridge.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── REST endpoints ────────────────────────────────────────────────────────────
@app.get("/health", tags=["diagnostic"])
def health():
    return {
        "status": "ok",
        "bridge_connected": _bridge_connected,
        "bridge_url": f"ws://{BRIDGE_HOST}:{BRIDGE_PORT}",
        "bridge_error": _bridge_error,
        "symbols_live": sorted(latest_ticks.keys()),
        "tick_count": len(latest_ticks),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ticks", tags=["diagnostic"])
def all_ticks():
    """Latest tick snapshot for every symbol the bridge is sending."""
    return latest_ticks


@app.get("/tick/{symbol}", tags=["diagnostic"])
def tick_for_symbol(symbol: str):
    """Latest tick for one symbol (case-insensitive)."""
    sym = symbol.upper()
    if sym not in latest_ticks:
        return {"error": f"No tick received yet for {sym}", "available": sorted(latest_ticks.keys())}
    return latest_ticks[sym]


# ── Browser WebSocket relay ────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    browser_clients.add(ws)

    # push the current snapshot so the page populates immediately on connect
    for tick in list(latest_ticks.values()):
        try:
            await ws.send_text(json.dumps(tick))
        except Exception:
            break

    try:
        while True:
            await ws.receive_text()   # keep connection alive; we only push, not pull
    except WebSocketDisconnect:
        pass
    finally:
        browser_clients.discard(ws)


# ── Inline HTML monitor ───────────────────────────────────────────────────────
_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MT5 Bridge Monitor</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body   { font-family: 'Consolas', 'Courier New', monospace;
           background: #0d1117; color: #e6edf3;
           padding: 24px 20px; min-height: 100vh; }
  h1     { font-size: 15px; letter-spacing: .12em; color: #58a6ff;
           text-transform: uppercase; margin-bottom: 6px; }
  .sub   { font-size: 11px; color: #8b949e; margin-bottom: 20px; }
  #status{ display: inline-flex; align-items: center; gap: 6px;
           font-size: 12px; margin-bottom: 20px; }
  .dot   { width: 8px; height: 8px; border-radius: 50%; background: #f85149; }
  .dot.ok{ background: #3fb950; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  table  { border-collapse: collapse; width: 100%; max-width: 780px; }
  th     { text-align: left; padding: 7px 14px;
           border-bottom: 1px solid #21262d;
           font-size: 10px; text-transform: uppercase; letter-spacing: .08em;
           color: #8b949e; font-weight: 400; }
  td     { padding: 9px 14px; border-bottom: 1px solid #161b22;
           font-size: 13px; }
  tr.flash td { background: #162032; }
  tr     { transition: background .35s; }
  .sym   { color: #58a6ff; font-weight: 700; letter-spacing: .05em; }
  .bid   { color: #3fb950; }
  .ask   { color: #f85149; }
  .spr   { color: #8b949e; }
  .ts    { color: #6e7681; font-size: 11px; }
  .empty { padding: 32px 14px; color: #8b949e; font-size: 12px; }
  .api-links { margin-top: 28px; font-size: 11px; color: #8b949e; }
  .api-links a { color: #58a6ff; text-decoration: none; margin-right: 16px; }
  .api-links a:hover { text-decoration: underline; }
</style>
</head>
<body>
<h1>⚡ MT5 Bridge — Live Tick Monitor</h1>
<p class="sub">Connects to bridge WebSocket · refreshes on every tick · no page reload needed</p>

<div id="status">
  <span class="dot" id="dot"></span>
  <span id="status-text">Connecting…</span>
</div>

<table>
  <thead>
    <tr>
      <th>Symbol</th>
      <th>Bid</th>
      <th>Ask</th>
      <th>Spread (pts)</th>
      <th>Last tick (local)</th>
    </tr>
  </thead>
  <tbody id="tbody">
    <tr><td class="empty" colspan="5">Waiting for first tick…</td></tr>
  </tbody>
</table>

<div class="api-links">
  REST:
  <a href="/health">/health</a>
  <a href="/ticks">/ticks</a>
  <a href="/docs">/docs</a>
</div>

<script>
(function () {
  const tbody  = document.getElementById('tbody');
  const dot    = document.getElementById('dot');
  const statusTxt = document.getElementById('status-text');
  const rows   = {};   // symbol → <tr>
  let firstTick = false;

  function digits(sym) {
    if (sym.includes('JPY'))                     return 3;
    if (/^(BTC|ETH|XAU)/.test(sym))             return 2;
    return 5;
  }

  function spreadPts(sym, bid, ask) {
    const d = digits(sym);
    const mult = d === 3 ? 1000 : d === 2 ? 10 : 100000;
    return ((ask - bid) * mult).toFixed(1);
  }

  function onTick(t) {
    if (t.type !== 'tick') return;
    if (!firstTick) {
      tbody.innerHTML = '';   // remove "waiting" row
      firstTick = true;
    }
    const sym = t.symbol;
    const d   = digits(sym);
    const ts  = new Date(t.time * 1000).toLocaleTimeString();

    if (!rows[sym]) {
      const tr = document.createElement('tr');
      tr.innerHTML =
        `<td class="sym">${sym}</td>` +
        `<td class="bid"></td>` +
        `<td class="ask"></td>` +
        `<td class="spr"></td>` +
        `<td class="ts"></td>`;
      tbody.appendChild(tr);
      rows[sym] = tr;
    }

    const tr = rows[sym];
    tr.cells[1].textContent = t.bid.toFixed(d);
    tr.cells[2].textContent = t.ask.toFixed(d);
    tr.cells[3].textContent = spreadPts(sym, t.bid, t.ask);
    tr.cells[4].textContent = ts;

    tr.classList.add('flash');
    setTimeout(() => tr.classList.remove('flash'), 380);
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      dot.classList.add('ok');
      statusTxt.textContent = 'Connected to bridge';
    };
    ws.onclose = () => {
      dot.classList.remove('ok');
      statusTxt.textContent = 'Disconnected — reconnecting in 3s…';
      setTimeout(connect, 3000);
    };
    ws.onerror = () => {
      statusTxt.textContent = 'WebSocket error';
    };
    ws.onmessage = (e) => {
      try { onTick(JSON.parse(e.data)); } catch {}
    };
  }

  connect();
})();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    return _HTML


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[test_app] Starting on http://0.0.0.0:{TEST_PORT}", flush=True)
    print(f"[test_app] Will connect to bridge at ws://{BRIDGE_HOST}:{BRIDGE_PORT}", flush=True)
    uvicorn.run("test_app:app", host="0.0.0.0", port=TEST_PORT, reload=False)
