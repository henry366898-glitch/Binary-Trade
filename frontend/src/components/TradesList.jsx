import { useEffect, useState } from 'react';
import { useStore } from '../lib/store';

function Countdown({ expiresAt }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, []);
  const ms = new Date(expiresAt).getTime() - now;
  if (ms <= 0) return <span style={{ color: 'var(--accent)' }}>settling…</span>;
  const s = Math.ceil(ms / 1000);
  return <span style={{ color: 'var(--accent)' }}>{s}s</span>;
}

// compact HH:MM:SS for trade rows
function fmtTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
  return d.toLocaleTimeString();
}

export default function TradesList() {
  const trades = useStore((s) => s.trades);
  const refreshTrades = useStore((s) => s.refreshTrades);

  // Poll for settlements — only while there are open trades, every 2s.
  // Empty dep array: start once on mount. refreshTrades is a stable Zustand
  // action so it never needs to be in the dep array.
  const hasOpen = trades.some((t) => t.status === 'open');
  useEffect(() => {
    if (!hasOpen) return; // no open trades — nothing to poll for
    const id = setInterval(refreshTrades, 2000);
    return () => clearInterval(id);
  }, [hasOpen]);

  return (
    <div className="trades-strip">
      <div className="trades-strip-header">
        <div className="trades-strip-title">RECENT TRADES</div>
      </div>
      <div className="trades-table">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Dir</th>
              <th>Amount</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Opened</th>
              <th>Closed</th>
              <th>Expiry</th>
              <th>Status</th>
              <th>P&L</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 && (
              <tr><td colSpan={10} style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
                No trades yet — place your first trade
              </td></tr>
            )}
            {trades.map((t) => (
              <tr key={t.id}>
                <td>{t.symbol}</td>
                <td><span className={`tag ${t.direction}`}>{t.direction}</span></td>
                <td>${t.amount.toFixed(2)}</td>
                <td>{t.entry_price.toFixed(5)}</td>
                <td>{t.exit_price != null ? t.exit_price.toFixed(5) : '—'}</td>
                <td>{fmtTime(t.opened_at)}</td>
                <td>{t.status === 'open' ? '—' : fmtTime(t.settled_at)}</td>
                <td>{t.status === 'open' ? <Countdown expiresAt={t.expires_at + 'Z'} /> : fmtTime(t.expires_at)}</td>
                <td><span className={`tag ${t.status}`}>{t.status}</span></td>
                <td className={t.status === 'won' ? 'up' : t.status === 'lost' ? 'down' : ''}
                    style={{ color: t.status === 'won' ? 'var(--up)' : t.status === 'lost' ? 'var(--down)' : 'inherit' }}>
                  {t.status === 'open' ? '—' : (t.profit >= 0 ? '+' : '') + '$' + t.profit.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
