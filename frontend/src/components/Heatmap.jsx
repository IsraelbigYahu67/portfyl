import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHeatmap } from "../api";
import { useStockDetail } from "./StockDetail";

const PERIODS = [
  { key: "1d", label: "1D" },
  { key: "1w", label: "1W" },
  { key: "mtd", label: "MTD" },
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "ytd", label: "YTD" },
  { key: "1y", label: "1Y" },
  { key: "5y", label: "5Y" },
];

// Gain→loss gradient derived from the theme's --gain/--loss tokens via
// color-mix() so heatmap tiles track the live theme/accent instead of an
// independent hardcoded scale.
const STOPS = [
  { min: 3,    color: "color-mix(in srgb, var(--gain) 100%, black 15%)" },
  { min: 1.5,  color: "var(--gain)" },
  { min: 0.5,  color: "color-mix(in srgb, var(--gain) 70%, var(--surface-card) 30%)" },
  { min: 0,    color: "color-mix(in srgb, var(--gain) 35%, var(--surface-card) 65%)" },
  { min: -0.001, color: "var(--surface-card-elevated)" }, // ~0%, avoids float-equality edge case
  { min: -0.5, color: "color-mix(in srgb, var(--loss) 35%, var(--surface-card) 65%)" },
  { min: -1.5, color: "color-mix(in srgb, var(--loss) 70%, var(--surface-card) 30%)" },
  { min: -3,   color: "var(--loss)" },
  { min: -Infinity, color: "color-mix(in srgb, var(--loss) 100%, black 15%)" },
];

function getColor(pct) {
  return (STOPS.find((s) => pct >= s.min) || STOPS[STOPS.length - 1]).color;
}

function getTileTextColor(pct) {
  if (pct >= 0.5 || pct <= -1.5) return "text-white";
  return "text-ink";
}

// Squarified treemap (Bruls/Huijing/van Wijk).
// Rows are laid along the SHORTER side. Tiles within a row stack along that
// short side; the row thickness extends along the long side.
function squarify(items, W, H) {
  const sorted = [...items].sort((a, b) => {
    if (a.ticker === "__small__") return 1;
    if (b.ticker === "__small__") return -1;
    return b.weight - a.weight;
  });
  const total = sorted.reduce((s, it) => s + it.weight, 0) || 1;
  const scaled = sorted.map((it) => ({ ...it, area: (it.weight / total) * W * H }));

  const placed = [];
  let x = 0, y = 0, w = W, h = H;

  function worst(row, short) {
    const sum = row.reduce((s, r) => s + r.area, 0);
    if (sum <= 0 || short <= 0) return Infinity;
    const s2 = short * short;
    const sum2 = sum * sum;
    let mx = -Infinity, mn = Infinity;
    for (const r of row) {
      if (r.area > mx) mx = r.area;
      if (r.area < mn) mn = r.area;
    }
    return Math.max((s2 * mx) / sum2, sum2 / (s2 * mn));
  }

  function flushRow(row) {
    const sum = row.reduce((s, r) => s + r.area, 0);
    if (sum <= 0) return;
    if (w >= h) {
      // wide rectangle: row stacks vertically along h, thickness goes right
      const thickness = sum / h;
      let off = 0;
      for (const r of row) {
        const len = r.area / thickness;
        placed.push({ x, y: y + off, w: thickness, h: len, item: r });
        off += len;
      }
      x += thickness;
      w -= thickness;
    } else {
      // tall rectangle: row stacks horizontally along w, thickness goes down
      const thickness = sum / w;
      let off = 0;
      for (const r of row) {
        const len = r.area / thickness;
        placed.push({ x: x + off, y, w: len, h: thickness, item: r });
        off += len;
      }
      y += thickness;
      h -= thickness;
    }
  }

  let queue = [...scaled];
  let row = [];
  while (queue.length) {
    const short = Math.min(w, h);
    if (short <= 0) break;
    if (row.length === 0) {
      row.push(queue.shift());
      continue;
    }
    const candidate = [...row, queue[0]];
    if (worst(candidate, short) <= worst(row, short)) {
      row.push(queue.shift());
    } else {
      flushRow(row);
      row = [];
    }
  }
  if (row.length) flushRow(row);

  return placed;
}

export default function Heatmap() {
  const [period, setPeriod] = useState("1d");
  const [containerEl, setContainerEl] = useState(null);
  const [size, setSize] = useState({ w: 400, h: 400 });
  const [showSmallTooltip, setShowSmallTooltip] = useState(false);
  const tooltipRef = useRef(null);
  const { openStock } = useStockDetail();

  const { data = [], isLoading } = useQuery({
    queryKey: ["heatmap", period],
    queryFn: () => fetchHeatmap(period),
  });

  useEffect(() => {
    if (!containerEl) return;
    const ro = new ResizeObserver(() => {
      const r = containerEl.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) setSize({ w: r.width, h: r.height });
    });
    ro.observe(containerEl);
    return () => ro.disconnect();
  }, [containerEl]);

  const bigItems = data.filter((d) => d.weight >= 1);
  const smallItems = data.filter((d) => d.weight < 1);
  const smallWeight = smallItems.reduce((s, d) => s + d.weight, 0);

  const treeData = bigItems.length
    ? [...bigItems, ...(smallItems.length ? [{ ticker: "__small__", weight: smallWeight, change_pct: 0 }] : [])]
    : data;
  const tiles = treeData.length ? squarify(treeData.map((d) => ({ ...d, weight: d.weight })), size.w, size.h) : [];

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs font-semibold text-muted uppercase tracking-wider">
          Heatmap
        </h2>
        <div className="flex gap-0.5 bg-surface-hover rounded-lg p-0.5">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              onClick={() => setPeriod(p.key)}
              className={`px-2 py-1 text-[11px] rounded-md font-medium transition-colors ${
                period === p.key
                  ? "bg-surface-card text-brand font-semibold shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center min-h-[300px]">
          <div className="text-muted text-sm animate-pulse">Loading heatmap...</div>
        </div>
      ) : data.length === 0 ? (
        <p className="text-muted text-xs">No holdings data available.</p>
      ) : (
        <div
          ref={setContainerEl}
          className="relative flex-1 w-full overflow-hidden"
          style={{ minHeight: "400px" }}
        >
          {tiles.map((t) => {
            if (t.item.ticker === "__small__") {
              return (
                <div
                  key="__small__"
                  ref={tooltipRef}
                  onMouseEnter={() => setShowSmallTooltip(true)}
                  onMouseLeave={() => setShowSmallTooltip(false)}
                  className="absolute rounded cursor-default flex items-center justify-center overflow-visible"
                  style={{
                    left: `${t.x}px`,
                    top: `${t.y}px`,
                    width: `${t.w - 2}px`,
                    height: `${t.h - 2}px`,
                    backgroundColor: "var(--bg-subtle)",
                  }}
                >
                  <span className="text-muted font-bold text-lg tracking-widest">...</span>
                  {showSmallTooltip && (
                    <div
                      className="absolute z-50 bg-surface-card-elevated border border-hairline rounded-lg shadow-xl p-3 min-w-[240px] max-h-[300px] overflow-y-auto"
                      style={{ bottom: "calc(100% + 8px)", right: 0 }}
                    >
                      <div className="text-[10px] font-semibold text-muted uppercase mb-2">Small positions (&lt;1%)</div>
                      <div className="space-y-1.5">
                        {[...smallItems].sort((a, b) => b.weight - a.weight).map((s) => (
                          <div
                            key={s.ticker}
                            onClick={() => openStock(s.ticker)}
                            className="flex items-center justify-between gap-3 text-xs cursor-pointer hover:bg-surface-hover rounded px-1 py-0.5"
                          >
                            <span className="font-mono font-semibold text-ink">{s.ticker}</span>
                            <div className="flex items-center gap-2">
                              <span className={`font-medium ${s.change_pct >= 0 ? "text-gain" : "text-loss"}`}>
                                {s.change_pct >= 0 ? "+" : ""}{s.change_pct}%
                              </span>
                              <span className="text-muted font-medium">{s.weight}%</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            }
            const area = t.w * t.h;
            return (
              <div
                key={t.item.ticker}
                onClick={() => openStock(t.item.ticker)}
                className={`absolute rounded transition-opacity hover:opacity-80 cursor-pointer flex flex-col items-center justify-center overflow-hidden ${getTileTextColor(t.item.change_pct)}`}
                style={{
                  left: `${t.x}px`,
                  top: `${t.y}px`,
                  width: `${t.w - 2}px`,
                  height: `${t.h - 2}px`,
                  backgroundColor: getColor(t.item.change_pct),
                }}
                title={`${t.item.ticker} | ${t.item.change_pct >= 0 ? "+" : ""}${t.item.change_pct}% | Weight: ${t.item.weight}%`}
              >
                <span
                  className="font-mono font-bold leading-tight"
                  style={{ fontSize: `${Math.max(9, Math.min(22, Math.sqrt(area) / 6))}px` }}
                >
                  {t.item.ticker}
                </span>
                <span
                  className="font-medium leading-tight mt-0.5"
                  style={{ fontSize: `${Math.max(8, Math.min(14, Math.sqrt(area) / 10))}px` }}
                >
                  {t.item.change_pct >= 0 ? "+" : ""}{t.item.change_pct}%
                </span>
                <span
                  className="opacity-80 leading-tight mt-0.5 font-semibold"
                  style={{ fontSize: `${Math.max(8, Math.min(13, Math.sqrt(area) / 12))}px` }}
                >
                  {t.item.weight}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
