import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '../lib/store';
import { openAcademyCta } from '../lib/leadCta';

const STREAK_THRESHOLD = 5;

/* ── Circular countdown timer ─────────────────────────────────────────────── */
function CircularCountdown({ expiresAt, totalSeconds }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, []);

  const msLeft  = Math.max(0, new Date(expiresAt + 'Z').getTime() - now);
  const sLeft   = Math.ceil(msLeft / 1000);
  const frac    = msLeft / (totalSeconds * 1000); // 1 → 0
  const urgent  = frac < 0.25 && msLeft > 0;

  const R     = 38;
  const circ  = 2 * Math.PI * R;
  const dash  = Math.max(0, frac) * circ;

  return (
    <div className="circular-timer">
      <svg viewBox="0 0 100 100" className="circular-timer-svg">
        {/* background track */}
        <circle cx="50" cy="50" r={R} className="timer-track" />
        {/* animated arc */}
        <circle
          cx="50" cy="50" r={R}
          className="timer-arc"
          style={{
            strokeDasharray: `${dash} ${circ}`,
            stroke: urgent ? 'var(--down)' : 'var(--accent)',
          }}
        />
      </svg>
      <div className="circular-timer-label">
        {msLeft <= 0 ? (
          <span className="timer-settling">settling</span>
        ) : (
          <>
            <span className={`timer-secs ${urgent ? 'urgent' : ''}`}>{sLeft}</span>
            <span className="timer-unit">sec</span>
          </>
        )}
      </div>
    </div>
  );
}

/* ── Active trade card ────────────────────────────────────────────────────── */
function ActiveTradeCard({ trade, currentPrice, digits }) {
  const totalSeconds = Math.max(
    1,
    Math.round(
      (new Date(trade.expires_at + 'Z') - new Date(trade.opened_at + 'Z')) / 1000
    )
  );

  const mid     = currentPrice;
  let winning   = null;
  let priceDiff = 0;

  if (mid != null) {
    const movedUp = mid > trade.entry_price;
    winning   = (trade.direction === 'up' && movedUp) || (trade.direction === 'down' && !movedUp);
    priceDiff = mid - trade.entry_price;
  }

  const sign = priceDiff >= 0 ? '+' : '';

  return (
    <div className={`active-trade-card ${trade.direction}`}>
      {/* header row: direction + stake */}
      <div className="atc-header">
        <span className={`atc-direction ${trade.direction}`}>
          {trade.direction === 'up' ? '▲ UP' : '▼ DOWN'}
        </span>
        <span className="atc-amount">${Number(trade.amount).toFixed(2)}</span>
      </div>

      {/* circular timer */}
      <CircularCountdown expiresAt={trade.expires_at} totalSeconds={totalSeconds} />

      {/* price comparison */}
      <div className="atc-prices">
        <div className="atc-price-row">
          <span className="atc-label">Entry</span>
          <span className="atc-val">{trade.entry_price.toFixed(digits)}</span>
        </div>
        {mid != null && (
          <div className="atc-price-row">
            <span className="atc-label">Now</span>
            <span className={`atc-val ${winning ? 'up' : 'down'}`}>
              {mid.toFixed(digits)}
              <span className="atc-diff">
                &nbsp;({sign}{priceDiff.toFixed(digits)})
              </span>
            </span>
          </div>
        )}
      </div>

      {/* win / lose status bar */}
      {winning !== null && (
        <div className={`atc-status ${winning ? 'winning' : 'losing'}`}>
          <span>{winning ? '▲ WINNING' : '▼ LOSING'}</span>
          <span className="atc-payout">
            {winning
              ? `+$${(Number(trade.amount) * trade.payout_rate).toFixed(2)}`
              : `-$${Number(trade.amount).toFixed(2)}`}
          </span>
        </div>
      )}
    </div>
  );
}

/* ── Settlement result flash ──────────────────────────────────────────────── */
function ResultFlash({ result, onDone }) {
  useEffect(() => {
    const id = setTimeout(onDone, 3500);
    return () => clearTimeout(id);
  }, []);

  const won = result.status === 'won';
  return (
    <div className={`trade-result-flash ${result.status}`}>
      <div className="trf-icon">{won ? '✓' : '✗'}</div>
      <div className="trf-status">{won ? 'YOU WON' : 'YOU LOST'}</div>
      <div className="trf-amount">
        {won ? `+$${result.profit.toFixed(2)}` : `-$${Number(result.amount).toFixed(2)}`}
      </div>
      {won && <div className="trf-sub">Credited to your balance</div>}
      <button className="trf-dismiss" onClick={onDone}>×</button>
    </div>
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */
export default function TradeTicket({ onToast }) {
  const {
    amount, expirySeconds, expiryOptions, payoutRate,
    setAmount, setExpiry, placeTrade, user, stats, trades,
    selectedSymbol, prices,
  } = useStore();

  const [busy, setBusy]           = useState(false);
  const [now, setNow]             = useState(Date.now());
  const [resultFlash, setResult]  = useState(null); // settled trade to flash

  // 1-Hz clock for market-closed check
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const tick         = prices[selectedSymbol];
  const marketClosed = tick ? (now / 1000 - tick.time) > 60 : false;
  const mid          = tick ? (tick.bid + tick.ask) / 2 : null;

  // digits for price display
  const digits = selectedSymbol === 'USDJPY' ? 3
    : selectedSymbol.startsWith('BTC') || selectedSymbol.startsWith('ETH') || selectedSymbol.startsWith('XAU') ? 2
    : 5;

  // flash animation when bid/ask change
  const prevTickRef = useRef(null);
  const [bidFlash, setBidFlash] = useState('');
  const [askFlash, setAskFlash] = useState('');
  useEffect(() => {
    if (!tick) return;
    const prev = prevTickRef.current;
    if (prev) {
      if (tick.bid !== prev.bid) {
        setBidFlash(tick.bid > prev.bid ? 'flash-up' : 'flash-down');
        setTimeout(() => setBidFlash(''), 250);
      }
      if (tick.ask !== prev.ask) {
        setAskFlash(tick.ask > prev.ask ? 'flash-up' : 'flash-down');
        setTimeout(() => setAskFlash(''), 250);
      }
    }
    prevTickRef.current = tick;
  }, [tick]);

  // Open trades on the current symbol
  const openTrades = useMemo(
    () => (trades || []).filter((t) => t.status === 'open' && t.symbol === selectedSymbol),
    [trades, selectedSymbol]
  );

  // Detect settlement — compare prev open trades to current
  const prevTradesRef = useRef([]);
  useEffect(() => {
    const prevOpen = prevTradesRef.current.filter((t) => t.status === 'open' && t.symbol === selectedSymbol);
    for (const po of prevOpen) {
      const settled = (trades || []).find((t) => t.id === po.id && t.status !== 'open');
      if (settled && (settled.status === 'won' || settled.status === 'lost')) {
        setResult(settled);
        break;
      }
    }
    prevTradesRef.current = trades || [];
  }, [trades, selectedSymbol]);

  // Consecutive losses nudge
  const consecutiveLosses = useMemo(() => {
    let n = 0;
    for (const t of trades) {
      if (t.status === 'open') continue;
      if (t.status === 'lost') n += 1;
      else break;
    }
    return n;
  }, [trades]);
  const showStreakNudge = consecutiveLosses >= STREAK_THRESHOLD;

  const submit = async (direction) => {
    if (busy) return;
    setBusy(true);
    try {
      await placeTrade(direction);
      onToast?.({ kind: 'success', msg: `${direction.toUpperCase()} trade placed @ $${amount}` });
    } catch (e) {
      onToast?.({ kind: 'error', msg: e.message });
    } finally {
      setBusy(false);
    }
  };

  const payout    = (Number(amount) * payoutRate).toFixed(2);
  const fmtExpiry = (s) => s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m` : `${Math.floor(s / 3600)}h`;

  return (
    <div className="ticket">
      <div className="ticket-title">PLACE TRADE</div>

      {/* Live bid / ask price display */}
      <div className="ticket-live-price">
        <div className="ticket-price-col">
          <span className="ticket-price-label">BID</span>
          <span className={`ticket-price-val down ${bidFlash}`}>
            {tick ? tick.bid.toFixed(digits) : '—'}
          </span>
        </div>
        <div className="ticket-price-divider" />
        <div className="ticket-price-col">
          <span className="ticket-price-label">ASK</span>
          <span className={`ticket-price-val up ${askFlash}`}>
            {tick ? tick.ask.toFixed(digits) : '—'}
          </span>
        </div>
      </div>

      {/* Settlement result flash */}
      {resultFlash && (
        <ResultFlash result={resultFlash} onDone={() => setResult(null)} />
      )}

      {/* Active trade cards */}
      {openTrades.length > 0 && !resultFlash && (
        <div className="active-trades-section">
          <div className="active-trades-label">
            {openTrades.length === 1 ? 'ACTIVE TRADE' : `ACTIVE TRADES (${openTrades.length})`}
          </div>
          {openTrades.map((t) => (
            <ActiveTradeCard key={t.id} trade={t} currentPrice={mid} digits={digits} />
          ))}
        </div>
      )}

      {showStreakNudge && (
        <div className="streak-nudge">
          <div className="streak-nudge-text">
            {consecutiveLosses} losses in a row. Trading without training usually looks like this.
          </div>
          <button type="button" className="streak-nudge-cta" onClick={() => openAcademyCta('nudge_streak')}>
            Free 15-min consultation →
          </button>
        </div>
      )}

      {marketClosed && (
        <div className="market-closed-banner">
          <strong>Market closed</strong> — {selectedSymbol} hasn&apos;t updated in over a minute. Trading is paused.
        </div>
      )}

      <div className="field">
        <div className="field-label">Amount (USD)</div>
        <div className="amount-row">
          <input
            type="number" min="1" step="1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <div className="amount-presets">
          {[1, 10, 50, 100].map((v) => (
            <button key={v} className="preset" onClick={() => setAmount(v)}>${v}</button>
          ))}
        </div>
      </div>

      <div className="field">
        <div className="field-label">Expiry</div>
        <div className="expiry-grid">
          {expiryOptions.map((s) => (
            <button
              key={s}
              className={`expiry-btn ${expirySeconds === s ? 'active' : ''}`}
              onClick={() => setExpiry(s)}
            >
              {fmtExpiry(s)}
            </button>
          ))}
        </div>
      </div>

      <div className="payout-info">
        <span style={{ color: 'var(--text-muted)' }}>Potential payout</span>
        <span className="val">+${payout}</span>
      </div>

      <div className="action-buttons">
        <button
          className="btn-up"
          disabled={busy || marketClosed || !user || Number(amount) <= 0 || (user?.balance ?? 0) < Number(amount)}
          onClick={() => submit('up')}
        >
          ▲ UP
        </button>
        <button
          className="btn-down"
          disabled={busy || marketClosed || !user || Number(amount) <= 0 || (user?.balance ?? 0) < Number(amount)}
          onClick={() => submit('down')}
        >
          ▼ DOWN
        </button>
      </div>

      {stats && (
        <div className="stats-card">
          <div className="stats-row"><span className="lbl">Total trades</span><span className="val">{stats.total_trades}</span></div>
          <div className="stats-row"><span className="lbl">Win rate</span><span className="val">{stats.win_rate.toFixed(1)}%</span></div>
          <div className="stats-row"><span className="lbl">Wins</span><span className="val up">{stats.wins}</span></div>
          <div className="stats-row"><span className="lbl">Losses</span><span className="val down">{stats.losses}</span></div>
          <div className="stats-row">
            <span className="lbl">Net P&L</span>
            <span className={`val ${stats.total_profit >= 0 ? 'up' : 'down'}`}>
              ${stats.total_profit.toFixed(2)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
