import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';
import { useStore } from '../lib/store';
import ThemeToggle from './ThemeToggle';

function fmtKickoff(iso) {
  const d = new Date(iso);
  const diffMs = d - new Date();
  if (diffMs <= 0) return 'starting…';
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `in ${mins}m`;
  const hrs = Math.floor(mins / 60);
  return `in ${hrs}h ${mins % 60}m`;
}

function StatusTag({ status }) {
  return <span className={`tag ${status}`}>{status}</span>;
}

function BetSlip({ pick, stake, setStake, onPlace, onClear, busy, error, balance, min, max }) {
  if (!pick) {
    return (
      <div className="sb-slip sb-slip-empty">
        <div className="client-card-title">Bet slip</div>
        <p className="sb-muted">Tap any odds to add a selection.</p>
      </div>
    );
  }
  const num = Number(stake);
  const payout = Number.isFinite(num) && num > 0 ? num * pick.odds : 0;
  const tooLow = num < min;
  const tooHigh = num > max;
  const noFunds = num > balance;
  const blocked = busy || !Number.isFinite(num) || num <= 0 || tooLow || tooHigh || noFunds;

  return (
    <div className="sb-slip">
      <div className="sb-slip-head">
        <div className="client-card-title">Bet slip</div>
        <button className="sb-slip-x" onClick={onClear} aria-label="Clear selection">×</button>
      </div>
      <div className="sb-slip-match">{pick.match}</div>
      <div className="sb-slip-pick">
        <span>{pick.market_name} · <strong>{pick.selection_name}</strong></span>
        <span className="sb-odds">{pick.odds.toFixed(2)}</span>
      </div>

      <label className="sb-label">Stake (USD)</label>
      <input
        className="sb-stake"
        type="number" min={min} max={max} step="1"
        value={stake}
        onChange={(e) => setStake(e.target.value)}
        autoFocus
      />
      <div className="sb-presets">
        {[5, 10, 25, 50, 100].map((v) => (
          <button key={v} type="button" className="preset" onClick={() => setStake(String(v))}>${v}</button>
        ))}
      </div>

      <div className="sb-payout-row">
        <span className="sb-muted">Potential payout</span>
        <strong className="sb-payout">${payout.toFixed(2)}</strong>
      </div>

      {error && <div className="auth-error" style={{ marginTop: 8 }}>{error}</div>}
      {!error && noFunds && <div className="sb-hint sb-hint-bad">Stake exceeds your balance (${balance.toFixed(2)}).</div>}
      {!error && tooLow && <div className="sb-hint">Minimum stake is ${min}.</div>}
      {!error && tooHigh && <div className="sb-hint">Maximum stake is ${max}.</div>}

      <button className="sb-place" disabled={blocked} onClick={onPlace}>
        {busy ? 'Placing…' : `Place bet · $${(Number(stake) || 0).toFixed(2)}`}
      </button>
    </div>
  );
}

export default function Sportsbook() {
  const user = useStore((s) => s.user);
  const token = useStore((s) => s.token);
  const loadMe = useStore((s) => s.loadMe);

  const [sports, setSports] = useState([]);
  const [limits, setLimits] = useState({ min: 1, max: 1000 });
  const [activeSport, setActiveSport] = useState('');
  const [events, setEvents] = useState([]);
  const [bets, setBets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [pick, setPick] = useState(null);
  const [stake, setStake] = useState('10');
  const [placing, setPlacing] = useState(false);
  const [slipError, setSlipError] = useState('');
  const [toast, setToast] = useState('');

  useEffect(() => { if (token && !user) loadMe(); }, [token]);

  // load the sports catalogue once
  useEffect(() => {
    (async () => {
      try {
        const d = await api.sbSports();
        setSports(d.sports || []);
        setLimits({ min: d.min_bet ?? 1, max: d.max_bet ?? 1000 });
      } catch (e) { setError(e.message); }
    })();
  }, []);

  const loadEvents = async () => {
    try {
      const d = await api.sbEvents(activeSport || undefined);
      setEvents(d.events || []);
    } catch (e) { setError(e.message); }
  };
  const loadBets = async () => {
    try {
      setBets(await api.sbBets());
      try { await loadMe(); } catch {}
    } catch (e) { /* keep prior */ }
  };

  // refresh events + bets on sport change and on a poll (to see settlement)
  useEffect(() => {
    if (!user) return;
    let alive = true;
    (async () => {
      setLoading(true);
      await Promise.all([loadEvents(), loadBets()]);
      if (alive) setLoading(false);
    })();
    const id = setInterval(() => { loadEvents(); loadBets(); }, 5000);
    return () => { alive = false; clearInterval(id); };
  }, [user?.id, activeSport]);

  if (!token) { if (typeof window !== 'undefined') window.location.href = '/'; return null; }
  if (!user) return <div style={{ padding: 32, color: 'var(--text-muted)' }}>Loading…</div>;

  const selectPick = (ev, market, sel) => {
    setSlipError('');
    setPick({
      event_id: ev.id,
      match: `${ev.home} vs ${ev.away}`,
      market_key: market.key,
      market_name: market.name,
      selection_key: sel.key,
      selection_name: sel.name,
      odds: sel.odds,
    });
  };

  const placeBet = async () => {
    if (!pick) return;
    setPlacing(true); setSlipError('');
    try {
      await api.sbPlaceBet({
        event_id: pick.event_id,
        market_key: pick.market_key,
        selection_key: pick.selection_key,
        stake: Number(stake),
      });
      setToast(`Bet placed: ${pick.selection_name} @ ${pick.odds.toFixed(2)}`);
      setPick(null);
      await loadBets();
      setTimeout(() => setToast(''), 2500);
    } catch (e) { setSlipError(e.message); } finally { setPlacing(false); }
  };

  const openBets = bets.filter((b) => b.status === 'open');
  const settled = bets.filter((b) => b.status !== 'open');

  return (
    <div className="legal-screen">
      <div className="legal-topbar">
        <a className="legal-back" href="/">← Back to EdgeTrade</a>
        <div className="brand" style={{ fontSize: 14 }}>
          <span className="dot"></span>
          EDGETRADE <span className="practice">SPORTSBOOK</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="balance-pill"><span className="lbl">Balance</span><span className="val">${user.balance.toFixed(2)}</span></div>
          <ThemeToggle />
        </div>
      </div>

      <div className="sb-wrap">
        <div className="sb-intro">
          <h1 className="legal-title" style={{ margin: 0 }}>Sports betting</h1>
          <p className="sb-muted" style={{ margin: '4px 0 0' }}>
            Simulated global fixtures · virtual money · wagers use your trading balance.
          </p>
        </div>

        {/* sport filter */}
        <div className="sb-sports">
          <button className={`sb-chip ${!activeSport ? 'active' : ''}`} onClick={() => setActiveSport('')}>All</button>
          {sports.map((s) => (
            <button key={s.sport} className={`sb-chip ${activeSport === s.sport ? 'active' : ''}`} onClick={() => setActiveSport(s.sport)}>
              {s.sport}
            </button>
          ))}
        </div>

        {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}

        <div className="sb-layout">
          {/* events */}
          <div className="sb-events">
            {loading && <div className="sb-muted" style={{ padding: 24 }}>Loading fixtures…</div>}
            {!loading && events.length === 0 && (
              <div className="sb-muted" style={{ padding: 24 }}>No fixtures right now — the simulator is scheduling more, check back in a moment.</div>
            )}
            {events.map((ev) => {
              const live = ev.status === 'live';
              return (
                <div key={ev.id} className={`sb-event ${live ? 'live' : ''}`}>
                  <div className="sb-event-top">
                    <div className="sb-event-meta">
                      <span className="sb-sport-tag">{ev.sport}</span>
                      <span className="sb-league">{ev.league}{ev.country ? ` · ${ev.country}` : ''}</span>
                    </div>
                    <div className={`sb-kick ${live ? 'live' : ''}`}>{live ? '● LIVE' : fmtKickoff(ev.start_time)}</div>
                  </div>
                  <div className="sb-teams">{ev.home} <span className="sb-vs">vs</span> {ev.away}</div>
                  {ev.markets.map((m) => (
                    <div key={m.key} className="sb-market">
                      <div className="sb-market-name">{m.name}{m.line != null ? ` (${m.line})` : ''}</div>
                      <div className="sb-odds-row">
                        {m.selections.map((sel) => {
                          const active = pick && pick.event_id === ev.id && pick.market_key === m.key && pick.selection_key === sel.key;
                          return (
                            <button
                              key={sel.key}
                              className={`sb-odds-btn ${active ? 'active' : ''}`}
                              disabled={live}
                              onClick={() => selectPick(ev, m, sel)}
                              title={live ? 'Betting closed (in play)' : `Add ${sel.name}`}
                            >
                              <span className="sb-odds-name">{sel.name}</span>
                              <span className="sb-odds-val">{sel.odds.toFixed(2)}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>

          {/* side: slip + my bets */}
          <div className="sb-side">
            <BetSlip
              pick={pick}
              stake={stake}
              setStake={setStake}
              onPlace={placeBet}
              onClear={() => { setPick(null); setSlipError(''); }}
              busy={placing}
              error={slipError}
              balance={user.balance}
              min={limits.min}
              max={limits.max}
            />

            <div className="sb-bets">
              <div className="client-card-title" style={{ marginBottom: 8 }}>
                My bets {openBets.length > 0 && <span className="sb-muted">· {openBets.length} open</span>}
              </div>
              {bets.length === 0 && <p className="sb-muted">No bets yet.</p>}
              {bets.map((b) => {
                const leg = b.legs[0] || {};
                return (
                  <div key={b.id} className="sb-bet">
                    <div className="sb-bet-top">
                      <span className="sb-bet-sel">{leg.selection_name}</span>
                      <StatusTag status={b.status} />
                    </div>
                    <div className="sb-bet-sub">{leg.match} · {leg.market_name}</div>
                    <div className="sb-bet-nums">
                      <span>${b.stake.toFixed(2)} @ {b.combined_odds.toFixed(2)}</span>
                      <span className={b.status === 'won' ? 'sb-pos' : b.status === 'lost' ? 'sb-neg' : 'sb-muted'}>
                        {b.status === 'open'
                          ? `→ $${b.potential_payout.toFixed(2)}`
                          : b.status === 'won'
                            ? `+$${b.profit.toFixed(2)}`
                            : b.status === 'void'
                              ? 'refunded'
                              : `-$${b.stake.toFixed(2)}`}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {toast && <div className="toast success"><span>{toast}</span></div>}
    </div>
  );
}
