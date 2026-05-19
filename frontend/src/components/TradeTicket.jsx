import { useEffect, useMemo, useState } from 'react';
import { useStore } from '../lib/store';
import { openAcademyCta } from '../lib/leadCta';

const STREAK_THRESHOLD = 5;

export default function TradeTicket({ onToast }) {
  const {
    amount, expirySeconds, expiryOptions, payoutRate,
    setAmount, setExpiry, placeTrade, user, stats, trades,
    selectedSymbol, prices,
  } = useStore();
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  // tick a 1-Hz clock so the market-closed check stays fresh even with no incoming WS ticks
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const tick = prices[selectedSymbol];
  const marketClosed = tick ? (now / 1000 - tick.time) > 60 : false;

  // count consecutive losses among most recent settled trades
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

  const payout = (Number(amount) * payoutRate).toFixed(2);

  const fmtExpiry = (s) =>
    s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m` : `${Math.floor(s / 3600)}h`;

  return (
    <div className="ticket">
      <div className="ticket-title">PLACE TRADE</div>

      {showStreakNudge && (
        <div className="streak-nudge">
          <div className="streak-nudge-text">
            {consecutiveLosses} losses in a row. Trading without training usually looks like this.
          </div>
          <button
            type="button"
            className="streak-nudge-cta"
            onClick={() => openAcademyCta('nudge_streak')}
          >
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
            type="number"
            min="1"
            step="1"
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
