import { Fragment, useEffect, useMemo, useState } from 'react';
import ThemeToggle from './ThemeToggle';

const TOKEN_KEY = 'et_admin_token';

// ---------- API helper ----------

function getToken() { return sessionStorage.getItem(TOKEN_KEY) || ''; }
function setToken(t) { sessionStorage.setItem(TOKEN_KEY, t); }
function clearToken() { sessionStorage.removeItem(TOKEN_KEY); }

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const t = getToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  const ctype = res.headers.get('content-type') || '';
  return ctype.includes('application/json') ? res.json() : res.text();
}

function waLink(phone, name) {
  const cleaned = String(phone || '').replace(/[^\d+]/g, '');
  const msg = `Hi ${(name || '').split(' ')[0] || 'there'}, this is Stewarts Academy following up on EdgeTrade.`;
  return `https://wa.me/${cleaned.replace(/^\+/, '')}?text=${encodeURIComponent(msg)}`;
}

async function openProofInNewTab(txnId) {
  try {
    const res = await fetch(`/api/admin/transactions/${txnId}/proof`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const w = window.open(url, '_blank');
    // revoke after a delay so the new tab has time to load
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
    if (!w) alert('Pop-up blocked. Please allow pop-ups for this site.');
  } catch (e) {
    alert(`Could not load proof: ${e.message}`);
  }
}

async function downloadAuthed(url, filename) {
  try {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl; a.download = filename;
    a.click();
    URL.revokeObjectURL(objUrl);
  } catch (e) { alert(`Download failed: ${e.message}`); }
}

function leadHeat(l) {
  if (l.academy_clicks_total > 0) return 'hot';
  if (l.balance <= 2000) return 'warm';
  if (l.balance_resets_used > 0) return 'warm';
  return '';
}

function fmtMoney(n) { return `$${Number(n).toFixed(2)}`; }
function fmtSigned(n) { return `${n > 0 ? '+' : ''}$${Number(n).toFixed(2)}`; }
function fmtDate(s) { return s ? new Date(s).toLocaleString() : '—'; }

// ---------- bootstrap / login forms ----------

function BootstrapForm({ onAuthed }) {
  const [secret, setSecret] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault(); setError(''); setBusy(true);
    try {
      const r = await api('/api/admin/auth/bootstrap', {
        method: 'POST',
        body: JSON.stringify({ secret_key: secret, email, password }),
      });
      setToken(r.access_token); onAuthed(r.admin);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card" style={{ width: 420 }}>
        <div className="brand" style={{ marginBottom: 20 }}>
          <span className="dot"></span>EDGETRADE<span className="practice">ADMIN · SETUP</span>
        </div>
        <div className="auth-title">Create the first admin</div>
        <div className="auth-sub">
          No admin accounts exist yet. Use the ADMIN_SECRET from your backend .env to create the first super-admin.
        </div>
        <form className="auth-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}
          <input type="password" placeholder="ADMIN_SECRET (from .env)" value={secret} onChange={(e) => setSecret(e.target.value)} required autoFocus />
          <input type="email" placeholder="Your email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          <input type="password" placeholder="New password (≥ 10 chars)" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={10} autoComplete="new-password" />
          <button type="submit" className="auth-submit" disabled={busy}>{busy ? '…' : 'Create super-admin'}</button>
        </form>
        <div className="disclaimer">
          Once any admin exists this form is permanently disabled. Future admins are created from the admin UI by an existing super-admin.
        </div>
      </div>
    </div>
  );
}

function LoginForm({ onAuthed }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault(); setError(''); setBusy(true);
    try {
      const r = await api('/api/admin/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      setToken(r.access_token); onAuthed(r.admin);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card" style={{ width: 380 }}>
        <div className="brand" style={{ marginBottom: 20 }}>
          <span className="dot"></span>EDGETRADE<span className="practice">ADMIN</span>
        </div>
        <div className="auth-title">Admin sign in</div>
        <div className="auth-sub">Sign in with your admin account.</div>
        <form className="auth-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}
          <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus autoComplete="email" />
          <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
          <button type="submit" className="auth-submit" disabled={busy}>{busy ? '…' : 'Sign in'}</button>
        </form>
      </div>
    </div>
  );
}

// ---------- balance adjust modal (reused by Clients list + detail) ----------

function AdjustModal({ user, onClose, onSaved }) {
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState(null);

  const loadHistory = async () => {
    try { setHistory(await api(`/api/admin/leads/${user.id}/adjustments`)); }
    catch (e) { setError(e.message); }
  };

  const submit = async (e) => {
    e.preventDefault(); setError('');
    const n = Number(amount);
    if (!Number.isFinite(n) || n === 0) { setError('Amount must be a non-zero number'); return; }
    setBusy(true);
    try {
      const adj = await api(`/api/admin/leads/${user.id}/balance_adjust`, {
        method: 'POST',
        body: JSON.stringify({ amount: n, reason: reason.trim() }),
      });
      onSaved?.(adj); onClose();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const preview = (() => {
    const n = Number(amount);
    if (!Number.isFinite(n) || n === 0) return null;
    const after = Math.max(0, +(user.balance + n).toFixed(2));
    return { before: user.balance, after, floored: (user.balance + n) < 0 };
  })();

  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className="conversion-card adjust-card">
        <button className="conversion-close" onClick={onClose} aria-label="Close">×</button>
        <div className="conversion-heading" style={{ fontSize: 18 }}>Adjust balance — {user.full_name}</div>
        <div className="conversion-sub">
          {user.email} · current balance <strong style={{ color: 'var(--text)' }}>${user.balance.toFixed(2)}</strong>.
          Positive = deposit, negative = withdrawal. Balance is floored at $0.
        </div>
        <form className="adjust-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="adjust-row">
            <label>Amount (USD)</label>
            <input type="number" step="0.01" min="-100000" max="100000" placeholder="e.g. 500 or -250" value={amount} onChange={(e) => setAmount(e.target.value)} required autoFocus />
            <div className="adjust-presets">
              {[100, 500, 1000, -100, -500, -1000].map((v) => (
                <button key={v} type="button" className="preset" onClick={() => setAmount(String(v))}>
                  {v > 0 ? `+$${v}` : `-$${Math.abs(v)}`}
                </button>
              ))}
            </div>
          </div>
          <div className="adjust-row">
            <label>Reason (audit log)</label>
            <input type="text" placeholder="e.g. Goodwill deposit for support delay" value={reason} onChange={(e) => setReason(e.target.value)} required minLength={3} maxLength={255} />
          </div>
          {preview && (
            <div className="adjust-preview">
              ${preview.before.toFixed(2)} → <strong>${preview.after.toFixed(2)}</strong>
              {preview.floored && <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>(floored at $0)</span>}
            </div>
          )}
          <div className="conversion-footer">
            <button type="submit" className="conversion-reset" disabled={busy || !amount || !reason}>{busy ? '…' : 'Apply'}</button>
            <button type="button" className="conversion-secondary" onClick={onClose}>Cancel</button>
            <button type="button" className="conversion-secondary" onClick={loadHistory}>
              {history ? 'Refresh history' : 'View history'}
            </button>
          </div>
        </form>
        {history && (
          <div className="adjust-history">
            <div className="adjust-history-title">Past adjustments</div>
            {history.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>None yet.</div>}
            {history.map((h) => (
              <div key={h.id} className="adjust-history-row">
                <span className="mono" style={{ color: h.amount > 0 ? 'var(--up)' : 'var(--down)' }}>
                  {fmtSigned(h.amount)}
                </span>
                <span className="mono" style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                  ${h.balance_before.toFixed(2)} → ${h.balance_after.toFixed(2)}
                </span>
                <span style={{ flex: 1, fontSize: 12 }}>{h.reason}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                  {fmtDate(h.created_at)} · admin #{h.admin_id}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- Clients page (list + detail) ----------

const CLIENT_COLUMNS = [
  { key: 'id',                  label: 'ID',          align: 'right',  width: 50 },
  { key: 'account_number',      label: 'A/C',         align: 'left',   width: 80,  mono: true, fmt: (v) => v || '—' },
  { key: 'signup_date',         label: 'Signup',      align: 'left',   width: 160, fmt: fmtDate },
  { key: 'full_name',           label: 'Name',        align: 'left' },
  { key: 'email',               label: 'Email',       align: 'left' },
  { key: 'phone_number',        label: 'Phone',       align: 'left',   mono: true },
  { key: 'country',             label: 'Country',     align: 'left' },
  { key: 'referral_source',     label: 'Source',      align: 'left',   fmt: (v) => v || '—' },
  { key: 'agreed_to_marketing', label: 'Marketing',   align: 'center', fmt: (v) => v ? 'YES' : 'no' },
  { key: 'balance',             label: 'Balance',     align: 'right',  mono: true, fmt: (v) => `$${v.toFixed(2)}` },
  { key: 'balance_resets_used', label: 'Resets',      align: 'right',  mono: true },
  { key: 'total_trades',        label: 'Trades',      align: 'right',  mono: true },
  { key: 'win_rate_pct',        label: 'Win %',       align: 'right',  mono: true, fmt: (v) => v.toFixed(1) },
  { key: 'total_profit',        label: 'P&L',         align: 'right',  mono: true, fmt: fmtSigned },
  { key: 'academy_clicks_total',label: 'Clicks',      align: 'right',  mono: true },
  { key: 'last_click_surface',  label: 'Last surface',align: 'left',   fmt: (v) => v || '—' },
];

function ClientsPage({ onOpenClient }) {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState('signup_date');
  const [sortDir, setSortDir] = useState('desc');
  const load = async () => {
    setLoading(true); setError('');
    try { const d = await api('/api/admin/leads?format=json'); setLeads(d.leads || []); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const filteredSorted = useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = leads;
    if (q) {
      out = out.filter((l) =>
        [l.full_name, l.email, l.phone_number, l.country, l.referral_source, l.last_click_surface, l.account_number]
          .some((v) => v && String(v).toLowerCase().includes(q))
      );
    }
    out = [...out].sort((a, b) => {
      const av = a[sortKey]; const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      const cmp = String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return out;
  }, [leads, query, sortKey, sortDir]);

  const onSort = (k) => {
    if (sortKey === k) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(k); setSortDir('desc'); }
  };

  const exportXlsx = () => downloadAuthed('/api/admin/leads?format=xlsx', 'edgetrade_clients.xlsx');

  const hotCount = leads.filter((l) => leadHeat(l) === 'hot').length;
  const warmCount = leads.filter((l) => leadHeat(l) === 'warm').length;

  return (
    <>
      <div className="page-header">
        <div className="page-title">Clients</div>
        <div className="page-subtitle">
          <strong>{leads.length}</strong> total · <span className="heat-dot heat-hot" /> <strong>{hotCount}</strong> hot · <span className="heat-dot heat-warm" /> <strong>{warmCount}</strong> warm
        </div>
      </div>
      <div className="admin-toolbar">
        <input
          type="search" placeholder="Search name / email / phone / country / source…"
          value={query} onChange={(e) => setQuery(e.target.value)} className="admin-search"
        />
        <div className="admin-actions">
          <button className="admin-btn" onClick={load} disabled={loading}>{loading ? '…' : 'Refresh'}</button>
          <button className="admin-btn" onClick={exportXlsx}>Export</button>
        </div>
      </div>
      {error && <div className="admin-error">{error}</div>}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th style={{ width: 8 }}></th>
              {CLIENT_COLUMNS.map((c) => (
                <th key={c.key} style={{ textAlign: c.align, minWidth: c.width }}
                  className={`admin-th ${sortKey === c.key ? 'sorted' : ''}`} onClick={() => onSort(c.key)}>
                  {c.label}{sortKey === c.key && <span className="sort-arrow">{sortDir === 'asc' ? '↑' : '↓'}</span>}
                </th>
              ))}
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredSorted.length === 0 && !loading && (
              <tr><td colSpan={CLIENT_COLUMNS.length + 2} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>
                {leads.length === 0 ? 'No clients yet.' : 'No matches for your filter.'}
              </td></tr>
            )}
            {filteredSorted.map((l) => {
              const heat = leadHeat(l);
              return (
                <tr key={l.id} className={`clickable ${heat ? `row-${heat}` : ''}`} onClick={() => onOpenClient(l.id)}>
                  <td><span className={`heat-dot heat-${heat || 'none'}`} /></td>
                  {CLIENT_COLUMNS.map((c) => (
                    <td key={c.key} style={{ textAlign: c.align }} className={c.mono ? 'mono' : ''}>
                      {c.fmt ? c.fmt(l[c.key]) : (l[c.key] ?? '—')}
                    </td>
                  ))}
                  <td className="admin-actions-cell" onClick={(e) => e.stopPropagation()}>
                    <a className="admin-wa" href={waLink(l.phone_number, l.full_name)} target="_blank" rel="noopener noreferrer">WA →</a>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ClientDetail({ clientId, onBack }) {
  const [client, setClient] = useState(null);
  const [trades, setTrades] = useState([]);
  const [adjustments, setAdjustments] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [createTxnOpen, setCreateTxnOpen] = useState(false);
  const [adjFilter, setAdjFilter] = useState('all'); // 'all' | 'deposit' | 'withdrawal'

  const load = async () => {
    setLoading(true); setError('');
    try {
      const [c, t, a] = await Promise.all([
        api(`/api/admin/clients/${clientId}`),
        api(`/api/admin/trades?user_id=${clientId}&limit=200`),
        api(`/api/admin/leads/${clientId}/adjustments`),
      ]);
      setClient(c); setTrades(t.trades || []); setAdjustments(a || []);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [clientId]);

  const toggleDisable = async () => {
    const action = client.disabled_at ? 'enable' : 'disable';
    if (action === 'disable' && !confirm(`Disable ${client.full_name}? They will be unable to log in.`)) return;
    try { await api(`/api/admin/clients/${client.id}/${action}`, { method: 'POST' }); await load(); }
    catch (e) { setError(e.message); }
  };

  if (loading && !client) return <div style={{ padding: 32, color: 'var(--text-muted)' }}>Loading client…</div>;
  if (error) return <div className="admin-error">{error}</div>;
  if (!client) return null;

  const filteredAdjustments = adjFilter === 'all'
    ? adjustments
    : adjustments.filter((a) => (adjFilter === 'deposit' ? a.amount > 0 : a.amount < 0));

  return (
    <>
      <div className="page-header">
        <div>
          <button className="admin-btn admin-btn-secondary" onClick={onBack}>← Back to clients</button>
          <div className="page-title" style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
            {client.full_name}
            {client.disabled_at && <span className="tag down">DISABLED</span>}
          </div>
          <div className="page-subtitle">
            Client #{client.id} · A/C <strong style={{ color: 'var(--accent)' }}>{client.account_number || '—'}</strong> · joined {fmtDate(client.signup_date)}
          </div>
        </div>
        <div className="admin-actions">
          <button className="admin-btn" onClick={() => setCreateTxnOpen(true)} style={{ color: 'var(--accent)', borderColor: 'var(--accent)' }}>+ Create txn</button>
          <button
            className="admin-btn"
            onClick={toggleDisable}
            style={{ color: client.disabled_at ? 'var(--up)' : 'var(--down)', borderColor: client.disabled_at ? 'var(--up)' : 'var(--down)' }}
          >
            {client.disabled_at ? 'Enable client' : 'Disable client'}
          </button>
          <a className="admin-btn" href={waLink(client.phone_number, client.full_name)} target="_blank" rel="noopener noreferrer">
            Message on WhatsApp →
          </a>
        </div>
      </div>

      <div className="client-grid">
        <div className="client-card">
          <div className="client-card-title">Profile</div>
          <dl>
            <dt>Email</dt><dd>{client.email}</dd>
            <dt>Phone</dt><dd className="mono">{client.phone_number}</dd>
            <dt>Country</dt><dd>{client.country}</dd>
            <dt>Referral source</dt><dd>{client.referral_source || '—'}</dd>
            <dt>Marketing consent</dt><dd>{client.agreed_to_marketing ? 'YES' : 'no'}</dd>
          </dl>
        </div>
        <div className="client-card">
          <div className="client-card-title">Account</div>
          <dl>
            <dt>Balance</dt><dd className="mono" style={{ color: 'var(--accent)' }}>{fmtMoney(client.balance)}</dd>
            <dt>Resets used</dt><dd className="mono">{client.balance_resets_used} / 3</dd>
            <dt>Total trades</dt><dd className="mono">{client.total_trades}</dd>
            <dt>Wins / Losses</dt><dd className="mono"><span style={{ color: 'var(--up)' }}>{client.wins}</span> / <span style={{ color: 'var(--down)' }}>{client.losses}</span></dd>
            <dt>Win rate</dt><dd className="mono">{client.win_rate_pct.toFixed(1)}%</dd>
            <dt>Net P&L</dt><dd className="mono" style={{ color: client.total_profit >= 0 ? 'var(--up)' : 'var(--down)' }}>{fmtSigned(client.total_profit)}</dd>
          </dl>
        </div>
        <div className="client-card">
          <div className="client-card-title">Academy CTA clicks ({client.academy_clicks.length})</div>
          {client.academy_clicks.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No clicks yet.</div>}
          {client.academy_clicks.map((c) => (
            <div key={c.id} className="click-row">
              <span className="tag open">{c.surface}</span>
              <span style={{ flex: 1, fontSize: 12 }}>balance ${c.balance_at_click.toFixed(2)} · {c.total_trades_at_click} trades</span>
              <span style={{ color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>{fmtDate(c.created_at)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="page-section-title">Trades ({trades.length})</div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th><th>Opened</th><th>Symbol</th><th>Dir</th>
              <th style={{ textAlign: 'right' }}>Amount</th>
              <th style={{ textAlign: 'right' }}>Entry</th>
              <th style={{ textAlign: 'right' }}>Exit</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>P&L</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 && <tr><td colSpan={9} style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>No trades.</td></tr>}
            {trades.map((t) => (
              <tr key={t.id}>
                <td className="mono">{t.id}</td>
                <td className="mono">{fmtDate(t.opened_at)}</td>
                <td className="mono">{t.symbol}</td>
                <td><span className={`tag ${t.direction}`}>{t.direction}</span></td>
                <td className="mono" style={{ textAlign: 'right' }}>{fmtMoney(t.amount)}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{t.entry_price.toFixed(5)}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{t.exit_price != null ? t.exit_price.toFixed(5) : '—'}</td>
                <td><span className={`tag ${t.status}`}>{t.status}</span></td>
                <td className="mono" style={{ textAlign: 'right', color: t.profit > 0 ? 'var(--up)' : t.profit < 0 ? 'var(--down)' : 'inherit' }}>
                  {t.status === 'open' ? '—' : fmtSigned(t.profit)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '24px 28px 10px' }}>
        <div className="page-section-title" style={{ padding: 0 }}>Balance adjustments ({filteredAdjustments.length}{filteredAdjustments.length !== adjustments.length ? ` / ${adjustments.length}` : ''})</div>
        <select
          className="admin-search" style={{ maxWidth: 200 }}
          value={adjFilter}
          onChange={(e) => setAdjFilter(e.target.value)}
        >
          <option value="all">All adjustments</option>
          <option value="deposit">Deposits only</option>
          <option value="withdrawal">Withdrawals only</option>
        </select>
      </div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>When</th><th>Type</th>
              <th style={{ textAlign: 'right' }}>Amount</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>Before</th>
              <th style={{ textAlign: 'right' }}>After</th>
              <th>Reason</th><th>Proof</th><th>By</th>
            </tr>
          </thead>
          <tbody>
            {filteredAdjustments.length === 0 && <tr><td colSpan={9} style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>No adjustments match the filter.</td></tr>}
            {filteredAdjustments.map((a) => (
              <tr key={a.id}>
                <td className="mono">{fmtDate(a.created_at)}</td>
                <td><span className={`tag ${a.amount > 0 ? 'up' : 'down'}`}>{a.amount > 0 ? 'deposit' : 'withdrawal'}</span></td>
                <td className="mono" style={{ textAlign: 'right', color: a.amount > 0 ? 'var(--up)' : 'var(--down)' }}>{fmtSigned(a.amount)}</td>
                <td><span className={`tag ${a.status === 'pending' ? 'open' : a.status === 'approved' ? 'won' : 'lost'}`}>{a.status}</span></td>
                <td className="mono" style={{ textAlign: 'right' }}>{a.balance_before != null ? fmtMoney(a.balance_before) : '—'}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{a.balance_after != null ? fmtMoney(a.balance_after) : '—'}</td>
                <td className="cell-wrap">{a.reason}</td>
                <td>
                  {a.proof_image_path ? (
                    <button className="admin-wa" style={{ background: 'transparent', border: 'none', padding: 0 }} onClick={() => openProofInNewTab(a.id)}>View</button>
                  ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                </td>
                <td className="mono">{a.admin_id ? `admin #${a.admin_id}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {createTxnOpen && (
        <NewTransactionModal
          preSelectedClient={{ id: client.id, full_name: client.full_name, email: client.email, balance: client.balance, account_number: client.account_number }}
          onClose={() => setCreateTxnOpen(false)}
          onSaved={() => load()}
        />
      )}
    </>
  );
}

// ---------- Trades page (global) ----------

function TradesPage() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [symbolFilter, setSymbolFilter] = useState('');

  const load = async () => {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams({ limit: '300' });
      if (statusFilter) params.set('status', statusFilter);
      if (symbolFilter) params.set('symbol', symbolFilter);
      const d = await api(`/api/admin/trades?${params.toString()}`);
      setTrades(d.trades || []);
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [statusFilter, symbolFilter]);

  const symbols = useMemo(() => [...new Set(trades.map((t) => t.symbol))].sort(), [trades]);

  const totalPL = trades.reduce((s, t) => s + (t.status === 'open' ? 0 : t.profit), 0);

  return (
    <>
      <div className="page-header">
        <div className="page-title">Trades</div>
        <div className="page-subtitle">
          <strong>{trades.length}</strong> shown · net P&L <strong style={{ color: totalPL >= 0 ? 'var(--up)' : 'var(--down)' }}>{fmtSigned(totalPL)}</strong>
        </div>
      </div>
      <div className="admin-toolbar">
        <select className="admin-search" style={{ maxWidth: 200 }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="open">open</option>
          <option value="won">won</option>
          <option value="lost">lost</option>
          <option value="tie">tie</option>
        </select>
        <select className="admin-search" style={{ maxWidth: 200 }} value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}>
          <option value="">All symbols</option>
          {['EURUSD','GBPUSD','USDJPY','XAUUSD','BTCUSD','ETHUSD'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <div className="admin-actions">
          <button className="admin-btn" onClick={load} disabled={loading}>{loading ? '…' : 'Refresh'}</button>
          <button className="admin-btn" onClick={() => {
            const params = new URLSearchParams({ format: 'xlsx', limit: '1000' });
            if (statusFilter) params.set('status', statusFilter);
            if (symbolFilter) params.set('symbol', symbolFilter);
            downloadAuthed(`/api/admin/trades?${params}`, 'edgetrade_trades.xlsx');
          }}>Export</button>
        </div>
      </div>
      {error && <div className="admin-error">{error}</div>}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th><th>Opened</th><th>Client</th><th>Symbol</th><th>Dir</th>
              <th style={{ textAlign: 'right' }}>Amount</th>
              <th style={{ textAlign: 'right' }}>Entry</th>
              <th style={{ textAlign: 'right' }}>Exit</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>P&L</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 && !loading && (
              <tr><td colSpan={10} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>No trades match.</td></tr>
            )}
            {trades.map((t) => (
              <tr key={t.id}>
                <td className="mono">{t.id}</td>
                <td className="mono">{fmtDate(t.opened_at)}</td>
                <td>{t.user_name} <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>#{t.user_id}</span></td>
                <td className="mono">{t.symbol}</td>
                <td><span className={`tag ${t.direction}`}>{t.direction}</span></td>
                <td className="mono" style={{ textAlign: 'right' }}>{fmtMoney(t.amount)}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{t.entry_price.toFixed(5)}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{t.exit_price != null ? t.exit_price.toFixed(5) : '—'}</td>
                <td><span className={`tag ${t.status}`}>{t.status}</span></td>
                <td className="mono" style={{ textAlign: 'right', color: t.profit > 0 ? 'var(--up)' : t.profit < 0 ? 'var(--down)' : 'inherit' }}>
                  {t.status === 'open' ? '—' : fmtSigned(t.profit)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ---------- Approve verification modal (math challenge to confirm) ----------

function ApproveVerifyModal({ txn, onClose, onConfirmed }) {
  const a = useMemo(() => Math.floor(Math.random() * 9) + 2, []);
  const b = useMemo(() => Math.floor(Math.random() * 9) + 2, []);
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault(); setError('');
    if (Number(answer) !== a + b) {
      setError('Incorrect answer. Try again.');
      return;
    }
    setBusy(true);
    try { await onConfirmed(); onClose(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className="conversion-card adjust-card" style={{ maxWidth: 420 }}>
        <button className="conversion-close" onClick={onClose} aria-label="Close">×</button>
        <div className="conversion-heading" style={{ fontSize: 18 }}>Confirm approval</div>
        <div className="conversion-sub">
          About to approve <strong>{txn.direction}</strong> of <strong style={{ color: txn.amount > 0 ? 'var(--up)' : 'var(--down)' }}>${Math.abs(txn.amount).toFixed(2)}</strong> for <strong>{txn.user_name}</strong>.
          This applies the balance change immediately.
        </div>
        <form className="adjust-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="adjust-row">
            <label>To confirm, what is <strong style={{ color: 'var(--accent)', fontSize: 16 }}>{a} + {b}</strong>?</label>
            <input type="number" placeholder="?" value={answer}
              onChange={(e) => setAnswer(e.target.value)} required autoFocus />
          </div>
          <div className="conversion-footer">
            <button type="submit" className="conversion-reset" disabled={busy || !answer}
              style={!busy && answer ? { background: 'var(--up)', color: '#0a0d12' } : undefined}>
              {busy ? '…' : 'Confirm approve'}
            </button>
            <button type="button" className="conversion-secondary" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}


// ---------- Reject reason modal ----------

function RejectReasonModal({ txn, onClose, onConfirmed }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault(); setError('');
    const r = reason.trim();
    if (r.length < 3) { setError('Reason must be at least 3 characters'); return; }
    setBusy(true);
    try { await onConfirmed(r); onClose(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className="conversion-card adjust-card" style={{ maxWidth: 480 }}>
        <button className="conversion-close" onClick={onClose} aria-label="Close">×</button>
        <div className="conversion-heading" style={{ fontSize: 18 }}>Reject transaction</div>
        <div className="conversion-sub">
          Rejecting <strong>{txn.direction}</strong> of <strong style={{ color: 'var(--down)' }}>${Math.abs(txn.amount).toFixed(2)}</strong> for <strong>{txn.user_name}</strong>.
          The reason below is shown to the client.
        </div>
        <form className="adjust-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="adjust-row">
            <label>Rejection reason (visible to client)</label>
            <input type="text" placeholder="e.g. Bank details could not be verified — please resubmit"
              value={reason} onChange={(e) => setReason(e.target.value)}
              required minLength={3} maxLength={255} autoFocus />
          </div>
          <div className="conversion-footer">
            <button type="submit" className="conversion-reset" disabled={busy || reason.trim().length < 3}
              style={!busy && reason.trim().length >= 3 ? { background: 'var(--down)', color: '#0a0d12' } : undefined}>
              {busy ? '…' : 'Reject transaction'}
            </button>
            <button type="button" className="conversion-secondary" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}


// ---------- Transaction details modal (admin view of a single transaction) ----------

function TxnDetailsModal({ txn, onClose, onApprove, onReject }) {
  const bd = txn.bank_details;
  const isPending = txn.status === 'pending';
  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className="conversion-card adjust-card">
        <button className="conversion-close" onClick={onClose} aria-label="Close">×</button>
        <div className="conversion-heading" style={{ fontSize: 18 }}>
          Transaction #{txn.id} · <span className={`tag ${txn.amount > 0 ? 'up' : 'down'}`}>{txn.direction}</span> <span className={`tag ${isPending ? 'open' : txn.status === 'approved' ? 'won' : 'lost'}`}>{txn.status}</span>
        </div>
        <div className="conversion-sub">
          Client: <strong>{txn.user_name}</strong> · {txn.user_email} · A/C <strong style={{ color: 'var(--accent)' }}>{txn.user_account_number || '—'}</strong>
        </div>

        <div className="client-card" style={{ marginTop: 8 }}>
          <div className="client-card-title">Amount</div>
          <dl>
            <dt>Amount</dt><dd className="mono" style={{ color: txn.amount > 0 ? 'var(--up)' : 'var(--down)' }}>{txn.amount > 0 ? '+' : ''}${txn.amount.toFixed(2)}</dd>
            <dt>Balance before</dt><dd className="mono">{txn.balance_before != null ? `$${txn.balance_before.toFixed(2)}` : '—'}</dd>
            <dt>Balance after</dt><dd className="mono">{txn.balance_after != null ? `$${txn.balance_after.toFixed(2)}` : '—'}</dd>
            <dt>Reason / note</dt><dd style={{ overflowWrap: 'anywhere' }}>{txn.reason}</dd>
            <dt>Payment method</dt><dd>{txn.payment_type_name || <span style={{ color: 'var(--text-muted)' }}>—</span>}</dd>
            <dt>Requested at</dt><dd className="mono">{fmtDate(txn.created_at)}</dd>
            {txn.processed_at && <><dt>Processed at</dt><dd className="mono">{fmtDate(txn.processed_at)}</dd></>}
          </dl>
        </div>

        {txn.status === 'rejected' && txn.reject_reason && (
          <div className="client-card" style={{ marginTop: 10, borderColor: 'var(--down)' }}>
            <div className="client-card-title" style={{ color: 'var(--down)' }}>Rejection reason</div>
            <div style={{ color: 'var(--text)', fontSize: 13, overflowWrap: 'anywhere', wordBreak: 'break-word', lineHeight: 1.5 }}>
              {txn.reject_reason}
            </div>
          </div>
        )}

        {bd && Object.keys(bd).length > 0 && (
          <div className="client-card" style={{ marginTop: 10 }}>
            <div className="client-card-title">Bank / wallet details (provided by client)</div>
            <dl>
              {Object.entries(bd).map(([label, value]) => (
                <Fragment key={label}>
                  <dt>{label.replace(/_/g, ' ')}</dt>
                  <dd className="mono" style={{ overflowWrap: 'anywhere' }}>{value || '—'}</dd>
                </Fragment>
              ))}
            </dl>
          </div>
        )}

        <div className="conversion-footer" style={{ marginTop: 16 }}>
          {txn.has_proof && (
            <button type="button" className="admin-btn" onClick={() => openProofInNewTab(txn.id)}>
              View payment proof
            </button>
          )}
          {isPending && onApprove && (
            <button type="button" className="conversion-reset" style={{ background: 'var(--up)', color: '#0a0d12' }}
              onClick={onApprove}>
              Approve
            </button>
          )}
          {isPending && onReject && (
            <button type="button" className="admin-btn" style={{ color: 'var(--down)', borderColor: 'var(--down)' }}
              onClick={onReject}>
              Reject
            </button>
          )}
          <button type="button" className="conversion-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}


// ---------- New transaction modal (deposit / withdrawal from Transactions page) ----------

function NewTransactionModal({ mode: initialMode, preSelectedClient, onClose, onSaved }) {
  // mode toggleable inside the modal so this works as both "+ Deposit" / "− Withdrawal"
  // from the toolbar AND as a single "Create txn" button from a client's detail page.
  const [mode, setMode] = useState(initialMode || 'deposit');
  const [clients, setClients] = useState([]);
  const [clientQuery, setClientQuery] = useState('');
  const [selectedClient, setSelectedClient] = useState(preSelectedClient || null);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [proof, setProof] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (preSelectedClient) return;
    (async () => {
      try { const d = await api('/api/admin/leads?format=json'); setClients(d.leads || []); }
      catch (e) { setError(e.message); }
    })();
  }, [preSelectedClient]);

  const filtered = useMemo(() => {
    const q = clientQuery.trim().toLowerCase();
    if (!q) return clients.slice(0, 20);
    return clients.filter((c) =>
      [c.full_name, c.email, c.phone_number, String(c.id)]
        .some((v) => v && String(v).toLowerCase().includes(q))
    ).slice(0, 20);
  }, [clients, clientQuery]);

  const submit = async (e) => {
    e.preventDefault(); setError('');
    if (!selectedClient) { setError('Pick a client first'); return; }
    const raw = Number(amount);
    if (!Number.isFinite(raw) || raw <= 0) { setError('Amount must be a positive number'); return; }
    const signed = mode === 'deposit' ? raw : -raw;
    setBusy(true);
    try {
      const adj = await api(`/api/admin/leads/${selectedClient.id}/balance_adjust`, {
        method: 'POST',
        body: JSON.stringify({ amount: signed, reason: reason.trim() }),
      });
      if (proof) {
        try {
          const fd = new FormData();
          fd.append('file', proof);
          const res = await fetch(`/api/admin/transactions/${adj.id}/proof`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${getToken()}` },
            body: fd,
          });
          if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${res.status}`); }
        } catch (e) {
          setError(`Transaction saved (#${adj.id}) but proof upload failed: ${e.message}`);
        }
      }
      onSaved?.(adj); onClose();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const preview = (() => {
    if (!selectedClient) return null;
    const raw = Number(amount);
    if (!Number.isFinite(raw) || raw <= 0) return null;
    const signed = mode === 'deposit' ? raw : -raw;
    const after = Math.max(0, +(selectedClient.balance + signed).toFixed(2));
    return { before: selectedClient.balance, after, floored: (selectedClient.balance + signed) < 0 };
  })();

  const isDeposit = mode === 'deposit';

  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className="conversion-card adjust-card">
        <button className="conversion-close" onClick={onClose} aria-label="Close">×</button>
        <div className="conversion-heading" style={{ fontSize: 18 }}>Create transaction</div>
        <div className="conversion-sub">
          Direct admin-initiated transaction (records as <strong>approved</strong> immediately).
          Withdrawals are floored at $0.
        </div>

        <form className="adjust-form" onSubmit={submit}>
          {error && <div className="auth-error">{error}</div>}

          <div className="adjust-row">
            <label>Type</label>
            <div className="txn-direction-toggle">
              <button type="button"
                className={`txn-dir-btn ${isDeposit ? 'active deposit' : ''}`}
                onClick={() => setMode('deposit')}>+ Deposit</button>
              <button type="button"
                className={`txn-dir-btn ${!isDeposit ? 'active withdrawal' : ''}`}
                onClick={() => setMode('withdrawal')}>− Withdrawal</button>
            </div>
          </div>

          <div className="adjust-row">
            <label>Client</label>
            {selectedClient ? (
              <div className="picked-client">
                <div>
                  <strong>{selectedClient.full_name}</strong>
                  <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 8, fontFamily: 'var(--font-mono)' }}>
                    A/C {selectedClient.account_number || '—'} · {selectedClient.email} · balance ${selectedClient.balance.toFixed(2)}
                  </span>
                </div>
                {!preSelectedClient && (
                  <button type="button" className="admin-btn admin-btn-secondary" onClick={() => setSelectedClient(null)}>Change</button>
                )}
              </div>
            ) : (
              <>
                <input
                  type="text"
                  placeholder="Search by name / email / phone / id"
                  value={clientQuery}
                  onChange={(e) => setClientQuery(e.target.value)}
                  autoFocus
                />
                <div className="client-picker-list">
                  {filtered.length === 0 && <div style={{ padding: 12, color: 'var(--text-muted)', fontSize: 12 }}>No matches.</div>}
                  {filtered.map((c) => (
                    <button
                      key={c.id} type="button" className="client-picker-row"
                      onClick={() => { setSelectedClient(c); setClientQuery(''); }}
                    >
                      <span><strong>{c.full_name}</strong> <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>#{c.id}</span></span>
                      <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>{c.email}</span>
                      <span className="mono" style={{ color: 'var(--accent)', fontSize: 12 }}>${c.balance.toFixed(2)}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <div className="adjust-row">
            <label>{isDeposit ? 'Deposit amount (USD)' : 'Withdrawal amount (USD)'}</label>
            <input
              type="number" step="0.01" min="0.01" max="100000"
              placeholder="e.g. 500"
              value={amount} onChange={(e) => setAmount(e.target.value)}
              required disabled={!selectedClient}
            />
            <div className="adjust-presets">
              {[50, 100, 500, 1000, 2500, 5000].map((v) => (
                <button key={v} type="button" className="preset" disabled={!selectedClient}
                  onClick={() => setAmount(String(v))}>${v}</button>
              ))}
            </div>
          </div>

          <div className="adjust-row">
            <label>Reason (visible to client)</label>
            <input
              type="text"
              placeholder={isDeposit ? 'e.g. Goodwill credit for support delay' : 'e.g. Refund of duplicate credit'}
              value={reason} onChange={(e) => setReason(e.target.value)}
              required minLength={3} maxLength={255}
              disabled={!selectedClient}
            />
          </div>

          <div className="adjust-row">
            <label>Proof (optional)</label>
            <input type="file"
              accept=".jpg,.jpeg,.png,.webp,.pdf"
              onChange={(e) => setProof(e.target.files?.[0] || null)}
              disabled={!selectedClient} />
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {proof ? `Selected: ${proof.name} (${(proof.size / 1024).toFixed(0)} KB)` : 'JPG / PNG / WebP / PDF, max 5MB'}
            </div>
          </div>

          {preview && (
            <div className="adjust-preview">
              ${preview.before.toFixed(2)} → <strong>${preview.after.toFixed(2)}</strong>
              {preview.floored && <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>(floored at $0)</span>}
            </div>
          )}

          <div className="conversion-footer">
            <button
              type="submit"
              className="conversion-reset"
              disabled={busy || !selectedClient || !amount || !reason}
              style={!busy && selectedClient && amount && reason ? { background: isDeposit ? 'var(--up)' : 'var(--down)', color: '#0a0d12' } : undefined}
            >
              {busy ? '…' : isDeposit ? `Deposit $${amount || '…'}` : `Withdraw $${amount || '…'}`}
            </button>
            <button type="button" className="conversion-secondary" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------- Transactions page (global balance adjustments) ----------

function TransactionsPage() {
  const [txns, setTxns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [directionFilter, setDirectionFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [newTxnMode, setNewTxnMode] = useState(null);
  const [detailTxn, setDetailTxn] = useState(null);

  const load = async () => {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams({ limit: '300' });
      if (directionFilter) params.set('direction', directionFilter);
      if (statusFilter) params.set('status', statusFilter);
      const d = await api(`/api/admin/transactions?${params.toString()}`);
      setTxns(d.transactions || []);
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [directionFilter, statusFilter]);

  // client-side date range filter on top of the loaded results
  const filteredTxns = useMemo(() => {
    if (!dateFrom && !dateTo) return txns;
    const from = dateFrom ? new Date(dateFrom + 'T00:00:00').getTime() : -Infinity;
    const to = dateTo ? new Date(dateTo + 'T23:59:59.999').getTime() : Infinity;
    return txns.filter((t) => {
      const ts = new Date(t.created_at).getTime();
      return ts >= from && ts <= to;
    });
  }, [txns, dateFrom, dateTo]);

  const [approveTxn, setApproveTxn] = useState(null);
  const [rejectTxn, setRejectTxn] = useState(null);

  const doApprove = async (id) => {
    await api(`/api/admin/transactions/${id}/approve`, { method: 'POST' });
    await load();
  };
  const doReject = async (id, reason) => {
    await api(`/api/admin/transactions/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
    await load();
  };

  const approved = filteredTxns.filter((t) => t.status === 'approved');
  const depositTotal = approved.filter((t) => t.amount > 0).reduce((s, t) => s + t.amount, 0);
  const withdrawTotal = approved.filter((t) => t.amount < 0).reduce((s, t) => s + Math.abs(t.amount), 0);
  const pendingCount = filteredTxns.filter((t) => t.status === 'pending').length;

  return (
    <>
      <div className="page-header">
        <div className="page-title">Transactions</div>
        <div className="page-subtitle">
          <strong>{filteredTxns.length}</strong> shown · <span style={{ color: pendingCount > 0 ? 'var(--accent)' : 'inherit' }}><strong>{pendingCount}</strong> pending</span> · deposits <strong style={{ color: 'var(--up)' }}>{fmtMoney(depositTotal)}</strong> · withdrawals <strong style={{ color: 'var(--down)' }}>{fmtMoney(withdrawTotal)}</strong>
        </div>
      </div>
      <div className="admin-toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
        <select className="admin-search" style={{ maxWidth: 160 }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <select className="admin-search" style={{ maxWidth: 160 }} value={directionFilter} onChange={(e) => setDirectionFilter(e.target.value)}>
          <option value="">All directions</option>
          <option value="deposit">Deposits</option>
          <option value="withdrawal">Withdrawals</option>
        </select>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          From
          <input type="date" className="admin-search" style={{ maxWidth: 150 }} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          to
          <input type="date" className="admin-search" style={{ maxWidth: 150 }} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          {(dateFrom || dateTo) && (
            <button className="admin-btn admin-btn-secondary" onClick={() => { setDateFrom(''); setDateTo(''); }}>×</button>
          )}
        </div>
        <div style={{ flex: 1 }} />
        <div className="admin-actions">
          <button className="admin-btn" onClick={() => setNewTxnMode('deposit')} style={{ color: 'var(--up)', borderColor: 'var(--up)' }}>
            + Deposit
          </button>
          <button className="admin-btn" onClick={() => setNewTxnMode('withdrawal')} style={{ color: 'var(--down)', borderColor: 'var(--down)' }}>
            − Withdrawal
          </button>
          <button className="admin-btn" onClick={load} disabled={loading}>{loading ? '…' : 'Refresh'}</button>
          <button className="admin-btn" onClick={() => {
            const params = new URLSearchParams({ format: 'xlsx', limit: '1000' });
            if (directionFilter) params.set('direction', directionFilter);
            if (statusFilter) params.set('status', statusFilter);
            downloadAuthed(`/api/admin/transactions?${params}`, 'edgetrade_transactions.xlsx');
          }}>Export</button>
        </div>
      </div>
      {error && <div className="admin-error">{error}</div>}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>When</th><th>Client</th><th>Type</th><th>Method</th>
              <th style={{ textAlign: 'right' }}>Amount</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>Before</th>
              <th style={{ textAlign: 'right' }}>After</th>
              <th>Reason</th><th>Proof</th><th>By</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredTxns.length === 0 && !loading && (
              <tr><td colSpan={12} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>No transactions match.</td></tr>
            )}
            {filteredTxns.map((t) => (
              <tr key={t.id} className={t.status === 'pending' ? 'row-warm' : ''}>
                <td className="mono">{fmtDate(t.created_at)}</td>
                <td>{t.user_name} <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>#{t.user_id}</span></td>
                <td>
                  <span className={`tag ${t.amount > 0 ? 'up' : 'down'}`}>{t.direction}</span>
                  {t.is_client_request && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--text-muted)' }}>(client req)</span>}
                </td>
                <td>{t.payment_type_name || <span style={{ color: 'var(--text-muted)' }}>—</span>}</td>
                <td className="mono" style={{ textAlign: 'right', color: t.amount > 0 ? 'var(--up)' : 'var(--down)' }}>{fmtSigned(t.amount)}</td>
                <td>
                  <span className={`tag ${t.status === 'pending' ? 'open' : t.status === 'approved' ? 'won' : 'lost'}`}>{t.status}</span>
                </td>
                <td className="mono" style={{ textAlign: 'right' }}>{t.balance_before != null ? fmtMoney(t.balance_before) : '—'}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{t.balance_after != null ? fmtMoney(t.balance_after) : '—'}</td>
                <td className="cell-wrap">{t.reason}</td>
                <td>
                  {t.has_proof ? (
                    <button className="admin-wa" style={{ background: 'transparent', border: 'none', padding: 0 }} onClick={() => openProofInNewTab(t.id)}>View</button>
                  ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                </td>
                <td className="mono" style={{ fontSize: 11 }}>{t.admin_email || (t.admin_id ? `admin #${t.admin_id}` : '—')}</td>
                <td className="admin-actions-cell">
                  <button className="admin-row-btn" onClick={() => setDetailTxn(t)}>Details</button>
                  {t.status === 'pending' && (
                    <>
                      <button className="admin-row-btn" style={{ color: 'var(--up)' }} onClick={() => setApproveTxn(t)}>Approve</button>
                      <button className="admin-row-btn" style={{ color: 'var(--down)' }} onClick={() => setRejectTxn(t)}>Reject</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {newTxnMode && (
        <NewTransactionModal
          mode={newTxnMode}
          onClose={() => setNewTxnMode(null)}
          onSaved={() => load()}
        />
      )}
      {detailTxn && (
        <TxnDetailsModal
          txn={detailTxn}
          onClose={() => setDetailTxn(null)}
          onApprove={() => { setApproveTxn(detailTxn); setDetailTxn(null); }}
          onReject={() => { setRejectTxn(detailTxn); setDetailTxn(null); }}
        />
      )}
      {approveTxn && (
        <ApproveVerifyModal
          txn={approveTxn}
          onClose={() => setApproveTxn(null)}
          onConfirmed={() => doApprove(approveTxn.id)}
        />
      )}
      {rejectTxn && (
        <RejectReasonModal
          txn={rejectTxn}
          onClose={() => setRejectTxn(null)}
          onConfirmed={(reason) => doReject(rejectTxn.id, reason)}
        />
      )}
    </>
  );
}

// ---------- Payment types page ----------

const BLANK_PT = {
  name: '', enabled: true,
  deposit_enabled: true, withdrawal_enabled: false,
  deposit_min: 0, deposit_max: 100000,
  withdrawal_min: 0, withdrawal_max: 100000,
  instructions: '', display_order: 0,
  fields: [],
};

function PaymentTypeEditor({ initial, onSave, onCancel, busy, error }) {
  const [f, setF] = useState({ ...BLANK_PT, ...(initial || {}), fields: (initial?.fields || []).map((x) => ({ ...x })) });
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  // image is "enabled" if the type already has one OR the admin toggles it on
  const [imageEnabled, setImageEnabled] = useState(!!initial?.has_image);

  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const num = (k, v) => set(k, v === '' ? 0 : Number(v));

  const addField = () => setF((s) => ({ ...s, fields: [...s.fields, { label: '', value: '' }] }));
  const removeField = (i) => setF((s) => ({ ...s, fields: s.fields.filter((_, idx) => idx !== i) }));
  const updateField = (i, key, val) => setF((s) => ({
    ...s, fields: s.fields.map((x, idx) => idx === i ? { ...x, [key]: val } : x),
  }));

  // load existing image for edit mode
  useEffect(() => {
    if (!initial?.has_image) return;
    let url;
    (async () => {
      try {
        const res = await fetch(`/api/admin/payment_types/${initial.id}/image`, { headers: { Authorization: `Bearer ${getToken()}` } });
        if (!res.ok) return;
        const blob = await res.blob();
        url = URL.createObjectURL(blob);
        setImagePreview(url);
      } catch {}
    })();
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [initial?.id, initial?.has_image]);

  const onImagePick = (file) => {
    setImageFile(file);
    if (file) {
      const url = URL.createObjectURL(file);
      setImagePreview(url);
    }
  };

  return (
    <div className="conversion-backdrop" role="dialog" aria-modal="true">
      <div className="conversion-card adjust-card" style={{ maxWidth: 720 }}>
        <button className="conversion-close" onClick={onCancel} aria-label="Close">×</button>
        <div className="conversion-heading" style={{ fontSize: 18 }}>
          {initial ? `Edit payment type: ${initial.name}` : 'New payment type'}
        </div>
        <div className="conversion-sub">
          Define which directions this method supports, the per-direction min/max, and the data fields.
          For <strong>deposits</strong>, the values you enter below are shown to the client.
          For <strong>withdrawals</strong>, the labels become input fields the client must fill.
        </div>

        <form className="adjust-form" onSubmit={(e) => { e.preventDefault(); onSave(f, imageFile); }}>
          {error && <div className="auth-error">{error}</div>}

          <div className="adjust-row">
            <label>Name *</label>
            <input value={f.name} onChange={(e) => set('name', e.target.value)} required minLength={2} maxLength={128} placeholder="e.g. USDT TRC20 / Bank Transfer UAE" />
          </div>

          <div className="adjust-row">
            <label>Availability</label>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center', fontSize: 13, color: 'var(--text-dim)' }}>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input type="checkbox" checked={f.deposit_enabled} onChange={(e) => set('deposit_enabled', e.target.checked)} /> Deposit
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input type="checkbox" checked={f.withdrawal_enabled} onChange={(e) => set('withdrawal_enabled', e.target.checked)} /> Withdrawal
              </label>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center', marginLeft: 'auto' }}>
                <input type="checkbox" checked={f.enabled} onChange={(e) => set('enabled', e.target.checked)} /> Enabled
              </label>
            </div>
          </div>

          {f.deposit_enabled && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div className="adjust-row"><label>Deposit min ($)</label><input type="number" min="0" step="0.01" value={f.deposit_min} onChange={(e) => num('deposit_min', e.target.value)} /></div>
              <div className="adjust-row"><label>Deposit max ($)</label><input type="number" min="0" step="0.01" value={f.deposit_max} onChange={(e) => num('deposit_max', e.target.value)} /></div>
            </div>
          )}
          {f.withdrawal_enabled && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div className="adjust-row"><label>Withdrawal min ($)</label><input type="number" min="0" step="0.01" value={f.withdrawal_min} onChange={(e) => num('withdrawal_min', e.target.value)} /></div>
              <div className="adjust-row"><label>Withdrawal max ($)</label><input type="number" min="0" step="0.01" value={f.withdrawal_max} onChange={(e) => num('withdrawal_max', e.target.value)} /></div>
            </div>
          )}

          <div className="adjust-row">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={imageEnabled}
                onChange={(e) => {
                  setImageEnabled(e.target.checked);
                  if (!e.target.checked) { setImageFile(null); setImagePreview(null); }
                }}
              />
              Image / QR (visible to client during deposit)
            </label>
            {imageEnabled && (
              <>
                <input type="file" accept=".jpg,.jpeg,.png,.webp" onChange={(e) => onImagePick(e.target.files?.[0] || null)} />
                {imagePreview && (
                  <img src={imagePreview} alt="payment image"
                    style={{ marginTop: 6, maxWidth: 240, maxHeight: 200, borderRadius: 6, border: '1px solid var(--border)' }} />
                )}
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  Optional. JPG / PNG / WebP, max 5MB.
                </div>
              </>
            )}
          </div>

          <div className="adjust-row">
            <label>Instructions (short note above the fields)</label>
            <input value={f.instructions || ''} onChange={(e) => set('instructions', e.target.value)} maxLength={2000} placeholder="e.g. Send the amount to the wallet below and upload your receipt" />
          </div>

          <div className="adjust-row">
            <label>Fields (columns)</label>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: -4 }}>
              For deposits, the value you enter is shown to the client. For withdrawals, the client fills it in.
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
              {f.fields.map((field, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr auto', gap: 6 }}>
                  <input placeholder="Label (e.g. IBAN)" value={field.label} onChange={(e) => updateField(i, 'label', e.target.value)} maxLength={64} />
                  <input placeholder="Value (for deposit display, leave blank if withdrawal-only)" value={field.value || ''} onChange={(e) => updateField(i, 'value', e.target.value)} maxLength={512} />
                  <button type="button" className="admin-btn admin-btn-secondary" onClick={() => removeField(i)} style={{ padding: '6px 10px' }}>×</button>
                </div>
              ))}
              <button type="button" className="admin-btn" onClick={addField} style={{ alignSelf: 'flex-start', marginTop: 4 }}>+ Add field</button>
            </div>
          </div>

          <div className="adjust-row">
            <label>Display order</label>
            <input type="number" value={f.display_order} onChange={(e) => num('display_order', e.target.value)} style={{ maxWidth: 120 }} />
          </div>

          <div className="conversion-footer">
            <button type="submit" className="conversion-reset" disabled={busy || !f.name}
              style={!busy && f.name ? { background: 'var(--accent)', color: '#0a0d12' } : undefined}>
              {busy ? '…' : (initial ? 'Save changes' : 'Create payment type')}
            </button>
            <button type="button" className="conversion-secondary" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PaymentTypesPage() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');
  const [editorOpen, setEditorOpen] = useState(false); // false | true (new) | object (edit)
  const [busy, setBusy] = useState(false);
  const [editorError, setEditorError] = useState('');

  const load = async () => {
    try { setItems(await api('/api/admin/payment_types')); }
    catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, []);

  const uploadImage = async (id, file) => {
    if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    const res = await fetch(`/api/admin/payment_types/${id}/image`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
      body: fd,
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${res.status}`); }
  };

  const save = async (rawF, imageFile) => {
    setBusy(true); setEditorError('');
    try {
      // strip rows with no label and trim whitespace — sending half-filled rows yields validation noise
      const f = {
        ...rawF,
        fields: (rawF.fields || [])
          .map((x) => ({ label: (x.label || '').trim(), value: (x.value || '').trim() || null }))
          .filter((x) => x.label),
      };
      const isEdit = editorOpen && typeof editorOpen === 'object';
      const res = isEdit
        ? await api(`/api/admin/payment_types/${editorOpen.id}`, { method: 'PATCH', body: JSON.stringify(f) })
        : await api('/api/admin/payment_types', { method: 'POST', body: JSON.stringify(f) });
      if (imageFile) {
        try { await uploadImage(res.id, imageFile); }
        catch (e) { setEditorError(`Saved but image upload failed: ${e.message}`); setBusy(false); await load(); return; }
      }
      setEditorOpen(false);
      await load();
    } catch (e) { setEditorError(e.message); }
    finally { setBusy(false); }
  };

  const remove = async (p) => {
    if (!confirm(`Delete "${p.name}"? If any transactions reference it, it'll be disabled instead.`)) return;
    setError('');
    try { await api(`/api/admin/payment_types/${p.id}`, { method: 'DELETE' }); await load(); }
    catch (e) { setError(e.message); }
  };

  return (
    <>
      <div className="page-header">
        <div className="page-title">Payment Types</div>
        <div className="page-subtitle">
          <strong>{items.length}</strong> total · <strong>{items.filter((p) => p.enabled).length}</strong> enabled
        </div>
      </div>
      <div className="admin-toolbar">
        <div style={{ flex: 1 }} />
        <button className="admin-btn" onClick={() => { setEditorError(''); setEditorOpen(true); }}>
          + New payment type
        </button>
      </div>
      {error && <div className="admin-error">{error}</div>}
      {editorOpen && (
        <PaymentTypeEditor
          initial={typeof editorOpen === 'object' ? editorOpen : null}
          onSave={save}
          onCancel={() => { setEditorOpen(false); setEditorError(''); }}
          busy={busy}
          error={editorError}
        />
      )}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th><th>Name</th><th>Status</th><th>Direction</th>
              <th style={{ textAlign: 'right' }}>Deposit min/max</th>
              <th style={{ textAlign: 'right' }}>W/d min/max</th>
              <th>Image</th>
              <th>Instructions</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr><td colSpan={9} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>
                No payment types yet. Click <strong>+ New payment type</strong> to create one.
              </td></tr>
            )}
            {items.map((p) => (
              <tr key={p.id} className={!p.enabled ? 'row-warm' : ''}>
                <td className="mono">{p.id}</td>
                <td><strong>{p.name}</strong></td>
                <td><span className={`tag ${p.enabled ? 'won' : 'lost'}`}>{p.enabled ? 'enabled' : 'disabled'}</span></td>
                <td>
                  {p.deposit_enabled && <span className="tag up" style={{ marginRight: 4 }}>deposit</span>}
                  {p.withdrawal_enabled && <span className="tag down">w/d</span>}
                  {!p.deposit_enabled && !p.withdrawal_enabled && <span style={{ color: 'var(--text-muted)' }}>—</span>}
                </td>
                <td className="mono" style={{ textAlign: 'right' }}>
                  {p.deposit_enabled ? `$${p.deposit_min} – $${p.deposit_max}` : '—'}
                </td>
                <td className="mono" style={{ textAlign: 'right' }}>
                  {p.withdrawal_enabled ? `$${p.withdrawal_min} – $${p.withdrawal_max}` : '—'}
                </td>
                <td>
                  {p.has_image ? (
                    <button className="admin-wa" style={{ background: 'transparent', border: 'none', padding: 0 }}
                      onClick={async () => {
                        try {
                          const res = await fetch(`/api/admin/payment_types/${p.id}/image`, { headers: { Authorization: `Bearer ${getToken()}` } });
                          if (!res.ok) throw new Error(`HTTP ${res.status}`);
                          const blob = await res.blob();
                          const url = URL.createObjectURL(blob);
                          window.open(url, '_blank');
                          setTimeout(() => URL.revokeObjectURL(url), 30_000);
                        } catch (e) { alert(`Could not load: ${e.message}`); }
                      }}>View</button>
                  ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                  <label className="admin-wa" style={{ marginLeft: 8, cursor: 'pointer' }}>
                    {p.has_image ? 'Replace' : 'Upload'}
                    <input type="file" accept=".jpg,.jpeg,.png,.webp,.pdf" style={{ display: 'none' }}
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        try { await uploadImage(p.id, file); await load(); }
                        catch (err) { setError(err.message); }
                      }} />
                  </label>
                </td>
                <td className="cell-wrap" style={{ maxWidth: 280, fontSize: 12 }}>{p.instructions || '—'}</td>
                <td className="admin-actions-cell">
                  <button className="admin-row-btn" onClick={() => { setEditorError(''); setEditorOpen(p); }}>Edit</button>
                  <button className="admin-row-btn" style={{ color: 'var(--down)' }} onClick={() => remove(p)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}


// ---------- Admins page (super_admin only) ----------

function AdminsPage({ currentAdmin }) {
  const [admins, setAdmins] = useState([]);
  const [error, setError] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [newPw, setNewPw] = useState('');
  const [newRole, setNewRole] = useState('admin');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { setAdmins(await api('/api/admin/users')); }
    catch (e) { setError(e.message); }
  };
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault(); setError(''); setBusy(true);
    try {
      await api('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({ email: newEmail, password: newPw, role: newRole }),
      });
      setNewEmail(''); setNewPw(''); setNewRole('admin'); setShowAdd(false);
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const remove = async (id, email) => {
    if (!confirm(`Delete admin ${email}? This cannot be undone.`)) return;
    setError('');
    try { await api(`/api/admin/users/${id}`, { method: 'DELETE' }); await load(); }
    catch (e) { setError(e.message); }
  };

  return (
    <>
      <div className="page-header">
        <div className="page-title">Admins</div>
        <div className="page-subtitle"><strong>{admins.length}</strong> admin accounts</div>
      </div>
      <div className="admin-toolbar">
        <div style={{ flex: 1 }} />
        <button className="admin-btn" onClick={() => setShowAdd((v) => !v)}>{showAdd ? 'Cancel' : '+ Add admin'}</button>
      </div>
      {error && <div className="admin-error">{error}</div>}
      {showAdd && (
        <form className="admin-add-form" onSubmit={create}>
          <input type="email" placeholder="Email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} required />
          <input type="password" placeholder="Password (≥ 10 chars)" value={newPw} onChange={(e) => setNewPw(e.target.value)} required minLength={10} />
          <select value={newRole} onChange={(e) => setNewRole(e.target.value)}>
            <option value="admin">admin</option>
            <option value="super_admin">super_admin</option>
          </select>
          <button type="submit" className="admin-btn" disabled={busy}>{busy ? '…' : 'Create'}</button>
        </form>
      )}
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>ID</th><th>Email</th><th>Role</th><th>Created</th><th>Created by</th><th></th>
            </tr>
          </thead>
          <tbody>
            {admins.map((a) => (
              <tr key={a.id}>
                <td className="mono">{a.id}</td>
                <td>{a.email}</td>
                <td><span className={`tag ${a.role === 'super_admin' ? 'open' : 'up'}`}>{a.role}</span></td>
                <td className="mono">{fmtDate(a.created_at)}</td>
                <td className="mono">{a.created_by_id ?? '—'}</td>
                <td>
                  {a.id !== currentAdmin.id && (
                    <button className="admin-wa" style={{ color: 'var(--down)' }} onClick={() => remove(a.id, a.email)}>
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ---------- root layout (sidebar + main) ----------

const NAV_ITEMS = [
  { key: 'clients',       label: 'Clients',       icon: 'C' },
  { key: 'trades',        label: 'Trades',        icon: 'T' },
  { key: 'transactions',  label: 'Transactions',  icon: '$' },
  { key: 'payment_types', label: 'Payment Types', icon: 'P' },
  { key: 'admins',        label: 'Admins',        icon: 'A', superOnly: true },
];

export default function AdminPage() {
  const [status, setStatus] = useState(null);
  const [admin, setAdmin] = useState(null);
  const [nav, setNav] = useState('clients');
  const [selectedClientId, setSelectedClientId] = useState(null);
  const [bootError, setBootError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const s = await api('/api/admin/auth/status');
        setStatus(s);
        if (s.has_admins && getToken()) {
          try { setAdmin(await api('/api/admin/auth/me')); }
          catch { clearToken(); }
        }
      } catch (e) { setBootError(e.message); }
    })();
  }, []);

  const signOut = () => { clearToken(); setAdmin(null); };

  if (bootError) return <div className="admin-error" style={{ margin: 24 }}>Could not contact backend: {bootError}</div>;
  if (status == null) return <div style={{ padding: 24, color: 'var(--text-muted)' }}>Loading…</div>;

  if (!status.has_admins) return <BootstrapForm onAuthed={(a) => { setAdmin(a); setStatus({ has_admins: true }); }} />;
  if (!admin) return <LoginForm onAuthed={setAdmin} />;

  const isSuper = admin.role === 'super_admin';
  const visibleNav = NAV_ITEMS.filter((i) => !i.superOnly || isSuper);

  const goToNav = (key) => { setNav(key); setSelectedClientId(null); };

  let page;
  if (nav === 'clients') {
    page = selectedClientId
      ? <ClientDetail clientId={selectedClientId} onBack={() => setSelectedClientId(null)} />
      : <ClientsPage onOpenClient={setSelectedClientId} />;
  } else if (nav === 'trades')        page = <TradesPage />;
  else if (nav === 'transactions')    page = <TransactionsPage />;
  else if (nav === 'payment_types')   page = <PaymentTypesPage />;
  else if (nav === 'admins')          page = <AdminsPage currentAdmin={admin} />;

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-sidebar-brand">
          <span className="dot"></span>
          <div>
            <div style={{ fontWeight: 700, letterSpacing: '-0.02em' }}>EDGETRADE</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.1em' }}>ADMIN</div>
          </div>
        </div>
        <nav className="admin-sidebar-nav">
          {visibleNav.map((item) => (
            <button
              key={item.key}
              className={`admin-nav-item ${nav === item.key ? 'active' : ''}`}
              onClick={() => goToNav(item.key)}
            >
              <span className="admin-nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="admin-sidebar-foot">
          <div className="admin-who" style={{ margin: 0, lineHeight: 1.4 }}>
            <div style={{ color: 'var(--text)' }}>{admin.email}</div>
            <div><em>{admin.role}</em></div>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button className="admin-btn admin-btn-secondary" onClick={signOut} style={{ flex: 1 }}>Sign out</button>
            <ThemeToggle />
          </div>
        </div>
      </aside>
      <main className="admin-main">
        {page}
      </main>
    </div>
  );
}
