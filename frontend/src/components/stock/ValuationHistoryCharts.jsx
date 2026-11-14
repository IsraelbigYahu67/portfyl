import { useCallback, useEffect, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { X } from "lucide-react";
import { formatShortDate } from "../../lib/format";
import { AXIS_TICK_STYLE, CATEGORICAL, GRID_STROKE } from "../../lib/chartTheme";
import SegmentedControl from "../ui/SegmentedControl";
import { useT } from "../../i18n/I18nProvider";

export const VALUATION_MULTIPLES = [
  { key: "trailing_pe", label: "P/E", fmt: (v) => v?.toFixed(1) },
  { key: "ev_ebitda", label: "EV/EBITDA", fmt: (v) => v?.toFixed(1) },
  { key: "price_to_sales", label: "P/S", fmt: (v) => v?.toFixed(2) },
  { key: "price_to_cash_flow", label: "P/FCF", fmt: (v) => v?.toFixed(1) },
  { key: "price_to_book", label: "P/B", fmt: (v) => v?.toFixed(2) },
];

// How long the open chart stays mounted after it has been closed / replaced,
// so the close and "pour" animations (index.css, `.vh-*`) can finish first.
const CLOSE_MS = 460;
const POUR_MS = 650;

function BucketDateTooltip({ active, payload, valueFormatter }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm shadow-lg">
      <div className="text-muted">
        {formatShortDate(point.bucket, { year: "numeric", month: "short", day: "numeric" })}
      </div>
      {valueFormatter && point.value != null && (
        <div className="font-semibold text-ink mt-0.5">{valueFormatter(point.value)}</div>
      )}
    </div>
  );
}

// Trailing multiples can blow way past a normal 2-digit range (a company
// freshly back to profitability can print a P/E in the thousands), so the
// axis needs to size itself to the actual label text instead of a constant
// that only works for the common case.
function estimateAxisWidth(labels, charWidth = 6.5, minWidth = 28, padding = 10) {
  const maxLen = labels.reduce((max, s) => Math.max(max, String(s).length), 0);
  return Math.max(minWidth, maxLen * charWidth + padding);
}

/** P/E when it has data, otherwise the first multiple that does (null if none). */
function defaultOpenKey(points) {
  const hasData = (m) => points.some((p) => p[m.key] != null);
  return (VALUATION_MULTIPLES.find(hasData) ?? null)?.key ?? null;
}

function buildSeries(multiple, points) {
  return points
    .map((p) => ({ bucket: p.bucket, value: p[multiple.key] }))
    .filter((p) => p.value != null);
}

/** One small tile of the strip: label, current value and a sparkline. */
function ValuationTile({ multiple, points, onSelect }) {
  const t = useT();
  const series = buildSeries(multiple, points);

  if (!series.length) {
    return (
      <div className="card !p-3 h-full">
        <div className="text-xs text-muted uppercase tracking-wider">{multiple.label}</div>
        <div className="text-sm text-muted mt-2">{t("No data")}</div>
      </div>
    );
  }

  const currentValue = points[points.length - 1]?.[multiple.key];
  const sortedValues = series.map((p) => p.value).slice().sort((a, b) => a - b);
  const minValue = sortedValues[0];
  const maxValue = sortedValues[sortedValues.length - 1];
  // A few evenly-spaced labels between the extremes, in addition to the exact
  // min/max -- plain tickCount would round to "nice" numbers that can fall
  // outside the true min/max and hide the very values the chart exists to show.
  const yTicks =
    maxValue > minValue
      ? [minValue, minValue + (maxValue - minValue) / 3, minValue + (2 * (maxValue - minValue)) / 3, maxValue]
      : [minValue];
  const yAxisWidth = estimateAxisWidth(yTicks.map((v) => multiple.fmt(v)));

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={t("Open {multiple} valuation history chart", { multiple: multiple.label })}
      className="card card-interactive !p-3 cursor-pointer h-full"
      onClick={(e) => onSelect(multiple.key, e.currentTarget)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(multiple.key, e.currentTarget);
        }
      }}
      title={t("Click to open the chart")}
    >
      <div className="text-xs text-muted uppercase tracking-wider">{multiple.label}</div>
      <div className="text-xl font-bold tabular-nums text-ink">
        {currentValue != null ? multiple.fmt(currentValue) : "—"}
      </div>
      <div className="h-16 mt-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 6, right: 2, left: 0, bottom: 6 }}>
            <YAxis
              domain={[minValue, maxValue]}
              ticks={yTicks}
              interval={0}
              tick={AXIS_TICK_STYLE}
              width={yAxisWidth}
              tickFormatter={(v) => multiple.fmt(v)}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={CATEGORICAL[0]}
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
              isAnimationActive={false}
              dot={false}
              activeDot={false}
            />
            {/* No <Tooltip> here on purpose: values can only be inspected on the opened chart. */}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** The big chart that opens above the strip, as wide as the content column. */
function ValuationBigChart({ multiple, points, onClose, className = "", style }) {
  const t = useT();
  const [logScale, setLogScale] = useState(false);
  const series = buildSeries(multiple, points);
  if (!series.length) return null;

  const currentValue = points[points.length - 1]?.[multiple.key];
  const sortedValues = series.map((p) => p.value).slice().sort((a, b) => a - b);
  const minValue = sortedValues[0];
  const maxValue = sortedValues[sortedValues.length - 1];
  const yAxisWidth = estimateAxisWidth([minValue, maxValue].map((v) => multiple.fmt(v)), 7, 44, 14);

  // A log axis cannot plot zero or negative multiples (e.g. a negative P/E),
  // so those points are left out while it is on.
  const positiveSeries = series.filter((p) => p.value > 0);
  const hiddenByLog = series.length - positiveSeries.length;
  const logAvailable = positiveSeries.length > 1;
  const useLog = logScale && logAvailable;
  const shownSeries = useLog ? positiveSeries : series;
  const logMin = Math.min(...positiveSeries.map((p) => p.value));
  const logMax = Math.max(...positiveSeries.map((p) => p.value));
  const logTicks =
    logMax > logMin ? [0, 1, 2, 3, 4].map((i) => logMin * (logMax / logMin) ** (i / 4)) : [logMin];

  return (
    <div className={`card !p-4 sm:!p-5 ${className}`} style={style}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h4 className="section-title">
            {t("{multiple} Valuation History", { multiple: multiple.label })}
          </h4>
          <div className="text-3xl font-bold tabular-nums text-ink mt-0.5">
            {currentValue != null ? multiple.fmt(currentValue) : "—"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {useLog && hiddenByLog > 0 && (
            <span className="text-xs text-muted">
              {hiddenByLog === 1
                ? t("{count} non-positive value hidden", { count: 1 })
                : t("{count} non-positive values hidden", { count: hiddenByLog })}
            </span>
          )}
          <SegmentedControl
            aria-label={t("Valuation chart scale")}
            value={useLog ? "log" : "linear"}
            onChange={(v) => setLogScale(v === "log")}
            options={[
              { value: "linear", label: t("Linear") },
              {
                value: "log",
                label: t("Log"),
                disabled: !logAvailable,
                title: logAvailable ? undefined : t("Not enough positive values for a log scale"),
              },
            ]}
          />
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label={t("Close chart")}
              className="inline-flex items-center justify-center h-9 w-9 rounded-full text-muted hover:text-ink hover:bg-surface-hover transition-colors"
            >
              <X size={20} />
            </button>
          )}
        </div>
      </div>
      <div className="h-[260px] sm:h-[340px] mt-3">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={shownSeries} margin={{ top: 10, right: 16, left: 4, bottom: 6 }}>
            <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="bucket"
              tick={AXIS_TICK_STYLE}
              tickFormatter={(b) => formatShortDate(b, { month: "short", year: "numeric" })}
              minTickGap={40}
            />
            <YAxis
              scale={useLog ? "log" : "auto"}
              domain={useLog ? [logMin, logMax] : [minValue, maxValue]}
              ticks={useLog ? logTicks : undefined}
              interval={useLog ? 0 : "preserveEnd"}
              allowDataOverflow={useLog}
              tick={AXIS_TICK_STYLE}
              width={yAxisWidth}
              tickFormatter={(v) => multiple.fmt(v)}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={CATEGORICAL[0]}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill={CATEGORICAL[0]}
              fillOpacity={0.08}
              isAnimationActive={false}
              dot={false}
            />
            <Tooltip content={<BucketDateTooltip valueFormatter={multiple.fmt} />} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/**
 * The five multiples as a strip of sparkline tiles. Clicking a tile opens its
 * chart in a panel above the strip, as wide as the content column (not the
 * whole screen). The opened tile collapses out of the strip and the others
 * flow wider; opening another one pours the new chart over the old one and
 * the old tile slides back into the strip. Motion lives in `index.css` (`.vh-*`).
 */
export default function ValuationHistoryCharts({ points }) {
  // The page opens with the P/E chart already showing (or, if P/E has no data
  // for this ticker, the first multiple that does). It starts open, so there is
  // no opening animation on first render.
  const [initialKey] = useState(() => defaultOpenKey(points));
  const [selectedKey, setSelectedKey] = useState(initialKey); // tile hidden from the strip
  const [panelKey, setPanelKey] = useState(initialKey); // chart mounted in the panel
  const [outgoingKey, setOutgoingKey] = useState(null); // chart being poured over
  const [open, setOpen] = useState(initialKey != null); // panel expanded
  const [pour, setPour] = useState({ n: 0, x: 50 });
  const panelRef = useRef(null);
  const timers = useRef({});

  const clearTimer = (name) => {
    clearTimeout(timers.current[name]);
    delete timers.current[name];
  };
  useEffect(() => () => Object.keys(timers.current).forEach((n) => clearTimeout(timers.current[n])), []);

  const handleSelect = useCallback(
    (key, tileEl) => {
      if (key === selectedKey) return;
      // Where the pour starts: the clicked tile's centre, as a % of the panel width.
      let x = 50;
      const panelRect = panelRef.current?.getBoundingClientRect();
      const tileRect = tileEl?.getBoundingClientRect();
      if (panelRect?.width && tileRect) {
        x = Math.min(100, Math.max(0, ((tileRect.left + tileRect.width / 2 - panelRect.left) / panelRect.width) * 100));
      }
      clearTimer("close");
      clearTimer("pour");
      if (open && panelKey && panelKey !== key) {
        setOutgoingKey(panelKey);
        timers.current.pour = setTimeout(() => setOutgoingKey(null), POUR_MS);
      }
      setPour((p) => ({ n: p.n + 1, x }));
      setSelectedKey(key);
      setPanelKey(key);
      if (!open) {
        // Let the collapsed panel paint once so its height can ease open.
        requestAnimationFrame(() => requestAnimationFrame(() => setOpen(true)));
      }
    },
    [selectedKey, open, panelKey],
  );

  const handleClose = useCallback(() => {
    clearTimer("pour");
    setOutgoingKey(null);
    setOpen(false);
    setSelectedKey(null);
    clearTimer("close");
    timers.current.close = setTimeout(() => setPanelKey(null), CLOSE_MS);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, handleClose]);

  const multipleOf = (key) => VALUATION_MULTIPLES.find((m) => m.key === key);
  const current = panelKey ? multipleOf(panelKey) : null;
  const outgoing = outgoingKey ? multipleOf(outgoingKey) : null;
  // After a range change the open multiple may have no points left; then its
  // tile stays in the strip (it only shows "No data") and the panel is empty.
  const shownKey = selectedKey && points.some((p) => p[selectedKey] != null) ? selectedKey : null;
  const panelOpen = open && shownKey != null;

  return (
    <div>
      <div ref={panelRef} className="vh-panel" data-open={panelOpen ? "true" : "false"} aria-hidden={!panelOpen}>
        <div className="min-h-0 vh-panel-inner">
          {/* pb gives the shadow of the card room and the gap to the strip; it collapses with the panel */}
          <div className="pb-4 grid" data-testid="valuation-chart-panel">
            {outgoing && (
              <ValuationBigChart
                key={`out-${outgoing.key}`}
                multiple={outgoing}
                points={points}
                className="vh-leave pointer-events-none"
                style={{ gridArea: "1 / 1" }}
              />
            )}
            {current && (
              <ValuationBigChart
                key={`${current.key}-${pour.n}`}
                multiple={current}
                points={points}
                onClose={handleClose}
                className={outgoing ? "vh-pour" : ""}
                style={{ gridArea: "1 / 1", "--pour-x": `${pour.x}%` }}
              />
            )}
          </div>
        </div>
      </div>

      <div className="vh-strip" data-testid="valuation-strip">
        {VALUATION_MULTIPLES.map((m) => (
          <div
            key={m.key}
            className="vh-item"
            data-selected={shownKey === m.key ? "true" : "false"}
            data-testid={`valuation-tile-${m.key}`}
            inert={shownKey === m.key ? "" : undefined}
          >
            <ValuationTile multiple={m} points={points} onSelect={handleSelect} />
          </div>
        ))}
      </div>
    </div>
  );
}
