import { useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';
import { useStore } from '../lib/store';
import { api } from '../lib/api';

export default function Chart() {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const lastCandleRef = useRef(null);
  const loadedTimeframeRef = useRef(null);
  const loadedSymbolRef = useRef(null);
  const priceLinesRef = useRef([]);
  const selectedSymbol = useStore((s) => s.selectedSymbol);
  const selectedTimeframe = useStore((s) => s.selectedTimeframe);
  const setTimeframe = useStore((s) => s.setTimeframe);
  const prices = useStore((s) => s.prices);
  const trades = useStore((s) => s.trades);

  // initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#11161e' },
        textColor: '#8896a8',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1d2531' },
        horzLines: { color: '#1d2531' },
      },
      rightPriceScale: { borderColor: '#232b38' },
      timeScale: { borderColor: '#232b38', timeVisible: true, secondsVisible: true },
      crosshair: {
        vertLine: { color: '#56657a', width: 1, style: 3 },
        horzLine: { color: '#56657a', width: 1, style: 3 },
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: '#00d68f',
      downColor: '#ff4f6d',
      borderUpColor: '#00d68f',
      borderDownColor: '#ff4f6d',
      wickUpColor: '#00d68f',
      wickDownColor: '#ff4f6d',
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver(() => {
      chart.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, []);

  // load historical candles when symbol or timeframe changes
  useEffect(() => {
    if (!seriesRef.current) return;
    // mark the series as not-yet-loaded for this (symbol, timeframe) combo —
    // the tick effect will skip until setData completes below.
    lastCandleRef.current = null;
    loadedTimeframeRef.current = null;
    loadedSymbolRef.current = null;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.candles(selectedSymbol, selectedTimeframe, 300);
        if (cancelled || !seriesRef.current) return;
        const seen = new Set();
        const cleaned = (res.candles || [])
          .filter((c) => c && Number.isFinite(c.time) && !seen.has(c.time) && (seen.add(c.time) || true))
          .sort((a, b) => a.time - b.time);
        if (cleaned.length) {
          seriesRef.current.setData(cleaned);
          lastCandleRef.current = cleaned[cleaned.length - 1];
        } else {
          const tick = prices[selectedSymbol];
          if (tick) {
            const mid = (tick.bid + tick.ask) / 2;
            const now = Math.floor(Date.now() / 1000);
            const bucket = selectedTimeframe * 60;
            const c = { time: now - (now % bucket), open: mid, high: mid, low: mid, close: mid };
            seriesRef.current.setData([c]);
            lastCandleRef.current = c;
          }
        }
        loadedTimeframeRef.current = selectedTimeframe;
        loadedSymbolRef.current = selectedSymbol;
      } catch (e) {
        console.error('Failed to load candles', e);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedSymbol, selectedTimeframe]);

  // update on tick — but only after the candles for THIS (symbol, timeframe) have loaded.
  // Otherwise we'd be appending a bar at a new-timeframe slot to a series still holding the
  // old timeframe's data, and lightweight-charts throws on time going backward.
  useEffect(() => {
    const tick = prices[selectedSymbol];
    if (!tick || !seriesRef.current) return;
    if (loadedTimeframeRef.current !== selectedTimeframe) return;
    if (loadedSymbolRef.current !== selectedSymbol) return;
    try {
      const mid = (tick.bid + tick.ask) / 2;
      const t = Math.floor(tick.time);
      const bucket = selectedTimeframe * 60;
      const slot = t - (t % bucket);
      let c = lastCandleRef.current;
      if (!c || c.time < slot) {
        c = { time: slot, open: mid, high: mid, low: mid, close: mid };
        lastCandleRef.current = c;
      } else if (c.time === slot) {
        c.high = Math.max(c.high, mid);
        c.low = Math.min(c.low, mid);
        c.close = mid;
      } else {
        return; // older than current bar — skip
      }
      seriesRef.current.update(c);
    } catch {
      // transient; next tick will fix it
    }
  }, [prices, selectedSymbol, selectedTimeframe]);

  // draw a horizontal price line for each OPEN trade on the current symbol —
  // green for UP, red for DOWN, with the stake on the right-axis label.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const pl of priceLinesRef.current) {
      try { series.removePriceLine(pl); } catch {}
    }
    priceLinesRef.current = [];
    const open = (trades || []).filter((t) => t && t.status === 'open' && t.symbol === selectedSymbol);
    for (const t of open) {
      try {
        const pl = series.createPriceLine({
          price: Number(t.entry_price),
          color: t.direction === 'up' ? '#00e5a4' : '#e11d48',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `${t.direction === 'up' ? '▲' : '▼'} $${Number(t.amount || 0).toFixed(0)}`,
        });
        priceLinesRef.current.push(pl);
      } catch (e) {
        // skip a single bad trade rather than crashing the whole chart
      }
    }
  }, [trades, selectedSymbol]);

  const tfLabel = (tf) => (tf === 60 ? '1H' : `${tf}M`);

  return (
    <div className="chart-container">
      <div className="chart-toolbar">
        {[1, 5, 15, 60].map((tf) => (
          <button
            key={tf}
            className={`timeframe-btn ${selectedTimeframe === tf ? 'active' : ''}`}
            onClick={() => setTimeframe(tf)}
          >
            {tfLabel(tf)}
          </button>
        ))}
      </div>
      <div className="chart-canvas-wrap">
        <div className="chart-watermark">{selectedSymbol} · {tfLabel(selectedTimeframe)} · PRACTICE</div>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      </div>
    </div>
  );
}
