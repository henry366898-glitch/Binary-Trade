import { useEffect, useMemo, useRef, useState } from 'react';
import { connectStream } from './lib/api';
import { useStore } from './lib/store';
import AuthScreen from './components/AuthScreen';
import SymbolList from './components/SymbolList';
import Chart from './components/Chart';
import TradeTicket from './components/TradeTicket';
import TradesList from './components/TradesList';
import ConversionModal from './components/ConversionModal';
import { Disclaimer, Privacy, Terms } from './components/LegalPages';
import AdminPage from './components/AdminPage';
import TransactionsPage from './components/TransactionsPage';
import ThemeToggle from './components/ThemeToggle';
import { openAcademyCta } from './lib/leadCta';

const RESETS_MAX = 3;
const LOW_BALANCE_THRESHOLD = 2000;
const TRADE_TOAST_THRESHOLD = 10;

function Header({ onLogout }) {
  const user = useStore((s) => s.user);
  const selectedSymbol = useStore((s) => s.selectedSymbol);
  const prices = useStore((s) => s.prices);
  const tick = prices[selectedSymbol];
  const mid = tick ? (tick.bid + tick.ask) / 2 : null;

  const prevRef = useRef(null);
  const [flash, setFlash] = useState('');
  useEffect(() => {
    if (mid != null && prevRef.current != null) {
      if (mid > prevRef.current) setFlash('flash-up');
      else if (mid < prevRef.current) setFlash('flash-down');
      const id = setTimeout(() => setFlash(''), 200);
      prevRef.current = mid;
      return () => clearTimeout(id);
    }
    prevRef.current = mid;
  }, [mid]);

  const digits = selectedSymbol === 'USDJPY' ? 3 :
                 selectedSymbol.startsWith('BTC') || selectedSymbol.startsWith('ETH') || selectedSymbol.startsWith('XAU') ? 2 : 5;

  return (
    <div className="header">
      <div className="brand">
        <span className="dot"></span>
        EDGETRADE
        <span className="practice">PRACTICE</span>
      </div>
      <div className="header-right">
        <div className="chart-symbol">{selectedSymbol}</div>
        <div className={`chart-price ${flash}`}>
          {mid != null ? mid.toFixed(digits) : '—'}
        </div>
        {user?.account_number && (
          <div className="account-pill" title="Your EdgeTrade account number">
            <span className="lbl">A/C</span>
            <span className="val">{user.account_number}</span>
          </div>
        )}
        <div className="balance-pill">
          <span className="lbl">Balance</span>
          <span className="val">${user?.balance.toFixed(2) ?? '0.00'}</span>
        </div>
        <a className="header-link" href="/transactions">Transactions</a>
        <ThemeToggle />
        <button className="logout-btn" onClick={onLogout}>Logout</button>
      </div>
    </div>
  );
}

function ProfileWidget({ user }) {
  const [open, setOpen] = useState(false);
  if (!user) return null;
  const initials = (user.full_name || user.email || '?')
    .split(/\s+/).map((s) => s[0]).slice(0, 2).join('').toUpperCase();
  return (
    <>
      <button type="button" className="profile-pill" onClick={() => setOpen(true)} title="Profile">
        <span className="profile-pill-initials">{initials}</span>
        <span className="profile-pill-name">{user.full_name?.split(/\s+/)[0] || 'Profile'}</span>
      </button>
      {open && (
        <div className="conversion-backdrop" role="dialog" aria-modal="true" onClick={() => setOpen(false)}>
          <div className="conversion-card" style={{ maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
            <button className="conversion-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
            <div className="conversion-heading" style={{ fontSize: 18 }}>Profile</div>
            <div className="client-card" style={{ marginTop: 12 }}>
              <dl>
                <dt>Name</dt><dd>{user.full_name || '—'}</dd>
                <dt>Email</dt><dd style={{ overflowWrap: 'anywhere' }}>{user.email}</dd>
                <dt>Account</dt><dd className="mono" style={{ color: 'var(--accent)' }}>{user.account_number || '—'}</dd>
                <dt>Phone</dt><dd className="mono">{user.phone_number || '—'}</dd>
              </dl>
            </div>
          </div>
        </div>
      )}
    </>
  );
}


export default function App() {
  // simple pathname-based legal-page routing (no router needed)
  const path = typeof window !== 'undefined' ? window.location.pathname : '/';
  if (path === '/disclaimer')   return <Disclaimer />;
  if (path === '/privacy')      return <Privacy />;
  if (path === '/terms')        return <Terms />;
  if (path === '/admin')        return <AdminPage />;
  if (path === '/transactions') return <TransactionsPage />;

  const { user, token, setUser, logout, loadMe, loadMarketMeta, ingestTick, refreshTrades, trades, resetBalance } = useStore();
  const [toast, setToast] = useState(null);
  const [modalVariant, setModalVariant] = useState(null); // 'low' | 'zero' | null

  // decide whether/which modal to show whenever balance changes.
  // never fires until the user has actually traded — otherwise new accounts with
  // a $0 starting balance would see the "you lost it all" modal immediately.
  const lowShownKey = user ? `et_low_shown_${user.id}` : null;
  const hasTraded = (trades?.length ?? 0) > 0;
  useEffect(() => {
    if (!user || !hasTraded) return;
    const bal = user.balance;
    if (bal <= 0) {
      setModalVariant('zero');
    } else if (bal <= LOW_BALANCE_THRESHOLD && lowShownKey && !localStorage.getItem(lowShownKey)) {
      setModalVariant('low');
      localStorage.setItem(lowShownKey, '1');
    }
  }, [user?.balance, user?.id, hasTraded]);

  const resetsUsed = user?.balance_resets_used ?? 0;
  const canReset = resetsUsed < RESETS_MAX;

  const handleReset = async () => {
    try {
      const u = await resetBalance();
      // allow the low-balance modal to fire again next time they drop below threshold
      if (u?.id) localStorage.removeItem(`et_low_shown_${u.id}`);
      setModalVariant(null);
      setToast({ kind: 'success', msg: `Balance reset to $${u.balance.toFixed(2)}` });
    } catch (e) {
      setToast({ kind: 'error', msg: e.message });
    }
  };

  const handleClose = () => setModalVariant(null);

  // fire the "10 trades" CTA toast once per user
  const tradesPlaced = trades?.length ?? 0;
  useEffect(() => {
    if (!user) return;
    const key = `et_toast10_${user.id}`;
    if (tradesPlaced >= TRADE_TOAST_THRESHOLD && !localStorage.getItem(key)) {
      setToast({
        kind: 'cta',
        msg: 'Curious how trained traders approach each trade?',
        cta: 'Talk to a coach →',
        surface: 'toast',
      });
      localStorage.setItem(key, '1');
    }
  }, [tradesPlaced, user?.id]);

  // initial auth check
  useEffect(() => {
    if (token && !user) loadMe();
  }, [token]);

  // load market metadata & connect websocket once authenticated.
  // Depend on user?.id (a stable primitive) NOT the full user object —
  // refreshTrades writes back a new user reference on every poll which
  // would otherwise re-trigger this effect and reconnect the WebSocket.
  const userId = user?.id;
  useEffect(() => {
    if (!userId) return;
    loadMarketMeta();
    refreshTrades();
    const ws = connectStream((msg) => {
      if (msg.type === 'tick') ingestTick(msg);
    });
    return () => ws.close();
  }, [userId]);

  // toast auto-dismiss (CTA toasts linger longer so the user can click)
  useEffect(() => {
    if (!toast) return;
    const ttl = toast.kind === 'cta' ? 10000 : 2500;
    const id = setTimeout(() => setToast(null), ttl);
    return () => clearTimeout(id);
  }, [toast]);

  if (!user) return <AuthScreen />;

  return (
    <div className="app">
      <Header onLogout={logout} />
      <div className="main">
        <SymbolList />
        <div className="chart-panel">
          <div className="chart-header">
            <div className="chart-header-left">
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.1em' }}>
                LIVE · MT5 FEED
              </div>
            </div>
          </div>
          <Chart />
          <TradesList />
        </div>
        <TradeTicket onToast={setToast} />
      </div>
      <ProfileWidget user={user} />
      <div className="app-footer">
        <span className="app-footer-text">
          EdgeTrade is a practice simulation. No real money is traded. Powered by Stewarts Academy.
        </span>
        <button
          type="button"
          className="app-footer-cta"
          onClick={() => openAcademyCta('footer')}
        >
          Book a free call →
        </button>
        <span className="app-footer-sep">·</span>
        <a className="app-footer-link" href="/disclaimer">Disclaimer</a>
        <a className="app-footer-link" href="/privacy">Privacy</a>
        <a className="app-footer-link" href="/terms">Terms</a>
      </div>
      {toast && (
        <div className={`toast ${toast.kind}`}>
          <span>{toast.msg}</span>
          {toast.cta && (
            <button
              type="button"
              className="toast-cta"
              onClick={() => { openAcademyCta(toast.surface || 'toast'); setToast(null); }}
            >
              {toast.cta}
            </button>
          )}
        </div>
      )}
      {modalVariant && (
        <ConversionModal
          variant={modalVariant}
          onClose={handleClose}
          onReset={handleReset}
          canReset={canReset}
          resetsUsed={resetsUsed}
          resetsMax={RESETS_MAX}
        />
      )}
    </div>
  );
}
