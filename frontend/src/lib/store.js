import { create } from 'zustand';
import { api } from './api';

export const useStore = create((set, get) => ({
  // auth
  user: null,
  token: localStorage.getItem('token'),

  // market
  symbols: [],
  selectedSymbol: 'EURUSD',
  selectedTimeframe: 1, // minutes: 1, 5, 15, 60
  prices: {}, // { symbol: { bid, ask, time } }

  // trading
  amount: 10,
  expirySeconds: 60,
  expiryOptions: [30, 60, 120, 300, 600],
  payoutRate: 0.85,

  // trades
  trades: [],
  stats: null,

  setUser: (user, token) => {
    if (token) localStorage.setItem('token', token);
    set({ user, token });
  },
  logout: () => {
    localStorage.removeItem('token');
    set({ user: null, token: null, trades: [], stats: null });
  },

  setSymbol: (s) => set({ selectedSymbol: s }),
  setTimeframe: (tf) => set({ selectedTimeframe: tf }),
  setAmount: (a) => set({ amount: a }),
  setExpiry: (e) => set({ expirySeconds: e }),

  ingestTick: (tick) => set((s) => ({
    prices: { ...s.prices, [tick.symbol]: tick }
  })),

  // returns true if the selected symbol hasn't had a tick in 60+ seconds
  isMarketClosed: (symbol) => {
    const t = get().prices[symbol];
    if (!t) return false; // no data yet — don't show closed until we've ever seen a tick
    return (Date.now() / 1000) - t.time > 60;
  },

  loadMarketMeta: async () => {
    const m = await api.symbols();
    set({ symbols: m.symbols, expiryOptions: m.expiry_options, payoutRate: m.payout_rate });
  },

  loadMe: async () => {
    try {
      const user = await api.me();
      set({ user });
    } catch { get().logout(); }
  },

  refreshTrades: async () => {
    const [trades, stats] = await Promise.all([api.trades(), api.stats()]);
    // Update balance from stats in-place — avoids creating a new user object
    // reference on every poll (which would re-trigger App's [userId] effect).
    set((s) => ({
      trades,
      stats,
      user: s.user ? { ...s.user, balance: stats.balance } : s.user,
    }));
  },

  resetBalance: async () => {
    const user = await api.resetBalance();
    set({ user });
    return user;
  },

  placeTrade: async (direction) => {
    const { selectedSymbol, amount, expirySeconds } = get();
    const trade = await api.placeTrade({
      symbol: selectedSymbol,
      direction,
      amount: Number(amount),
      expiry_seconds: Number(expirySeconds),
    });
    await get().refreshTrades();
    return trade;
  },
}));
