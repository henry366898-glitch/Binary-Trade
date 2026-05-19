// Lightweight API client. Reads token from localStorage.
const API = '/api';

function authHeaders() {
  const t = localStorage.getItem('token');
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function request(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  register: (data) => request('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  login:    (data) => request('/auth/login',    { method: 'POST', body: JSON.stringify(data) }),
  me:       () => request('/trades/me'),
  symbols:  () => request('/market/symbols'),
  candles:  (sym, tf = 1, n = 100) => request(`/market/candles/${sym}?timeframe=${tf}&count=${n}`),
  placeTrade: (data) => request('/trades', { method: 'POST', body: JSON.stringify(data) }),
  trades:   (limit = 50) => request(`/trades?limit=${limit}`),
  stats:    () => request('/trades/stats'),
  resetBalance: () => request('/trades/reset', { method: 'POST' }),
  transactions: () => request('/trades/transactions'),
  createTransaction: (data) => request('/trades/transactions', { method: 'POST', body: JSON.stringify(data) }),
  paymentTypes: (direction) => request(`/trades/payment_types${direction ? `?direction=${direction}` : ''}`),
  uploadTransactionProof: async (id, file) => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`/api/trades/transactions/${id}/proof`, {
      method: 'POST',
      headers: authHeaders(),
      body: fd,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return res.json();
  },
};

// WebSocket helper
export function connectStream(onTick) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/api/market/stream`);
  ws.onmessage = (e) => {
    try { onTick(JSON.parse(e.data)); } catch {}
  };
  ws.onerror = (e) => console.error('WS error', e);
  return ws;
}
