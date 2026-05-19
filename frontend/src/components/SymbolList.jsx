import { useEffect, useRef } from 'react';
import { useStore } from '../lib/store';

export default function SymbolList() {
  const symbols = useStore((s) => s.symbols);
  const prices = useStore((s) => s.prices);
  const selectedSymbol = useStore((s) => s.selectedSymbol);
  const setSymbol = useStore((s) => s.setSymbol);
  const prevPricesRef = useRef({});

  // track direction for color flash
  const dirs = {};
  for (const sym of symbols) {
    const cur = prices[sym]?.bid;
    const prev = prevPricesRef.current[sym];
    if (cur != null && prev != null) {
      if (cur > prev) dirs[sym] = 'up';
      else if (cur < prev) dirs[sym] = 'down';
    }
  }
  useEffect(() => {
    const snap = {};
    for (const sym of symbols) {
      if (prices[sym]?.bid != null) snap[sym] = prices[sym].bid;
    }
    prevPricesRef.current = snap;
  }, [prices, symbols]);

  const fmt = (n, sym) => {
    if (n == null) return '—';
    const digits = sym === 'USDJPY' ? 3 : sym.startsWith('BTC') || sym.startsWith('ETH') || sym.startsWith('XAU') ? 2 : 5;
    return n.toFixed(digits);
  };

  return (
    <div className="panel symbol-list">
      <div className="symbol-list-title">MARKETS</div>
      {symbols.map((sym) => {
        const t = prices[sym];
        return (
          <div
            key={sym}
            className={`symbol-item ${selectedSymbol === sym ? 'active' : ''}`}
            onClick={() => setSymbol(sym)}
          >
            <div className="symbol-name">{sym}</div>
            <div className={`symbol-price ${dirs[sym] || ''}`}>{fmt(t?.bid, sym)}</div>
          </div>
        );
      })}
    </div>
  );
}
