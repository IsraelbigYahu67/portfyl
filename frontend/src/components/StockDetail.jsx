import { useCallback, useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Customized, Legend,
  Line, Pie, PieChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  ArrowDown, ArrowDownRight, ArrowUpRight, Building2, ChevronDown, ChevronUp,
  ExternalLink, Eye, EyeOff, Flame, Globe, Info, Landmark, RotateCcw, Settings2,
  TrendingDown, TrendingUp, Users,
} from "lucide-react";
import {
  fetchHistory, fetchStockDividendGrowth, fetchShibuiInsiders,
  fetchShibuiEarningsRecap, fetchShibuiValuationHistory, fetchPoliticianTrades,
} from "../api";
import { columnChanges, ttmUnderlayRect } from "../lib/chartChanges";
import { formatShortDate, formatTableDate, humanizeCode } from "../lib/format";
import { buildWeeklyBuckets, assignTransactionsToWeeks, jitterOffsetPx } from "../lib/insiderWeekly";
import { buildPriceAxis } from "../lib/chartPriceAxis";
import useStockReportConfig, { ALL_SECTIONS } from "../hooks/useStockReportConfig";
import {
  CATEGORICAL, NEUTRAL_COLOR, GAIN_COLOR, LOSS_COLOR, AXIS_TICK, AXIS_TICK_STYLE, GRID_STROKE, TOOLTIP_STYLE,
} from "../lib/chartTheme";
import { withSliceCorners } from "../lib/pieCorners";
import { PieTouchScrub } from "../hooks/usePieTouchScrub";
import { buildFinancialAxis, formatFinancialTick, financialAxisWidth } from "../lib/chartFinancialAxis";
import { Badge, KpiBox } from "./ui";
import SegmentedControl from "./ui/SegmentedControl";
import ValuationHistoryCharts from "./stock/ValuationHistoryCharts";
import Pagination from "./ui/Pagination";
import ShinyText from "./reactbits/ShinyText";
import SpotlightCard from "./reactbits/SpotlightCard";
import { InfoIcon } from "./MetricCard";
import { TickerLink } from "./TickerLink";
import { msg, useT } from "../i18n/I18nProvider";

// Financial metric names the API sends in English (backend/routers/market.py),
// translated where a chart shows them.
export const METRIC_NAMES = [
  msg("Revenue"), msg("Cost of Revenue"), msg("Gross Profit"), msg("Operating Income"), msg("EBITDA"),
  msg("Net Income"), msg("Diluted EPS"), msg("Free Cash Flow"), msg("CapEx"), msg("Total Debt"),
  msg("Cash & Equivalents"), msg("Shares Outstanding"),
];

const TTM_COLOR = CATEGORICAL[3];
const TTM_SIDE_REVEAL = 2;
const TTM_RADIUS = 4;
const PERIOD_LABEL_MIN_GAP = 3;
// Chart text never goes below the 12px floor (DESIGN.md). Dense charts shorten
// or thin their period labels instead of shrinking them.
const PERIOD_LABEL_FONT_SIZE = 12;
// Fill colors for the financial bar charts (theme series, never hex).
const BAR_ACTUAL_COLOR = CATEGORICAL[0];
const BAR_ESTIMATE_COLOR = CATEGORICAL[5];
const PERIOD_AXIS_RESERVED_WIDTH = 52;

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

// `useStockDetail().openStock(ticker)` was originally a modal-opener. It now
// just navigates to the full-page overview — kept as a hook for backwards
// compatibility with existing call sites in Allocation/Dividends/Heatmap.
export { useStockDetail } from "../hooks/useStockDetail";

// Convenience: a link that navigates to the stock overview page. Drops in
// anywhere a bare ticker is rendered. Using `<Link>` (not a button) so
// middle-click / Cmd-click open a new tab.
export { TickerLink } from "./TickerLink";

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtCompact(v, currencySymbol = "$", decimals = 2) {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}${currencySymbol}${(abs / 1e12).toFixed(decimals)}T`;
  if (abs >= 1e9) return `${sign}${currencySymbol}${(abs / 1e9).toFixed(decimals)}B`;
  if (abs >= 1e6) return `${sign}${currencySymbol}${(abs / 1e6).toFixed(decimals)}M`;
  if (abs >= 1e3) return `${sign}${currencySymbol}${(abs / 1e3).toFixed(decimals)}K`;
  return `${sign}${currencySymbol}${abs.toFixed(decimals)}`;
}

function fmtMoney(v, currencySymbol = "$") {
  if (v == null) return "—";
  return `${currencySymbol}${v.toLocaleString("en-US", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function fmtPct(v, digits = 2) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function fmtRatio(v, digits = 2) {
  if (v == null) return "—";
  return v.toFixed(digits);
}

// Each row of the ratios table — value (focal stock), sector (median across
// constituents), and direction-aware Δ colouring. lowerIsBetter is true for
// valuation multiples (cheaper = greener) and leverage; false for quality
// metrics (margins, ROE, ROA, yield, liquidity).
const RATIO_ROWS = [
  { key: "forward_pe", label: msg("Forward P/E"), lowerIsBetter: true, yearKey: "forward_pe_fy1_year", labelYearSuffix: true,
    tooltip: msg("Forward Price to Earnings. Like P/E, but the denominator is analysts' estimated EPS for a future fiscal year. Current share price ÷ estimated future EPS. Because earnings are usually expected to grow, forward P/E is typically lower than trailing P/E. Reliability drops the further out the projected year, since estimates get less accurate.") },
  { key: "peg", label: msg("PEG"), lowerIsBetter: true,
    tooltip: msg("Price/Earnings to Growth. P/E ÷ the expected annual earnings growth rate (in %). Contextualizes P/E by accounting for growth. Rule of thumb: ≈1 is fairly valued, below 1 may be undervalued relative to growth, above 1 may be overvalued. Only as good as the growth estimate plugged in.") },
  { key: "de", label: msg("D/E"), lowerIsBetter: true,
    tooltip: msg("Debt to Equity. Total debt ÷ shareholders' equity. Measures financial leverage — how much the company is funded by borrowing versus owners' capital. A high D/E indicates heavy reliance on debt. Nuance: aggressive buybacks shrink the equity base and can inflate D/E, overstating true financial risk for cash-rich firms.") },
  { key: "current_ratio", label: msg("Current Ratio"), lowerIsBetter: false,
    tooltip: msg("Current assets ÷ current liabilities. A short-term liquidity test: can the company cover obligations due within one year using assets convertible to cash within one year? Above 1.0 means current assets exceed current liabilities; higher indicates a more comfortable liquidity cushion.") },
  { key: "roe", label: msg("ROE"), pct: true, lowerIsBetter: false,
    tooltip: msg("Return on Equity. Net income ÷ shareholders' equity. Measures how efficiently the company generates profit from owners' capital. A very high ROE can be inflated by a small equity base (from buybacks) or by heavy leverage, so interpret it alongside ROIC.") },
  { key: "roic", label: msg("ROIC"), pct: true, lowerIsBetter: false,
    tooltip: msg("Return on Invested Capital. NOPAT (Net Operating Profit After Tax) ÷ invested capital, where invested capital = total debt + equity − cash (the total capital actually deployed in the business). Measures how efficiently the company generates profit from all capital invested, regardless of how it's financed. Generally considered the highest-quality profitability metric because — unlike ROE — it is not distorted by leverage or buybacks. The key test: ROIC should exceed the company's cost of capital (WACC); if it does, the business is creating value.") },
  { key: "gross_margin", label: msg("Gross Margin"), pct: true, lowerIsBetter: false,
    tooltip: msg("(Revenue − cost of goods sold) ÷ revenue, as a %. The share of each sales dollar left after the direct costs of producing the product/service. High gross margin indicates strong pricing power or a low-cost product (typical of software).") },
  { key: "operating_margin", label: msg("Operating Margin"), pct: true, lowerIsBetter: false,
    tooltip: msg("Operating income ÷ revenue, as a %. Profit remaining after both COGS and operating expenses (R&D, sales, admin), but before interest and taxes. Reflects the profitability of core operations.") },
  { key: "net_margin", label: msg("Net Margin"), pct: true, lowerIsBetter: false,
    tooltip: msg("Net income ÷ revenue, as a %. The “bottom line” — the share of each sales dollar that becomes profit after all costs: operating expenses, interest, and taxes. A net margin very close to the operating margin can signal large non-operating gains or a very low tax burden.") },
  { key: "div_yield", label: msg("Div Yield"), pct: true, lowerIsBetter: false,
    tooltip: msg("Dividend Yield. Annual dividend per share ÷ share price, as a %. The cash return you receive in dividends relative to the stock's price. A low yield is typical of a growth company that reinvests profits rather than paying them out; a high yield suits income-focused stocks (though a very high yield can also signal risk).") },
  { key: "payout_ratio", label: msg("Payout Ratio"), pct: true, lowerIsBetter: true,
    tooltip: msg("Dividends paid ÷ net income, as a %. The share of profits returned to shareholders as dividends. A low ratio means the company retains most earnings to fund growth or buybacks (leaving room to sustain or raise the dividend); a high ratio means most profit is paid out, which can be harder to sustain.") },
  { key: "fcf_margin", label: msg("FCF Margin"), pct: true, lowerIsBetter: false,
    tooltip: msg("Free cash flow ÷ revenue, as a %. How much of every sales dollar ends up as real cash after capital expenditure. Compare it with net margin: a FCF margin at or above net margin means profits are backed by cash.") },
  { key: "fcf_yield", label: msg("FCF Yield"), pct: true, lowerIsBetter: false,
    tooltip: msg("Free cash flow ÷ market cap, as a %. The cash return the business generates relative to its price, before any of it is paid out — the inverse of P/FCF. A broader measure of shareholder capacity than the dividend yield alone.") },
  { key: "net_debt_ebitda", label: msg("Net Debt/EBITDA"), lowerIsBetter: true,
    tooltip: msg("(Total debt − cash) ÷ EBITDA. How many years of operating profit it would take to repay net debt. Below 0 means net cash; under ~2 is comfortable, above ~4 is heavy. Unlike D/E it is not distorted by buybacks shrinking equity.") },
];

// The tiles are shown in rows of three, each row answering one question.
const RATIO_GROUPS = [
  { title: msg("Valuation"), keys: ["forward_pe", "peg"], moreMultiples: true },
  { title: msg("Margins"), keys: ["gross_margin", "operating_margin", "net_margin"] },
  { title: msg("Returns & cash conversion"), keys: ["roe", "roic", "fcf_margin"] },
  { title: msg("Balance sheet"), keys: ["de", "net_debt_ebitda", "current_ratio"] },
  { title: msg("Shareholder payout"), keys: ["div_yield", "payout_ratio", "fcf_yield"] },
].map((g) => ({ ...g, rows: g.keys.map((k) => RATIO_ROWS.find((r) => r.key === k)) }));

function currencySymbol(code) {
  if (code === "EUR") return "€";
  if (code === "GBP") return "£";
  if (code === "GBp" || code === "GBX") return "p";
  if (code === "CZK") return " Kč";
  return "$";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

// Valuation & Quality tile: the stock's own value big on the left (vertically
// centred), the sector median top-right and the deviation from it bottom-right.
// Percent metrics carry "%" on all three numbers; plain multiples carry none.
const RATIO_TONE = { gain: "text-gain", loss: "text-loss", muted: "text-muted" };

// One row of the shared two-column grid: everything before the decimal point is
// right-aligned and the rest left-aligned, so the points line up between rows.
function DecimalRow({ text, className = "", title }) {
  const dot = text.indexOf(".");
  const whole = dot < 0 ? text : text.slice(0, dot);
  const rest = dot < 0 ? "" : text.slice(dot);
  return (
    <>
      <span className={`text-right ${className}`} title={title}>{whole}</span>
      <span className={`text-left ${className}`} title={title}>{rest}</span>
    </>
  );
}

function RatioTile({ label, info, value, sectorVal, pct, lowerIsBetter, showSector }) {
  const t = useT();
  const unit = pct ? "%" : "";
  const digits = pct ? 1 : 2;
  const fmt = (v) => (v == null ? "—" : `${v.toFixed(digits)}${unit}`);
  const delta = value != null && sectorVal != null ? value - sectorVal : null;
  const favourable = delta == null ? null : lowerIsBetter ? delta < 0 : delta > 0;
  const tone = favourable == null ? "muted" : favourable ? "gain" : "loss";
  const deltaText =
    delta == null ? "—" : `${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(digits)}${unit}`;
  return (
    <SpotlightCard className="card pop-tile !bg-surface-card-elevated flex flex-col gap-1 min-w-0 !p-3">
      <span className="eyebrow flex items-center gap-1.5">
        {label}
        <InfoIcon info={info} />
      </span>
      <div className="flex items-center gap-[18px]">
        <span className="financial-data font-display font-bold tracking-tight text-2xl">
          {fmt(value)}
        </span>
        {showSector && (
          <div className="grid grid-cols-[auto_auto] shrink-0 leading-tight text-sm font-semibold tabular-nums">
            <DecimalRow text={fmt(sectorVal)} className="text-muted" title={t("Sector median")} />
            <DecimalRow text={deltaText} className={RATIO_TONE[tone]} title={t("Deviation from sector median")} />
          </div>
        )}
      </div>
    </SpotlightCard>
  );
}

// Fills the empty slot of the Valuation row: the multiples removed from the
// tiles live in the Valuation History chart, so this tile points there and
// scrolls to it on click.
const VALUATION_HISTORY_ID = "valuation-history";

function MoreMultiplesTile() {
  const t = useT();
  const goToChart = () => {
    const target = document.getElementById(VALUATION_HISTORY_ID);
    if (!target) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  };
  return (
    <button
      type="button"
      onClick={goToChart}
      className="card pop-tile !bg-surface-card-elevated flex flex-col gap-1 min-w-0 !p-3 text-left cursor-pointer"
    >
      <span className="eyebrow">{t("More multiples")}</span>
      <span className="h-8 inline-flex items-center gap-1.5 text-base font-semibold text-brand">
        {t("Show chart")} <ArrowDown size={16} aria-hidden="true" />
      </span>
    </button>
  );
}

function useElementWidth(fallbackWidth = 360) {
  const [element, setElement] = useState(null);
  const [width, setWidth] = useState(fallbackWidth);
  const ref = useCallback((node) => setElement(node), []);

  useEffect(() => {
    if (!element) return undefined;

    const updateWidth = () => {
      const nextWidth = element.getBoundingClientRect().width;
      if (nextWidth > 0) setWidth(nextWidth);
    };

    updateWidth();
    if (typeof ResizeObserver === "undefined") return undefined;

    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  return [ref, width];
}

// Period axis for the financials bar charts. The font is always 12px. When the
// full labels do not fit horizontally the axis first switches to short labels
// (years as '17, quarters as Q1'24), then shows only every (interval+1)-th one.
export function financialPeriodAxisLayout(labels, containerWidth, isQuarterly = false) {
  const count = labels?.length || 0;
  const base = { fontSize: PERIOD_LABEL_FONT_SIZE, angle: 0, interval: 0, short: false };
  if (!count) return base;

  const plotWidth = Math.max(1, containerWidth - PERIOD_AXIS_RESERVED_WIDTH);
  const slotWidth = Math.max(1, plotWidth / count);
  // 0.72em is intentionally conservative for tabular digits in the UI fonts.
  const widthOf = (texts) =>
    Math.max(...texts.map((text) => String(text ?? "").length), 1) * PERIOD_LABEL_FONT_SIZE * 0.72;

  if (widthOf(labels) + PERIOD_LABEL_MIN_GAP <= slotWidth) return base;

  const shortWidth = widthOf(labels.map((label) => shortPeriodLabel(label))) + PERIOD_LABEL_MIN_GAP;
  const interval = shortWidth <= slotWidth ? 0 : Math.ceil(shortWidth / slotWidth) - 1;
  return { ...base, interval, short: true };
}

// "2024" -> "'24", "Q1 '24" -> "Q1'24", "2025E" -> "'25E".
export function shortPeriodLabel(label) {
  const text = String(label ?? "");
  const year = /^(\d{4})(\D*)$/.exec(text);
  if (year) return `'${year[1].slice(2)}${year[2]}`;
  const quarter = /^(Q[1-4])\s*'?(\d{2}|\d{4})(\D*)$/.exec(text);
  if (quarter) return `${quarter[1]}'${quarter[2].slice(-2)}${quarter[3]}`;
  return text;
}

// Height the x-axis needs so the longest rotated change label (e.g. "+1234%")
// is drawn whole instead of being clipped at the bottom of the chart.
function changeAxisHeight(changes, { decimals, angle, showChange }) {
  if (!showChange) return 24;
  const longest = Math.max(
    0,
    ...changes.filter((c) => c != null).map((c) => fmtPct(c, decimals).length),
  );
  const textWidth = longest * PERIOD_LABEL_FONT_SIZE * 0.65;
  const drop = textWidth * Math.sin((Math.abs(angle) * Math.PI) / 180);
  return Math.max(66, Math.ceil(28 + drop + 8));
}

// Two-line x-axis tick for the financials bar charts: period label on top,
// vs-previous-column % change (see columnChanges) beneath it. Rendering the
// change inside the tick keeps it centred under its column at any chart
// width. Both lines are 12px; the change line is dropped (its value stays in
// the bar tooltip) whenever it could not be drawn at that size, and ticks
// skipped by `interval` render nothing.
function ChangeTick({
  x,
  y,
  payload,
  index,
  changes,
  fontSize = PERIOD_LABEL_FONT_SIZE,
  changeFontSize = PERIOD_LABEL_FONT_SIZE,
  changeDecimals = 1,
  changeAngle = -45,
  showChange = true,
  short = false,
  interval = 0,
}) {
  const position = payload?.index ?? index ?? 0;
  if (position % (interval + 1) !== 0) return null;
  const change = changes?.[position] ?? null;
  const periodY = 10;
  const changeY = 28;
  const label = short ? shortPeriodLabel(payload.value) : payload.value;
  return (
    <g transform={`translate(${x},${y})`}>
      <text y={periodY} textAnchor="middle" fill={AXIS_TICK_STYLE.fill} fontSize={fontSize}>
        {label}
      </text>
      {showChange && changeFontSize >= PERIOD_LABEL_FONT_SIZE && change != null && (
        <text
          y={changeY}
          textAnchor="end"
          transform={`rotate(${changeAngle}, 0, ${changeY})`}
          fill={change >= 0 ? GAIN_COLOR : LOSS_COLOR}
          fontSize={changeFontSize}
          fontWeight={700}
        >
          {fmtPct(change, changeDecimals)}
        </text>
      )}
    </g>
  );
}

// Rounded TTM backplate drawn underneath the latest actual bar. Its two-pixel
// shoulders stay visible even when TTM is lower, while the actual bar remains
// intact on top and naturally hides the shared centre of the underlay.
function TtmUnderlay({ formattedGraphicalItems, yAxisMap, ttm }) {
  if (ttm == null) return null;
  const rects = formattedGraphicalItems?.[0]?.props?.data;
  const yScale = yAxisMap && Object.values(yAxisMap)[0]?.scale;
  if (!rects?.length || !yScale) return null;
  const target = rects.find((r) => r?.payload?.hasTtmOverlay);
  if (!target || target.x == null || target.width == null) return null;
  const underlay = ttmUnderlayRect(yScale, ttm);
  if (!underlay) return null;
  return (
    // Decoration only — must not swallow hover events meant for the bar
    // underneath (the tooltip would otherwise never fire on this column).
    <g pointerEvents="none">
      <rect
        x={target.x - TTM_SIDE_REVEAL}
        y={underlay.y}
        width={target.width + TTM_SIDE_REVEAL * 2}
        height={underlay.height}
        rx={TTM_RADIUS}
        ry={TTM_RADIUS}
        fill={TTM_COLOR}
      />
    </g>
  );
}

export function MetricBarChart({ metric, currencyCode, period = "annual", isCount = false, ttm = null }) {
  const t = useT();
  const cs = currencySymbol(currencyCode);
  const { name, years, values, yoy, cagr } = metric;
  const isQuarterly = period === "quarterly";
  const [chartRef, chartWidth] = useElementWidth();

  if (!years?.length) {
    return (
      <div className="bg-surface rounded-lg p-4 flex flex-col h-full">
        <h3 className="mb-1 section-title">{name ? t(name) : null}</h3>
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          {t("No data")}
        </div>
      </div>
    );
  }

  const isPerShare = name.includes("EPS");
  // Counts (e.g. Shares Outstanding) are plain quantities, not money, and carry
  // no positive/negative sentiment: format without a currency symbol and use a
  // single neutral colour.
  const fmtVal = (v) =>
    v == null
      ? "—"
      : isCount
        ? fmtCompact(v, "")
        : isPerShare
          ? `${cs}${v.toFixed(2)}`
          : fmtCompact(v, cs);
  const changeColor = (x) =>
    isCount || x == null ? "text-muted" : x >= 0 ? "text-gain" : "text-loss";
  const data = years.map((y, i) => ({
    year: y,
    value: values[i],
    yoy: yoy?.[i] ?? null,
  }));
  // TTM doesn't get its own column — a rounded purple underlay shares the last
  // full-year column and remains visible at its sides (annual view only).
  const showTtmOverlay = ttm != null && !isQuarterly && !isCount && data.length > 0;
  const rows = data;
  // CapEx is reported as a negative outflow, so a plain signed diff reads
  // "more spend" as a decrease. Track its magnitude instead — growing spend
  // should show as an increase, not get inverted by the sign.
  const useAbsGrowth = name === "CapEx";
  // Change vs the previous column (YoY annual / QoQ quarterly), shown as a
  // second x-axis line. Quarterly charts keep this for every quarter.
  const changes = columnChanges(rows, { useAbs: useAbsGrowth });
  const rowsWithChange = rows.map((r, i) => ({
    ...r,
    change: changes[i],
    hasTtmOverlay: showTtmOverlay && i === rows.length - 1,
  }));
  const periodAxis = financialPeriodAxisLayout(rows.map((row) => row.year), chartWidth, isQuarterly);
  const changeAngle = rows.length > 12 ? -65 : rows.length > 7 ? -55 : -45;
  // Quarterly history is often longer than six periods. Keep its second line
  // visible; the adaptive tick layout makes room without dropping periods.
  const showChangeLine = isQuarterly || rows.length <= 10;
  // Round, evenly spaced y ticks that also cover the TTM overlay (it is not a
  // bar, so recharts would not widen the domain for it on its own).
  const yAxis = buildFinancialAxis([
    ...rows.map((r) => r.value),
    ...(showTtmOverlay ? [ttm] : []),
  ]);
  const yTickLabel = (v) => formatFinancialTick(v, { perShare: isPerShare });
  const yAxisWidth = financialAxisWidth(yAxis.ticks.map(yTickLabel));

  const headlineChange = isQuarterly
    ? changes[changes.length - 1]
    : yoy && yoy.length
      ? yoy[yoy.length - 1]
      : null;
  const headlineChangeLabel = isQuarterly ? t("QoQ") : t("YoY");

  return (
    <div className="bg-surface rounded-lg p-4 flex flex-col">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="section-title">{name ? t(name) : null}</h3>
        <div className="flex flex-col items-end text-xs gap-0.5">
          <span className="text-muted">
            CAGR{" "}
            <span className={changeColor(cagr)}>
              {cagr == null ? "—" : fmtPct(cagr, 1)}
            </span>
          </span>
          <span className="text-muted">
            {headlineChangeLabel}{" "}
            <span className={changeColor(headlineChange)}>
              {headlineChange == null ? "—" : fmtPct(headlineChange, 1)}
            </span>
          </span>
        </div>
      </div>
      <div className="text-xl font-bold tabular-nums">{fmtVal(values[values.length - 1])}</div>
      <div
        ref={chartRef}
        className="mt-2"
        style={{ height: 180 }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rowsWithChange} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
            <XAxis
              dataKey="year"
              tick={
                <ChangeTick
                  changes={changes}
                  fontSize={periodAxis.fontSize}
                  changeDecimals={rows.length > 7 ? 0 : 1}
                  changeAngle={changeAngle}
                  showChange={showChangeLine}
                  short={periodAxis.short}
                  interval={periodAxis.interval}
                />
              }
              tickLine={false}
              axisLine={{ stroke: GRID_STROKE }}
              interval={0}
              minTickGap={PERIOD_LABEL_MIN_GAP}
              height={changeAxisHeight(changes, { decimals: rows.length > 7 ? 0 : 1, angle: changeAngle, showChange: showChangeLine })}
            />
            <YAxis
              tick={AXIS_TICK_STYLE}
              tickFormatter={yTickLabel}
              tickLine={false}
              axisLine={false}
              width={yAxisWidth}
              domain={yAxis.domain}
              ticks={yAxis.ticks}
              interval={0}
            />
            <Tooltip
              cursor={{ fill: "rgba(0,0,0,0.04)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload;
                return (
                  <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm shadow-lg">
                    <div className="text-muted">{row.year}</div>
                    <div className="font-semibold text-ink">{fmtVal(row.value)}</div>
                    {row.yoy != null && (
                      <div className={changeColor(row.yoy)}>
                        {t("YoY")} {fmtPct(row.yoy, 2)}
                      </div>
                    )}
                    {isQuarterly && row.change != null && (
                      <div className={changeColor(row.change)}>
                        {t("QoQ")} {fmtPct(row.change, 2)}
                      </div>
                    )}
                    {row.hasTtmOverlay && (
                      <div style={{ color: TTM_COLOR }}>TTM {fmtVal(ttm)}</div>
                    )}
                  </div>
                );
              }}
            />
            {showTtmOverlay && (
              <Customized
                component={(cp) => <TtmUnderlay {...cp} ttm={ttm} />}
              />
            )}
            <Bar dataKey="value" radius={[7, 7, 0, 0]}>
              {rows.map((d, i) => (
                <Cell key={i} fill={d.value < 0 ? LOSS_COLOR : BAR_ACTUAL_COLOR} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// Consensus score (1 = strong buy ... 5 = strong sell) -> Badge tone.
function ratingTone(score) {
  if (score == null) return "neutral";
  if (score <= 2.5) return "gain";
  if (score <= 3.5) return "warn";
  return "loss";
}

function RatingPill({ children, tone = "neutral" }) {
  return <Badge tone={tone}>{children}</Badge>;
}

// Inset track + rounded fill; `color` is a CSS color from the theme tokens.
function AnalystBar({ label, count, total, color }) {
  const t = useT();
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-24 text-muted">{t(label)}</span>
      <div
        className="flex-1 rounded-full h-2.5 overflow-hidden"
        style={{ background: "var(--bg-subtle, var(--surface-hover))", boxShadow: "var(--clay-inset-sm, none)" }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="tabular-nums text-muted w-6 text-right font-medium">{count}</span>
    </div>
  );
}

function SectionCustomizer({ config, toggle, moveUp, moveDown, reset, isVisible }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-base rounded-lg border border-surface-border text-muted hover:text-ink hover:border-brand transition-colors"
        title={t("Customize report sections")}
      >
        <Settings2 size={14} />
        {t("Customize")}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-72 z-50 bg-surface-card border border-surface-border rounded-xl shadow-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-surface-border">
              <span className="text-sm font-semibold text-muted uppercase tracking-wider">{t("Report Sections")}</span>
              <button
                type="button"
                onClick={reset}
                className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink transition-colors"
              >
                <RotateCcw size={10} /> {t("Reset")}
              </button>
            </div>
            <ul className="py-1 max-h-80 overflow-y-auto">
              {config.order.map((id, idx) => {
                const section = ALL_SECTIONS.find((s) => s.id === id);
                if (!section) return null;
                const visible = isVisible(id);
                return (
                  <li
                    key={id}
                    className="flex items-center gap-2 px-3 py-1.5 hover:bg-surface-hover transition-colors"
                  >
                    <button
                      type="button"
                      onClick={() => toggle(id)}
                      className={`shrink-0 ${visible ? "text-brand" : "text-muted"}`}
                      title={visible ? t("Hide section") : t("Show section")}
                    >
                      {visible ? <Eye size={14} /> : <EyeOff size={14} />}
                    </button>
                    <span className={`flex-1 text-base ${visible ? "text-ink" : "text-muted"}`}>
                      {t(section.label)}
                    </span>
                    <div className="flex items-center gap-0.5">
                      <button
                        type="button"
                        onClick={() => moveUp(id)}
                        disabled={idx === 0}
                        aria-label={t("Move {section} up", { section: t(section.label) })}
                        className="text-muted hover:text-ink disabled:opacity-20 transition-colors p-0.5"
                      >
                        <ChevronUp size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveDown(id)}
                        disabled={idx === config.order.length - 1}
                        aria-label={t("Move {section} down", { section: t(section.label) })}
                        className="text-muted hover:text-ink disabled:opacity-20 transition-colors p-0.5"
                      >
                        <ChevronDown size={12} />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

export function DividendGrowthSection({ ticker, currency = "USD" }) {
  const t = useT();
  const { data, isLoading } = useQuery({
    queryKey: ["dividend-growth", ticker],
    queryFn: () => fetchStockDividendGrowth(ticker),
    staleTime: 5 * 60 * 1000,
    enabled: !!ticker,
  });

  // Only real payments: zero-amount rows would stretch the x-axis back to years
  // before the first dividend and leave an empty chart for non-payers.
  const payments = (data?.payments || []).filter((p) => Number(p.amount) > 0);
  if (isLoading || !data || !payments.length) return null;

  const lastExDate = payments[payments.length - 1]?.ex_date;
  const oneYearAgo = new Date();
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
  if (!lastExDate || new Date(lastExDate) < oneYearAgo) return null;

  const sym = currencySymbol(currency);
  const tiles = [
    { label: t("Growth streak"), value: data.streak_years > 0 ? t("{years} yrs", { years: data.streak_years }) : "—" },
    { label: t("{years}yr CAGR", { years: data.cagr_years_used || 5 }), value: data.cagr_pct != null ? `${data.cagr_pct.toFixed(1)}%` : "—" },
    { label: t("YoY"), value: data.yoy_pct != null ? `${data.yoy_pct.toFixed(1)}%` : "—" },
  ];

  return (
    <section className="space-y-3">
      <h3 className="section-title">{t("Dividend history")}</h3>
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((tile) => (
          <KpiBox key={tile.label} size="sm" label={tile.label} value={tile.value} />
        ))}
      </div>
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={payments} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="ex_date" tick={AXIS_TICK_STYLE} tickFormatter={(d) => String(d).slice(0, 7)} minTickGap={24} />
            <YAxis tick={AXIS_TICK_STYLE} width={52} tickFormatter={(v) => `${sym}${v}`} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.03)" }}
              contentStyle={{ background: "var(--surface-card-elevated)", border: "1px solid var(--hairline)", borderRadius: 8, fontSize: 13 }}
              formatter={(v) => [`${sym}${v}`, t("Per share")]}
            />
            <Bar dataKey="amount" fill={GAIN_COLOR} radius={[7, 7, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

// Shared content shell: pure rendering, no fetching. Used by the
// standalone /stock/:ticker page.
export function StockOverview({
  data,
  headerTrailing = null,
  sectionIds = null,
  showHeader = true,
  showCustomizer = true,
  headerHeadingLevel = 2,
  ttmLoading = false,
}) {
  const t = useT();
  const [period, setPeriod] = useState("annual");
  const reportConfig = useStockReportConfig();

  const cs = currencySymbol(data.currency);
  const ratios = data.ratios || {};
  const sector = data.sector_avg || {};
  const analyst = data.analyst || {};
  const finAnnual = data.financials || {};
  const finQuarterly = data.financials_quarterly || {};
  const fin = period === "quarterly" ? finQuarterly : finAnnual;
  const ttm = data.ttm || {};
  const periodsCount = fin?.revenue?.years?.length || 0;
  const hasQuarterly = (finQuarterly?.revenue?.years?.length || 0) > 0;
  const estimates = data.analyst_estimates || {};
  const estimatesQ = data.analyst_estimates_quarterly || {};
  const mergedRevenue = useMemo(
    () => buildMergedSeries(finAnnual.revenue, estimates.revenue, "annual"),
    [finAnnual.revenue, estimates.revenue],
  );
  const mergedEps = useMemo(
    () => buildMergedSeries(finAnnual.eps, estimates.eps, "annual"),
    [finAnnual.eps, estimates.eps],
  );
  const mergedRevenueQ = useMemo(
    () => buildMergedSeries(finQuarterly.revenue, estimatesQ.revenue, "quarterly"),
    [finQuarterly.revenue, estimatesQ.revenue],
  );
  const mergedEpsQ = useMemo(
    () => buildMergedSeries(finQuarterly.eps, estimatesQ.eps, "quarterly"),
    [finQuarterly.eps, estimatesQ.eps],
  );

  const priceChange = data.change_percent;
  const priceUp = priceChange != null && priceChange >= 0;

  const sections = {
    quickStats: (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiBox size="sm" label={t("Market Cap")} value={fmtCompact(data.market_cap, cs)} />
        <KpiBox size="sm" label={t("Revenue (TTM)")} loading={ttmLoading} value={fmtCompact(ttm.revenue, cs)} />
        <KpiBox size="sm" label={t("Free Cash Flow (TTM)")} loading={ttmLoading} value={fmtCompact(ttm.fcf, cs)} />
        <KpiBox size="sm" label={t("Div Yield")} value={ratios.div_yield != null ? `${ratios.div_yield.toFixed(2)}%` : "—"} />
      </div>
    ),

    dividendGrowth: <DividendGrowthSection ticker={data.ticker} currency={data.currency} />,

    financials: (
      <div>
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <h3 className="section-title">
            {period === "quarterly" ? t("Quarterly Financials") : t("Annual Financials")}
            {periodsCount > 0 && (
              <span className="ml-2 text-muted normal-case tracking-normal">
                · {period === "quarterly"
                  ? t("Quarters: {count}", { count: periodsCount })
                  : t("Years: {count}", { count: periodsCount })}
              </span>
            )}
          </h3>
          <SegmentedControl
            aria-label={t("Financials period")}
            value={period}
            onChange={setPeriod}
            options={[
              { value: "annual", label: t("Annual") },
              {
                value: "quarterly",
                label: t("Quarterly"),
                disabled: !hasQuarterly,
                title: hasQuarterly ? undefined : t("No quarterly data available"),
              },
            ]}
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <MergedMetricBarChart
            name="Revenue"
            data={period === "annual" ? mergedRevenue : mergedRevenueQ}
            currencyCode={data.currency}
            isPerShare={false}
            ttm={ttm.revenue}
          />
          <MetricBarChart metric={fin.operating_income || {}} currencyCode={data.currency} period={period} ttm={ttm.operating_income} />
          <MetricBarChart metric={fin.net_income || {}} currencyCode={data.currency} period={period} ttm={ttm.net_income} />
          <MergedMetricBarChart
            name="Diluted EPS"
            data={period === "annual" ? mergedEps : mergedEpsQ}
            currencyCode={data.currency}
            isPerShare={true}
            ttm={ttm.eps}
          />
          <MetricBarChart metric={fin.fcf || {}} currencyCode={data.currency} period={period} ttm={ttm.fcf} />
          <MetricBarChart metric={fin.capex || {}} currencyCode={data.currency} period={period} ttm={ttm.capex} />
          <MetricBarChart metric={fin.debt || {}} currencyCode={data.currency} period={period} />
          <MetricBarChart metric={fin.cash || {}} currencyCode={data.currency} period={period} />
          <MetricBarChart metric={fin.shares_outstanding || {}} currencyCode={data.currency} period={period} isCount />
        </div>
      </div>
    ),

    ratiosAnalyst: (
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="bg-surface rounded-[var(--radius-card)] p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="section-title">
              {t("Valuation & Quality")}
            </h3>
            {sector.sample_size > 0 && (
              <span className="text-xs text-muted">
                {t("Sector = median of {count} {sector}", { count: sector.sample_size, sector: data.sector })}
              </span>
            )}
          </div>
          <div className="flex flex-col gap-4">
            {RATIO_GROUPS.map((group) => (
              <section key={group.title} aria-label={t(group.title)}>
                <h4 className="eyebrow mb-1.5">{t(group.title)}</h4>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {group.rows.map((r) => {
                    const year = r.yearKey ? ratios[r.yearKey] : null;
                    const label =
                      r.labelYearSuffix && year != null
                        ? `${t(r.label)} (${year})`
                        : t(r.label);
                    const direction = r.lowerIsBetter ? t("Lower is better.") : t("Higher is better.");
                    return (
                      <RatioTile
                        key={r.key}
                        label={label}
                        info={r.tooltip ? { title: label, what: t(r.tooltip), note: direction } : { title: label, what: direction }}
                        value={ratios[r.key]}
                        sectorVal={r.noSector ? null : sector[r.key]}
                        pct={!!r.pct}
                        lowerIsBetter={r.lowerIsBetter}
                        showSector={!r.noSector}
                      />
                    );
                  })}
                  {group.moreMultiples && <MoreMultiplesTile />}
                </div>
              </section>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-surface rounded-[var(--radius-card)] p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="section-title">
                {t("Analyst Rating")}
              </h3>
              {analyst.rating && (
                <RatingPill tone={ratingTone(analyst.score)}>{humanizeCode(analyst.rating)}</RatingPill>
              )}
            </div>
            {analyst.total > 0 ? (
              <>
                <div className="flex items-baseline gap-3 mb-3">
                  <span className="text-4xl font-bold tabular-nums">
                    {analyst.score != null ? analyst.score.toFixed(2) : "—"}
                  </span>
                  <span className="text-sm text-muted">
                    {t("consensus · analysts: {count}", { count: analyst.total })}
                  </span>
                </div>
                <div className="space-y-1.5">
                  <AnalystBar label={msg("Strong Buy")} count={analyst.strong_buy || 0} total={analyst.total} color={GAIN_COLOR} />
                  <AnalystBar label={msg("Buy")} count={analyst.buy || 0} total={analyst.total} color={GAIN_COLOR} />
                  <AnalystBar label={msg("Hold")} count={analyst.hold || 0} total={analyst.total} color="var(--chart-3)" />
                  <AnalystBar label={msg("Sell")} count={analyst.sell || 0} total={analyst.total} color={LOSS_COLOR} />
                  <AnalystBar label={msg("Strong Sell")} count={analyst.strong_sell || 0} total={analyst.total} color={LOSS_COLOR} />
                </div>
              </>
            ) : (
              <div className="text-muted text-sm">{t("No analyst coverage available.")}</div>
            )}
          </div>

          <div className="bg-surface rounded-[var(--radius-card)] p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="section-title">
                {t("Price Targets")}
              </h3>
              {analyst.target_mean != null && analyst.upside != null && (
                <span className={`text-sm font-medium ${analyst.upside >= 0 ? "text-gain" : "text-loss"}`}>
                  {t("{pct} avg upside", { pct: fmtPct(analyst.upside) })}
                </span>
              )}
            </div>
            {analyst.target_mean != null && analyst.target_low != null && analyst.target_high != null && data.price ? (
              <AnalystForecastCone
                low={analyst.target_low}
                high={analyst.target_high}
                mean={analyst.target_mean}
                current={data.price}
                cs={cs}
              />
            ) : (
              <div className="text-muted text-sm">{t("No price targets available.")}</div>
            )}
          </div>

        </div>
      </div>
    ),

    insiderVolume: (
      <InsiderVolumeChart
        ticker={data.ticker}
        transactions={data.insider_transactions}
        currencyCode={data.currency}
      />
    ),

    insiderTx: (
      <InsiderTransactionsWithSec
        ticker={data.ticker}
        transactions={data.insider_transactions}
        currencyCode={data.currency}
        currentPrice={data.price}
      />
    ),

    ownership: (
      <OwnershipSection ownership={data.ownership} currencyCode={data.currency} />
    ),

    earningsRecap: <EarningsRecapSection ticker={data.ticker} currencyCode={data.currency} />,

    valuationHistory: <ValuationHistorySection ticker={data.ticker} />,

    politicalTrades: (
      <PoliticalTradesSection ticker={data.ticker} currencyCode={data.currency} currentPrice={data.price} />
    ),
  };

  const renderedSectionIds = sectionIds || reportConfig.config.order;
  const HeaderHeading = `h${headerHeadingLevel}`;

  return (
    <>
      {/* ----- Header (always visible) ----- */}
      {showHeader && <div className="flex flex-col gap-4 px-4 py-4 border-b border-surface-border sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 flex-wrap">
            <HeaderHeading className="text-3xl font-bold font-mono"><ShinyText text={data.ticker} /></HeaderHeading>
            <span className="text-muted text-lg truncate">{data.name}</span>
            {data.exchange && (
              <span className="text-xs text-muted uppercase tracking-wider">{data.exchange}</span>
            )}
            {data.fundamentals_source && (
              <Badge
                size="sm"
                tone={data.fundamentals_source === "shibui" ? "brand" : "warn"}
                title={
                  data.fundamentals_source === "shibui"
                    ? t("Financials and ratios below are sourced from Shibui Finance (analyst rating/estimates are always from yfinance — Shibui doesn't cover those).")
                    : t("Shibui doesn't cover this ticker, or is unavailable right now (e.g. rate-limited) — financials and ratios below fell back to yfinance.")
                }
                className="uppercase tracking-wider cursor-help"
              >
                <Info size={10} />
                {data.fundamentals_source === "shibui" ? "Shibui" : t("yfinance fallback")}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1 text-sm text-muted flex-wrap">
            {data.sector && <span className="flex items-center gap-1"><Building2 size={11} />{data.sector}</span>}
            {data.industry && <span>· {data.industry}</span>}
            {data.country && <span className="flex items-center gap-1">· <Globe size={11} />{data.country}</span>}
            {data.website && (
              <a
                href={data.website}
                target="_blank"
                rel="noreferrer"
                className="hover:text-brand inline-flex items-center gap-0.5"
              >
                · <ExternalLink size={10} />{data.website.replace(/^https?:\/\//, "")}
              </a>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <div className="text-left sm:text-right">
            <div className="text-3xl font-bold tabular-nums">
              {data.price != null ? `${cs}${data.price.toFixed(2)}` : "—"}
            </div>
            {priceChange != null && (
              <div className={`text-base font-medium flex items-center justify-start gap-1 sm:justify-end ${priceUp ? "text-gain" : "text-loss"}`}>
                {priceUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                {data.change != null && `${data.change >= 0 ? "+" : ""}${data.change.toFixed(2)} `}
                ({fmtPct(priceChange)})
              </div>
            )}
          </div>
          {showCustomizer && <SectionCustomizer {...reportConfig} />}
          {headerTrailing}
        </div>
      </div>}

      <div className="p-4 space-y-6 sm:p-6">
        {renderedSectionIds.map((id) => {
          if (!reportConfig.isVisible(id)) return null;
          const content = sections[id];
          if (!content) return null;
          return <div key={id}>{content}</div>;
        })}
      </div>
    </>
  );
}

// 1-year forecast cone — replicates the TradingView/TipRanks look. Two data
// points (today, +1y); the fan is a single range-Area (dataKey returns
// [min,max]) so Recharts auto-domains tightly to the price band instead of
// stretching to 0. A locked Y-domain lets the overlay pills align with
// real chart coordinates.
const CONE_CHART_HEIGHT = 224; // matches h-56
const CONE_MARGIN_TOP = 12;
const CONE_MARGIN_BOTTOM = 20;
const CONE_XAXIS_HEIGHT = 30; // Recharts default XAxis height
// Right gutter that holds the target pills (each <= ~100px) beside the y axis.
const CONE_MARGIN_RIGHT = 104;
const EDGE_PILL_MIN_GAP = 22;

function AnalystForecastCone({ low, high, mean, current, cs }) {
  const t = useT();
  if (low == null || high == null || mean == null || current == null) return null;

  // Split the fan around the current price so the upper half renders green
  // (potential upside) and the lower half red (potential downside).
  const data = [
    {
      label: "Now",
      current,
      avg: current,
      upper: [current, current],
      lower: [current, current],
    },
    {
      label: "1Y",
      current,
      avg: mean,
      upper: [Math.max(low, current), Math.max(high, current)],
      lower: [Math.min(low, current), Math.min(high, current)],
    },
  ];

  const upsideAvg = ((mean - current) / current) * 100;
  const upsideMax = ((high - current) / current) * 100;
  const upsideMin = ((low - current) / current) * 100;

  // Each target is toned by direction vs. current: above gain, below loss.
  const toneFor = (v) => (v > current ? "gain" : v < current ? "loss" : "neutral");
  const avgStroke = mean > current ? GAIN_COLOR : mean < current ? LOSS_COLOR : NEUTRAL_COLOR;

  const lo = Math.min(low, current, mean);
  const hi = Math.max(high, current, mean);
  const padding = (hi - lo) * 0.08 || hi * 0.05 || 1;
  const yMin = lo - padding;
  const yMax = hi + padding;

  const pct = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

  return (
    <div className="relative">
      <div style={{ height: CONE_CHART_HEIGHT }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: CONE_MARGIN_TOP, right: CONE_MARGIN_RIGHT, bottom: CONE_MARGIN_BOTTOM, left: 4 }}
          >
            <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
            <XAxis
              dataKey="label"
              height={CONE_XAXIS_HEIGHT}
              tickFormatter={(value) => (value === "Now" ? t("Now") : t("1Y"))}
              tick={AXIS_TICK_STYLE}
              tickLine={false}
              axisLine={{ stroke: GRID_STROKE }}
            />
            <YAxis
              domain={[yMin, yMax]}
              allowDataOverflow={true}
              orientation="right"
              tick={AXIS_TICK_STYLE}
              tickFormatter={(v) => `${cs}${v.toFixed(0)}`}
              tickLine={false}
              axisLine={false}
              width={50}
            />
            {/* Two range Areas: upper (above current) green, lower (below
                current) red. dataKey returns [min, max] so Recharts renders
                a proper band rather than stacking from a zero baseline. */}
            <Area
              type="linear"
              dataKey="lower"
              stroke="none"
              fill={`color-mix(in srgb, ${LOSS_COLOR} 18%, transparent)`}
              isAnimationActive={false}
            />
            <Area
              type="linear"
              dataKey="upper"
              stroke="none"
              fill={`color-mix(in srgb, ${GAIN_COLOR} 18%, transparent)`}
              isAnimationActive={false}
            />
            {/* Mean-target trajectory — green if mean > current, red if below */}
            <Line
              type="linear"
              dataKey="avg"
              stroke={avgStroke}
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
            />
            {/* Current price — flat line across both points */}
            <Line
              type="linear"
              dataKey="current"
              stroke={CATEGORICAL[0]}
              strokeWidth={2}
              dot={{ fill: CATEGORICAL[0], r: 4 }}
              isAnimationActive={false}
            />
            <Tooltip
              cursor={{ stroke: GRID_STROKE, strokeDasharray: "2 4" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0]?.payload;
                if (!row) return null;
                return (
                  <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm shadow-lg space-y-0.5">
                    <div className="text-muted mb-1">{row.label === "Now" ? t("Now") : t("1Y")}</div>
                    {row.label === "Now" ? (
                      <div className="text-ink">{t("Current {price}", { price: `${cs}${current.toFixed(2)}` })}</div>
                    ) : (
                      <>
                        <div className="text-gain">{t("Max {price}", { price: `${cs}${high.toFixed(2)}` })} <span className="text-muted">({pct(upsideMax)})</span></div>
                        <div className="text-gain">{t("Avg {price}", { price: `${cs}${mean.toFixed(2)}` })} <span className="text-muted">({pct(upsideAvg)})</span></div>
                        <div className="text-loss">{t("Min {price}", { price: `${cs}${low.toFixed(2)}` })} <span className="text-muted">({pct(upsideMin)})</span></div>
                      </>
                    )}
                  </div>
                );
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <RightEdgePills
        items={[
          { key: "max", value: high, tone: toneFor(high), label: t("Max"), detail: pct(upsideMax) },
          { key: "avg", value: mean, tone: toneFor(mean), label: t("Avg"), detail: pct(upsideAvg) },
          { key: "now", value: current, tone: "brand", label: t("Now") },
          { key: "min", value: low, tone: toneFor(low), label: t("Min"), detail: pct(upsideMin) },
        ]}
        yMin={yMin}
        yMax={yMax}
        cs={cs}
      />
      <div className="absolute left-1/2 -translate-x-1/2 bottom-0 px-3 py-1 rounded-full bg-surface border border-surface-border text-xs uppercase tracking-wider text-muted">
        1Y Forecast
      </div>
    </div>
  );
}

// Spread pill centres vertically so neighbours are >= minGap px apart and all
// stay inside [top + minGap/2, bottom - minGap/2]. Input order is by y (stable
// for ties); a stack that hits the bottom edge is pushed back up, not off the
// plot. When there is not enough room for every pill the first ones are clamped
// to the top edge (they overlap rather than leave the plot).
export function layoutEdgePills(items, { top, bottom, minGap }) {
  const lo = top + minGap / 2;
  const hi = bottom - minGap / 2;
  const out = items
    .map((it, i) => ({ ...it, _i: i }))
    .sort((a, b) => a.y - b.y || a._i - b._i)
    .map(({ _i, ...it }) => ({ ...it, y: Math.min(Math.max(it.y, lo), hi) }));
  for (let i = 1; i < out.length; i++) {
    if (out[i].y - out[i - 1].y < minGap) out[i].y = out[i - 1].y + minGap;
  }
  for (let i = out.length - 1; i >= 0; i--) {
    const ceiling = i === out.length - 1 ? hi : out[i + 1].y - minGap;
    if (out[i].y > ceiling) out[i].y = ceiling;
  }
  return out.map((it) => ({ ...it, y: Math.max(it.y, lo) }));
}

function RightEdgePills({ items, yMin, yMax, cs }) {
  // Plot area = total height − top margin − (bottom margin + XAxis height).
  // Pills are positioned proportionally on that band, then spread so they
  // never overlap each other or leave the band.
  const plotTop = CONE_MARGIN_TOP;
  const plotBottom = CONE_MARGIN_BOTTOM + CONE_XAXIS_HEIGHT;
  const usable = CONE_CHART_HEIGHT - plotTop - plotBottom;
  const yFor = (v) => plotTop + ((yMax - v) / (yMax - yMin)) * usable;

  const placed = layoutEdgePills(
    items.map((it) => ({ key: it.key, y: yFor(it.value) })),
    { top: plotTop, bottom: plotTop + usable, minGap: EDGE_PILL_MIN_GAP },
  );
  const byKey = new Map(items.map((it) => [it.key, it]));

  return (
    <div className="absolute inset-0 pointer-events-none">
      {placed.map(({ key, y }) => {
        const it = byKey.get(key);
        return (
          <div
            key={key}
            className="absolute right-1"
            style={{ top: `${y}px`, transform: "translateY(-50%)" }}
          >
            <Badge
              tone={it.tone}
              size="sm"
              className="tabular-nums"
              title={it.detail ? `${it.label} ${cs}${it.value.toFixed(2)} (${it.detail})` : undefined}
            >
              {it.label} {cs}{it.value.toFixed(2)}
            </Badge>
          </div>
        );
      })}
    </div>
  );
}

// Parse a period label ("2024" or "Q1 '24") into a sortable numeric key.
// Annual labels collapse to the year; quarterly labels are mapped to
// year + Q/4 so Q1 '24 → 2024.25, Q4 '24 → 2025.0 etc.
function parsePeriodKey(label) {
  if (label == null) return null;
  const s = String(label);
  const annual = /^(\d{4})$/.exec(s);
  if (annual) return Number(annual[1]);
  const q = /^Q([1-4])\s*'(\d{2})$/.exec(s);
  if (q) {
    const yy = Number(q[2]);
    const year = yy < 70 ? 2000 + yy : 1900 + yy;
    return year + Number(q[1]) / 4;
  }
  return null;
}

// Merge a historical-financial metric block (years/values) with a forward
// analyst-estimates list. Estimate rows whose period already appears in the
// historical bars are dropped — the actual is preferred. Returns unified
// bar data sorted ascending by period.
function buildMergedSeries(metric, estimateRows, mode = "annual") {
  const out = [];
  const hist = metric || {};
  const histLabels = hist.years || [];
  const histValues = hist.values || [];
  const histYoy = hist.yoy || [];
  histLabels.forEach((label, i) => {
    const sortKey = parsePeriodKey(label);
    if (sortKey == null) return;
    out.push({
      label: String(label),
      sortKey,
      year: Math.floor(sortKey),
      value: histValues[i],
      isEstimate: false,
      low: null,
      high: null,
      analysts: 0,
      growth: histYoy[i] ?? null,
    });
  });
  const usedKeys = new Set(out.map((r) => r.sortKey));
  (estimateRows || []).forEach((e) => {
    let sortKey;
    let label;
    if (mode === "quarterly") {
      if (e.year == null || e.quarter == null) return;
      sortKey = e.year + e.quarter / 4;
      label = `Q${e.quarter} '${String(e.year % 100).padStart(2, "0")}E`;
    } else {
      if (e.year == null) return;
      sortKey = e.year;
      label = `${e.year}E`;
    }
    if (usedKeys.has(sortKey)) return;
    usedKeys.add(sortKey);
    out.push({
      label,
      sortKey,
      year: e.year,
      value: e.avg,
      isEstimate: true,
      low: e.low,
      high: e.high,
      analysts: e.analysts,
      growth: e.growth,
    });
  });
  out.sort((a, b) => a.sortKey - b.sortKey);
  return out;
}

export function MergedMetricBarChart({ name, data, currencyCode, isPerShare, ttm = null }) {
  const t = useT();
  const cs = currencySymbol(currencyCode);
  const isQuarterly = data?.some((d) => /^Q[1-4]/.test(d.label));
  const [chartRef, chartWidth] = useElementWidth();
  if (!data?.length) {
    return (
      <div className="bg-surface rounded-lg p-4 flex flex-col h-full">
        <h3 className="mb-1 section-title">{t(name)}</h3>
        <div className="flex-1 flex items-center justify-center text-muted text-sm">{t("No data")}</div>
      </div>
    );
  }

  // CAGR across actual history only — mixing in forecasts would inflate it.
  const actuals = data.filter((d) => !d.isEstimate);
  const cagr = (() => {
    if (actuals.length < 2) return null;
    const a = actuals[0].value;
    const b = actuals[actuals.length - 1].value;
    if (a == null || b == null || a <= 0 || b <= 0) return null;
    const n = actuals.length - 1;
    return ((b / a) ** (1 / n) - 1) * 100;
  })();
  // Headline reflects the latest *actual* (last reported FY / quarter), not
  // the furthest-out forecast — users want to see what the company really
  // earned, with the estimate bars providing the forward view.
  const lastActual = actuals[actuals.length - 1];
  // TTM doesn't get its own column — a rounded purple underlay shares the latest
  // actual column (annual view only), so estimates stay next to real fiscal years.
  const showTtm = ttm != null && !isQuarterly && actuals.length > 0;
  const lastActualIdx = data.reduce((k, d, i) => (d.isEstimate ? k : i), -1);
  const rows = data;
  // Change vs the previous column (YoY annual / QoQ quarterly, estimates vs
  // their prior period), shown as a second x-axis line for every period.
  const changes = columnChanges(rows);
  const rowsWithChange = rows.map((r, i) => ({
    ...r,
    change: changes[i],
    hasTtmOverlay: showTtm && i === lastActualIdx,
  }));
  // Do not discard QoQ just because a quarterly series is dense. The x-axis
  // reduces the set of rendered labels where necessary, while each displayed
  // period keeps the same two-line value/change treatment as annual charts.
  const showChangeLine = isQuarterly || rows.length <= 10;
  // Derive Revenue/EPS growth from the rendered actual bars. This keeps the
  // headline and the value beneath its year in lockstep even when the API's
  // optional historical YoY field is absent.
  const lastActualGrowth = lastActualIdx >= 0 ? changes[lastActualIdx] : null;
  const headlineGrowthLabel = isQuarterly ? t("QoQ") : t("YoY");
  // Forecast labels are wider than plain years, so include the actual rendered
  // labels in the same width-aware sizing used by the historical cards.
  const periodAxis = financialPeriodAxisLayout(rows.map((row) => row.label), chartWidth, isQuarterly);
  const changeAngle = rows.length > 12 ? -65 : rows.length > 7 ? -55 : -45;
  // Round, evenly spaced y ticks that also cover the TTM overlay.
  const yAxis = buildFinancialAxis([
    ...rows.map((r) => r.value),
    ...(showTtm ? [ttm] : []),
  ]);
  const yTickLabel = (v) => formatFinancialTick(v, { perShare: isPerShare });
  const yAxisWidth = financialAxisWidth(yAxis.ticks.map(yTickLabel));

  return (
    <div className="bg-surface rounded-lg p-4 flex flex-col">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="section-title">{t(name)}</h3>
        <div className="flex flex-col items-end text-xs gap-0.5">
          <span className="text-muted">
            CAGR{" "}
            <span className={cagr == null ? "text-muted" : cagr >= 0 ? "text-gain" : "text-loss"}>
              {cagr == null ? "—" : fmtPct(cagr, 1)}
            </span>
          </span>
          <span className="text-muted">
            {headlineGrowthLabel}{" "}
            <span className={lastActualGrowth == null ? "text-muted" : lastActualGrowth >= 0 ? "text-gain" : "text-loss"}>
              {lastActualGrowth == null ? "—" : fmtPct(lastActualGrowth, 1)}
            </span>
          </span>
        </div>
      </div>
      <div className="flex items-baseline gap-2">
        <div className="text-xl font-bold tabular-nums">
          {lastActual?.value == null
            ? "—"
            : isPerShare
              ? `${cs}${lastActual.value.toFixed(2)}`
              : fmtCompact(lastActual.value, cs)}
        </div>
        {lastActual?.label && (
          <div className="text-xs text-muted">{lastActual.label}</div>
        )}
      </div>
      <div
        ref={chartRef}
        className="mt-2"
        style={{ height: 180 }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rowsWithChange} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
            <XAxis
              dataKey="label"
              tick={
                <ChangeTick
                  changes={changes}
                  fontSize={periodAxis.fontSize}
                  changeDecimals={rows.length > 7 ? 0 : 1}
                  changeAngle={changeAngle}
                  showChange={showChangeLine}
                  short={periodAxis.short}
                  interval={periodAxis.interval}
                />
              }
              tickLine={false}
              axisLine={{ stroke: GRID_STROKE }}
              interval={0}
              minTickGap={PERIOD_LABEL_MIN_GAP}
              height={changeAxisHeight(changes, { decimals: rows.length > 7 ? 0 : 1, angle: changeAngle, showChange: showChangeLine })}
            />
            <YAxis
              tick={AXIS_TICK_STYLE}
              tickFormatter={yTickLabel}
              tickLine={false}
              axisLine={false}
              width={yAxisWidth}
              domain={yAxis.domain}
              ticks={yAxis.ticks}
              interval={0}
            />
            <Tooltip
              cursor={{ fill: "rgba(0,0,0,0.04)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload;
                return (
                  <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm shadow-lg">
                    <div className="text-muted">
                      {row.label} · {row.isEstimate ? t("estimate") : t("actual")}
                    </div>
                    <div className="font-semibold text-ink">
                      {row.value == null
                        ? "—"
                        : isPerShare
                          ? `${cs}${row.value.toFixed(2)}`
                          : fmtCompact(row.value, cs)}
                    </div>
                    {row.isEstimate && row.low != null && row.high != null && (
                      <div className="text-muted text-xs">
                        {t("Range {range}", {
                          range: isPerShare
                            ? `${cs}${row.low.toFixed(2)}–${cs}${row.high.toFixed(2)}`
                            : `${fmtCompact(row.low, cs)}–${fmtCompact(row.high, cs)}`,
                        })}
                      </div>
                    )}
                    {row.isEstimate && row.analysts > 0 && (
                      <div className="text-muted text-xs">{t("Analysts: {count}", { count: row.analysts })}</div>
                    )}
                    {row.growth != null && (
                      <div className={row.growth >= 0 ? "text-gain text-xs" : "text-loss text-xs"}>
                        {row.isEstimate ? t("Fcst growth") : t("YoY")} {fmtPct(row.growth, 2)}
                      </div>
                    )}
                    {isQuarterly && row.change != null && (
                      <div className={row.change >= 0 ? "text-gain text-xs" : "text-loss text-xs"}>
                        {t("QoQ")} {fmtPct(row.change, 2)}
                      </div>
                    )}
                    {row.hasTtmOverlay && (
                      <div style={{ color: TTM_COLOR }}>
                        TTM {isPerShare ? `${cs}${ttm.toFixed(2)}` : fmtCompact(ttm, cs)}
                      </div>
                    )}
                  </div>
                );
              }}
            />
            {showTtm && (
              <Customized
                component={(cp) => <TtmUnderlay {...cp} ttm={ttm} />}
              />
            )}
            <Bar dataKey="value" radius={[7, 7, 0, 0]}>
              {rows.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.value < 0 ? LOSS_COLOR : d.isEstimate ? BAR_ESTIMATE_COLOR : BAR_ACTUAL_COLOR}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-3 mt-2 text-xs text-muted">
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: BAR_ACTUAL_COLOR }} />{t("Actual")}</span>
        {showTtm && (
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: TTM_COLOR }} />TTM</span>
        )}
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: BAR_ESTIMATE_COLOR }} />{t("Estimate")}</span>
      </div>
    </div>
  );
}

function TargetRangeBar({ low, high, mean, median, current, cs }) {
  const t = useT();
  const span = high - low;
  if (span <= 0) return null;
  const pct = (v) => Math.max(0, Math.min(100, ((v - low) / span) * 100));
  const meanPct = pct(mean);
  const currentPct = pct(current);
  const medianPct = median != null ? pct(median) : null;
  return (
    <div>
      <div className="relative h-2 bg-surface-hover rounded-full">
        <div
          className="absolute top-0 h-2 rounded-full "
          style={{
            left: 0,
            right: 0,
            background: `linear-gradient(to right, ${mixToken(LOSS_COLOR, 30)}, ${mixToken("var(--chart-3)", 30)}, ${mixToken(GAIN_COLOR, 30)})`,
          }}
        />
        {medianPct != null && (
          <div
            className="absolute top-[-2px] h-3 w-0.5 rounded"
            style={{ left: `calc(${medianPct}% - 1px)`, backgroundColor: NEUTRAL_COLOR }}
            title={t("Median {price}", { price: `${cs}${median.toFixed(2)}` })}
          />
        )}
        <div
          className="absolute top-[-3px] h-4 w-0.5 bg-brand rounded"
          style={{ left: `calc(${meanPct}% - 1px)` }}
          title={t("Mean {price}", { price: `${cs}${mean.toFixed(2)}` })}
        />
        <div
          className="absolute top-[-4px] h-5 w-1 rounded"
          style={{ left: `calc(${currentPct}% - 2px)`, backgroundColor: "var(--ink)" }}
          title={t("Current {price}", { price: `${cs}${current.toFixed(2)}` })}
        />
      </div>
      <div className="flex items-center justify-between text-xs text-muted mt-2">
        <span>{t("Low {price}", { price: `${cs}${low.toFixed(2)}` })}</span>
        <span>{t("High {price}", { price: `${cs}${high.toFixed(2)}` })}</span>
      </div>
      <div className="flex items-center gap-3 text-xs text-muted mt-1">
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: "var(--ink)" }} />{t("Current")}</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 bg-brand rounded-full" />{t("Mean")}</span>
        {median != null && (
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: NEUTRAL_COLOR }} />{t("Median {price}", { price: `${cs}${median.toFixed(2)}` })}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ownership pie + insider transactions
// ---------------------------------------------------------------------------

// Distinct hues for the top-N institutional holders. "Other" + retail are
// rendered with muted greys so the named holders pop.
const OWNERSHIP_OTHER_COLOR = NEUTRAL_COLOR;
const OWNERSHIP_RETAIL_COLOR = "color-mix(in srgb, var(--ink) 55%, var(--surface-card))";
// Nested KPI tiles inside a card read as pressed wells (DESIGN.md section 4).
const KPI_WELL_CLASS = "!bg-surface-hover ![box-shadow:var(--clay-inset-sm)]";

function OwnershipSection({ ownership, currencyCode }) {
  const t = useT();
  if (!ownership) return null;
  const cs = currencySymbol(currencyCode);
  const holders = ownership.top_institutional_holders || [];
  const instPct = ownership.institutional_pct;
  const insiderPct = ownership.insider_pct;
  const shortPct = ownership.short_percent_float;

  if (!holders.length && instPct == null && insiderPct == null && shortPct == null) return null;

  // Build the pie slices. Each named institution carves its own slice out of
  // the total institutional ownership %; whatever's left of institutions
  // (beyond the top-N reported) is bundled into "Other institutions"; the
  // remainder goes to insiders + retail/float.
  const namedPctTotal = holders.reduce(
    (s, h) => s + (h.pct_out != null ? h.pct_out : 0),
    0,
  );
  const slices = [];
  holders.forEach((h, i) => {
    if (h.pct_out == null || h.pct_out <= 0) return;
    slices.push({
      key: `inst-${i}`,
      kind: "institution",
      name: h.name,
      pct: h.pct_out,
      shares: h.shares,
      value: h.value,
      date: h.date_reported,
      color: CATEGORICAL[i % CATEGORICAL.length],
    });
  });
  if (instPct != null) {
    const otherInst = Math.max(0, instPct - namedPctTotal);
    if (otherInst > 0.5) {
      slices.push({
        key: "inst-other",
        kind: "other",
        name: t("Other institutions"),
        pct: otherInst,
        color: OWNERSHIP_OTHER_COLOR,
      });
    }
  }
  if (insiderPct != null && insiderPct > 0) {
    slices.push({
      key: "insiders",
      kind: "insiders",
      name: t("Insiders"),
      pct: insiderPct,
      color: CATEGORICAL[6],
    });
  }
  const accountedPct = slices.reduce((s, x) => s + x.pct, 0);
  const retailPct = Math.max(0, 100 - accountedPct);
  if (retailPct > 0.5) {
    slices.push({
      key: "retail",
      kind: "retail",
      name: t("Retail / public float"),
      pct: retailPct,
      color: OWNERSHIP_RETAIL_COLOR,
    });
  }

  return (
    <div>
      <h3 className="mb-3 section-title">
        {t("Ownership Breakdown")}
      </h3>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="card !p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <KpiBox
              size="sm"
              className={KPI_WELL_CLASS}
              label={t("Institutions")}
              value={instPct != null ? `${instPct.toFixed(1)}%` : "—"}
            />
            <KpiBox
              size="sm"
              className={KPI_WELL_CLASS}
              label={t("Insiders")}
              value={insiderPct != null ? `${insiderPct.toFixed(1)}%` : "—"}
            />
            <KpiBox
              size="sm"
              className={KPI_WELL_CLASS}
              label={t("Top holders")}
              value={
                ownership.institutions_count != null
                  ? `${ownership.institutions_count}`
                  : "—"
              }
            />
            <KpiBox
              size="sm"
              className={KPI_WELL_CLASS}
              label={t("Short interest")}
              value={shortPct != null ? `${(shortPct * 100).toFixed(2)}%` : "—"}
            />
          </div>
          {slices.length > 0 ? (
            // Opt this donut alone into the slice pop (DESIGN.md §7); the rest
            // of the stock page keeps still.
            <div className="hover-pop-zone no-block-pop">
            <PieTouchScrub className="pie-pop h-72">
              {(tooltipProps) => (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={withSliceCorners(slices, { valueKey: "pct", inner: 60, outer: 110, corner: 9 })}
                    dataKey="pct"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={110}
                    paddingAngle={3}
                    cornerRadius={9}
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {slices.map((s) => (
                      <Cell key={s.key} fill={s.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    {...tooltipProps}
                    cursor={{ fill: "color-mix(in srgb, var(--ink) 5%, transparent)" }}
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const row = payload[0].payload;
                      return (
                        <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm shadow-lg max-w-xs">
                          <div className="font-semibold text-ink truncate">{row.name}</div>
                          <div className="text-muted tabular-nums">
                            {t("{pct}% of shares", { pct: row.pct.toFixed(2) })}
                          </div>
                          {row.shares != null && (
                            <div className="text-muted text-xs tabular-nums">
                              {t("{count} shares", { count: fmtCompact(row.shares, "") })}
                              {row.value != null && (
                                <> · {fmtCompact(row.value, cs)}</>
                              )}
                            </div>
                          )}
                          {row.date && (
                            <div className="text-muted text-xs mt-0.5">
                              {t("As of {date}", { date: row.date })}
                            </div>
                          )}
                        </div>
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              )}
            </PieTouchScrub>
            </div>
          ) : (
            <div className="h-72 flex items-center justify-center text-muted text-sm">
              {t("No ownership data available.")}
            </div>
          )}
        </div>

        <div className="card !p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="flex items-center gap-1.5 section-title">
              <Users size={12} />
              {t("Top Institutional Holders")}
            </h4>
            <span className="text-xs text-muted">{t("% of shares · value")}</span>
          </div>
          {holders.length === 0 ? (
            <div className="text-muted text-sm">{t("No institutional holders reported.")}</div>
          ) : (
            <ul className="space-y-1 max-h-80 overflow-y-auto pr-1">
              {holders.map((h, i) => (
                <li
                  key={`${h.name}-${i}`}
                  className="flex items-center gap-2 text-sm py-1 border-b border-surface-border last:border-0"
                >
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                    style={{ background: CATEGORICAL[i % CATEGORICAL.length] }}
                  />
                  <span className="flex-1 min-w-0 truncate text-ink" title={h.name}>
                    {h.name}
                  </span>
                  <span className="tabular-nums text-ink w-14 text-right">
                    {h.pct_out != null ? `${h.pct_out.toFixed(2)}%` : "—"}
                  </span>
                  <span className="tabular-nums text-muted w-20 text-right">
                    {h.value != null ? fmtCompact(h.value, cs) : "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shibui-backed sections: structured insider activity + cluster buys,
// earnings recap, historical valuation multiples, and (button-gated) political trades. Each fetches
// its own data independently (same pattern as DividendGrowthSection above)
// and renders nothing when Shibui doesn't cover the ticker, so these are
// silent no-ops for foreign/delisted/thinly-covered names.
// ---------------------------------------------------------------------------

const CHIP_TONE = { brand: "brand", warn: "warn", danger: "loss", neutral: "neutral" };

function Chip({ children, title, tone = "neutral" }) {
  return (
    <Badge size="sm" tone={CHIP_TONE[tone] ?? "neutral"} title={title} className="uppercase shrink-0">
      {children}
    </Badge>
  );
}

// Multi-select transaction-type filter, used by the insider table below. An empty `active` set means "no filter, show all" --
// clicking a chip while every type is showing isolates to just that one;
// further clicks add/remove types; selecting everything (or clicking "All")
// collapses back to the empty-set "show all" state.
export function toggleSetValue(active, value, totalCount) {
  if (active.size === 0) return new Set([value]);
  const next = new Set(active);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next.size === 0 || next.size === totalCount ? new Set() : next;
}

// Pill toggles: active = raised with brand text, inactive = pressed trough.
const FILTER_PILL =
  "text-xs font-bold uppercase tracking-wider px-3 py-1 max-md:min-h-[44px] rounded-full transition-colors";
const FILTER_PILL_ON = "bg-surface-card text-brand";
const FILTER_PILL_OFF = "bg-surface-hover text-muted hover:text-ink";

// Option labels and descriptions are English source text, translated here.
function TypeFilterChips({ options, active, onToggle, onReset, className = "" }) {
  const t = useT();
  if (!options || options.length <= 1) return null;
  const noFilter = active.size === 0;
  const pillStyle = (on) => ({ boxShadow: on ? "var(--clay-raise-sm)" : "var(--clay-inset-sm)" });
  return (
    <div className={`flex items-center gap-1.5 flex-wrap ${className}`}>
      <button
        type="button"
        onClick={onReset}
        aria-pressed={noFilter}
        style={pillStyle(noFilter)}
        className={`${FILTER_PILL} ${noFilter ? FILTER_PILL_ON : FILTER_PILL_OFF}`}
      >
        {t("All")}
      </button>
      {options.map((opt) => {
        const isOn = noFilter || active.has(opt.value);
        return (
          <button
            key={opt.value}
            type="button"
            title={opt.description ? t(opt.description) : undefined}
            aria-pressed={isOn}
            onClick={() => onToggle(opt.value)}
            style={pillStyle(isOn)}
            className={`${FILTER_PILL} ${isOn ? FILTER_PILL_ON : FILTER_PILL_OFF}`}
          >
            {t(opt.label)}
            <span className="ml-1 font-normal normal-case opacity-70">{opt.count}</span>
          </button>
        );
      })}
    </div>
  );
}

// Newest filing first; ISO dates sort lexicographically.
const YF_TYPE_META = {
  buy: { label: msg("Buy"), tone: "buy", description: msg("Insider purchased shares in the open market.") },
  sell: { label: msg("Sell"), tone: "sell", description: msg("Insider sold shares in the open market.") },
  other: {
    label: msg("Other"),
    tone: "neutral",
    description: msg("Grants, option exercises, gifts, and other non-market Form 4 transactions."),
  },
};

function isPoliticalTradeBuy(t) {
  const type = (t.transaction_type || "").toUpperCase();
  return type.includes("PURCHASE") || type === "BUY";
}

function daysBetween(earlier, later) {
  const d1 = new Date(earlier);
  const d2 = new Date(later);
  if (Number.isNaN(d1.getTime()) || Number.isNaN(d2.getTime())) return null;
  return Math.round((d2.getTime() - d1.getTime()) / 86400000);
}

// Custom ReferenceDot marker: circle for a plain stock trade, diamond for an
// option-flagged one (PLAN.md 1g-iii); color = buy/sell direction. Hover
// info uses a native SVG <title> (real OS tooltip on mouseover) rather than
// a custom-positioned tooltip, since recharts' own Tooltip doesn't attach to
// ReferenceDot annotations.
function TradeMarker({ cx, cy, fill, isOption, onClick, tooltip }) {
  if (cx == null || cy == null) return null;
  const common = { fill, stroke: "var(--surface-card)", strokeWidth: 1, onClick, style: { cursor: "pointer" } };
  if (isOption) {
    const r = 6;
    return (
      <polygon points={`${cx},${cy - r} ${cx + r},${cy} ${cx},${cy + r} ${cx - r},${cy}`} {...common}>
        <title>{tooltip}</title>
      </polygon>
    );
  }
  return (
    <circle cx={cx} cy={cy} r={5} {...common}>
      <title>{tooltip}</title>
    </circle>
  );
}

// "$ value" and "shares" aren't in the disclosed data -- STOCK Act only
// publishes an amount BAND, never an exact figure, and share count isn't
// published at all. Both are estimated here from the band midpoint and the
// stock's closing price on the trade date, and clearly marked with "~" so
// they never read as more precise than they are.
function formatTradeTooltip(trade, cs, t) {
  const name = trade.politician_canonical || trade.politician;
  const midValue = (Number(trade.amount_min) + Number(trade.amount_max)) / 2;
  const lines = [name, trade.transaction_date];

  if (Number.isFinite(midValue) && trade.tradePrice > 0) {
    const estShares = midValue / trade.tradePrice;
    lines.push(t("~{value} · ~{shares} sh", {
      value: `${cs}${Math.round(midValue).toLocaleString()}`,
      shares: Math.round(estShares).toLocaleString(),
    }));
    if (trade.isBuy && trade.currentPrice != null) {
      const pnlDollar = estShares * (trade.currentPrice - trade.tradePrice);
      const pnlPct = (trade.currentPrice / trade.tradePrice - 1) * 100;
      const sign = pnlDollar >= 0 ? "+" : "";
      lines.push(t("Unrealized: {amount} ({pct})", {
        amount: `${sign}${cs}${Math.round(pnlDollar).toLocaleString()}`,
        pct: `${sign}${pnlPct.toFixed(1)}%`,
      }));
    } else if (!trade.isBuy) {
      lines.push(t("Position sold — no unrealized P&L"));
    }
  }
  return lines.join("\n");
}

function PoliticalTradesChart({ ticker, trades, currencyCode, currentPrice, onSelect }) {
  const t = useT();
  const cs = currencySymbol(currencyCode);
  const { data: hist } = useQuery({
    queryKey: ["history", ticker, "1y"],
    queryFn: () => fetchHistory(ticker, "1y"),
    staleTime: 30 * 60 * 1000,
    enabled: false,
  });

  const points = hist?.data;
  if (!points?.length) return null;

  // Match each trade to the closing price on its date, falling back to the
  // nearest earlier trading day (STOCK Act dates are trading days, so this
  // should usually be an exact hit).
  const dots = trades
    .map((t) => {
      let y = null;
      for (const p of points) {
        if (p.date > t.transaction_date) break;
        y = p.close;
      }
      if (y == null) return null;
      return { ...t, x: t.transaction_date, y, tradePrice: y, currentPrice, isBuy: isPoliticalTradeBuy(t) };
    })
    .filter(Boolean);

  if (!dots.length) return null;

  return (
    <div className="card !p-4 mb-3">
      <h4 className="mb-2 section-title">
        {t("Trades on price chart")}
      </h4>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="date" tick={AXIS_TICK_STYLE} tickFormatter={(d) => String(d).slice(0, 7)} minTickGap={40} />
            <YAxis tick={AXIS_TICK_STYLE} width={52} domain={["auto", "auto"]} tickFormatter={(v) => `${cs}${v}`} />
            <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${cs}${v}`, "Close"]} />
            <Line type="monotone" dataKey="close" stroke={NEUTRAL_COLOR} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            {dots.map((d, i) => (
              <ReferenceDot
                key={i}
                x={d.x}
                y={d.y}
                isFront
                shape={(props) => (
                  <TradeMarker
                    {...props}
                    fill={d.isBuy ? GAIN_COLOR : LOSS_COLOR}
                    isOption={d.is_likely_option}
                    tooltip={formatTradeTooltip(d, cs, t)}
                    onClick={() => onSelect(d)}
                  />
                )}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted mt-2">
        {t("● stock trade · ◆ option-flagged trade · green = buy, red = sell — hover a marker for name/date/value/shares/unrealized P&L, click it (or a table row below) for full details.")}
      </p>
    </div>
  );
}

function TradeDetailCard({ trade, onClose }) {
  const t = useT();
  const isBuy = isPoliticalTradeBuy(trade);
  const reportLag = daysBetween(trade.transaction_date, trade.filed_date);

  return (
    <div className="card !p-4 mb-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-ink">
            {trade.politician_canonical || trade.politician}
          </div>
          <div className="text-sm text-muted mt-0.5">
            {trade.party} · {trade.chamber}
            {trade.state ? ` · ${trade.state}` : ""}
            {trade.state_district ? ` (${trade.state_district})` : ""}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("Close trade details")}
          className="text-muted hover:text-ink text-sm px-2 py-1 max-md:min-h-[44px] max-md:min-w-[44px]"
        >
          ✕
        </button>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
        <div>
          <div className="text-xs text-muted uppercase tracking-wider">{t("Type")}</div>
          <div className="mt-0.5">
            <Badge size="sm" tone={isBuy ? "gain" : "loss"} className="uppercase">
              {isBuy ? <ArrowUpRight size={11} aria-hidden="true" /> : <ArrowDownRight size={11} aria-hidden="true" />}
              {isBuy ? t("Buy") : t("Sell")}
            </Badge>
          </div>
        </div>
        <div>
          <div className="text-xs text-muted uppercase tracking-wider">{t("Amount")}</div>
          <div className="text-sm text-ink tabular-nums">
            ${Number(trade.amount_min).toLocaleString()}–${Number(trade.amount_max).toLocaleString()}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted uppercase tracking-wider">{t("Owner")}</div>
          <div className="text-sm text-ink">{trade.owner_code || "—"}</div>
        </div>
        <div>
          <div className="text-xs text-muted uppercase tracking-wider">{t("Transaction date")}</div>
          <div className="text-sm text-ink tabular-nums">{formatTableDate(trade.transaction_date)}</div>
        </div>
      </div>
      {trade.filed_date && (
        <p className="text-xs text-muted mt-2">
          {t("Reported {date}", { date: formatTableDate(trade.filed_date) })}
          {reportLag != null && reportLag > 0 && ` — ${reportLag === 1
            ? t("{count} day after the trade", { count: 1 })
            : t("{count} days after the trade", { count: reportLag })}`}
        </p>
      )}
      {trade.is_likely_option && (
        <div className="mt-3 pt-3 border-t border-surface-border">
          <Chip tone="warn">{t("Options trade")}</Chip>
          <p className="text-xs text-muted mt-1.5">{trade.asset_name}</p>
          <p className="text-xs text-muted mt-1">
            {t("Exact strike/expiration aren't in the data available here — can't automatically tell if this is a “deep ITM” style bet.")}
          </p>
        </div>
      )}
    </div>
  );
}

function PoliticalTradesSection({ ticker, currencyCode, currentPrice }) {
  const t = useT();
  const [enabled, setEnabled] = useState(false);
  const [selected, setSelected] = useState(null);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["politician-trades", ticker],
    queryFn: () => fetchPoliticianTrades(ticker),
    enabled: enabled && !!ticker,
    staleTime: 24 * 60 * 60 * 1000,
    retry: false,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h3 className="section-title">{t("Political Trades")}</h3>
        {!enabled && (
          <button
            onClick={() => setEnabled(true)}
            className="text-sm px-3 py-1.5 rounded-md bg-surface hover:bg-surface-hover border border-surface-border text-ink transition-colors"
          >
            {t("Load political trades")}
          </button>
        )}
      </div>

      {!enabled && (
        <p className="text-sm text-muted">
          {t("Congressional (STOCK Act) trades referencing this ticker. Loaded only on request — never fetched automatically.")}
        </p>
      )}

      {enabled && isLoading && <p className="text-sm text-muted">{t("Loading…")}</p>}

      {enabled && isError && (
        <p className="text-sm text-muted">
          {error?.response?.status === 503
            ? t("Political trades aren't configured — set ALPHA_VANTAGE_API_KEY on the backend to enable this.")
            : t("Could not load political trades.")}
        </p>
      )}

      {enabled && data && data.trades.length === 0 && (
        <p className="text-sm text-muted">{t("No disclosed congressional trades found for this ticker.")}</p>
      )}

      {enabled && data && data.trades.length > 0 && (
        <>
          <PoliticalTradesChart
            ticker={ticker}
            trades={data.trades}
            currencyCode={currencyCode}
            currentPrice={currentPrice}
            onSelect={setSelected}
          />
          {selected && <TradeDetailCard trade={selected} onClose={() => setSelected(null)} />}
          <div className="card !p-0 overflow-hidden">
            <div className="grid grid-cols-[1fr_3.5rem_5rem_9rem_6.5rem] gap-3 px-4 py-2 border-b border-surface-border text-xs uppercase tracking-wider text-muted font-medium">
              <span>{t("Politician")}</span>
              <span className="text-center">{t("Party")}</span>
              <span className="text-center">{t("Type")}</span>
              <span className="text-right">{t("Amount")}</span>
              <span className="text-right">{t("Date")}</span>
            </div>
            <ul className="max-h-96 overflow-y-auto">
              {data.trades.map((t, i) => {
                const isBuy = isPoliticalTradeBuy(t);
                return (
                  <li
                    key={i}
                    onClick={() => setSelected(t)}
                    className="grid grid-cols-[1fr_3.5rem_5rem_9rem_6.5rem] gap-3 items-center px-4 py-2 text-sm border-b border-surface-border last:border-0 hover:bg-surface-hover cursor-pointer"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-ink font-medium">
                        {t.politician_canonical || t.politician}
                      </div>
                      <div className="text-xs text-muted truncate">
                        {t.chamber} · {t.state}
                        {t.state_district ? ` (${t.state_district})` : ""} · {t.owner_code}
                        {t.is_likely_option && (
                          <span className="ml-1" style={{ color: "var(--chart-3)" }}>◆ {t("Option")}</span>
                        )}
                      </div>
                    </div>
                    <span className="text-center text-muted">{t.party}</span>
                    <span className="text-center">
                      <Badge size="sm" tone={isBuy ? "gain" : "loss"} className="uppercase">
                        {isBuy ? <ArrowUpRight size={11} aria-hidden="true" /> : <ArrowDownRight size={11} aria-hidden="true" />}
                        {isBuy ? t("Buy") : t("Sell")}
                      </Badge>
                    </span>
                    <span className="text-right tabular-nums text-muted">
                      ${Number(t.amount_min).toLocaleString()}–${Number(t.amount_max).toLocaleString()}
                    </span>
                    <span className="text-right tabular-nums text-muted">{formatTableDate(t.transaction_date)}</span>
                  </li>
                );
              })}
            </ul>
            {data.truncated && (
              <div className="px-4 py-2 text-xs text-muted border-t border-surface-border">
                Showing a partial list — {data.total_count} total trades found.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function EarningsRecapSection({ ticker, currencyCode }) {
  const t = useT();
  const cs = currencySymbol(currencyCode);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["shibui-earnings-recap", ticker],
    queryFn: () => fetchShibuiEarningsRecap(ticker),
    staleTime: 60 * 60 * 1000,
    enabled: !!ticker,
    retry: false,
  });

  if (isLoading || isError || !data?.quarters?.length) return null;
  const latest = data.quarters[0];
  const beat = latest.surprise_percent != null && latest.surprise_percent >= 0;
  const chartData = [...data.quarters].reverse().map((q) => ({
    label: `Q${q.quarter} '${String(q.year).slice(2)}`,
    surprise: q.surprise_percent,
  }));
  const recentBuyback = data.buyback_trend?.[0];
  // The Y axis must fit the widest tick label (e.g. "-1234%"), so size it from the data:
  // ~7px per character at the 12px tick font, plus room for the tick gap.
  const surpriseValues = chartData.map((d) => d.surprise).filter((v) => Number.isFinite(v));
  const widestTickChars = Math.max(
    2,
    ...surpriseValues.map((v) => `${Math.round(v)}%`.length),
    // ticks can round up past the data extremes (e.g. 1234 -> 1400), so allow one extra digit
  ) + 1;
  const surpriseAxisWidth = Math.max(36, widestTickChars * 7 + 8);

  return (
    <div>
      <h3 className="mb-3 section-title">{t("Earnings")}</h3>

      <div className="card !p-4 mb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="text-xs text-muted uppercase tracking-wider">
              {t("Latest report · Q{quarter} {year} · {date}", { quarter: latest.quarter, year: latest.year, date: formatTableDate(latest.report_date) })}
            </div>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <Badge tone={beat ? "gain" : "loss"} className="uppercase">
                {beat ? <ArrowUpRight size={12} aria-hidden="true" /> : <ArrowDownRight size={12} aria-hidden="true" />}
                {beat ? t("Beat") : t("Miss")}
              </Badge>
              <span className="text-base text-ink tabular-nums">
                {t("EPS {actual} vs {estimate} est.", {
                  actual: `${cs}${latest.eps_actual?.toFixed(2)}`,
                  estimate: `${cs}${latest.eps_estimate?.toFixed(2)}`,
                })}
              </span>
              {latest.surprise_percent != null && (
                <span className={`text-sm tabular-nums ${beat ? "text-gain" : "text-loss"}`}>
                  ({latest.surprise_percent >= 0 ? "+" : ""}
                  {latest.surprise_percent.toFixed(1)}%)
                </span>
              )}
            </div>
          </div>
          {data.nearest_8k_2_02 && (
            <a
              href={data.nearest_8k_2_02.filing_url}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-brand hover:underline inline-flex items-center gap-1"
            >
              {t("8-K press release")} <ExternalLink size={10} />
            </a>
          )}
        </div>
        {latest.revenue_actual != null && (
          <div className="text-sm text-muted mt-2 tabular-nums">
            {t("Revenue: {amount}", { amount: fmtCompact(latest.revenue_actual, cs) })}
            {data.latest_revenue_estimate != null && (
              <>
                {" "}
                {t("vs est. {amount}", { amount: fmtCompact(data.latest_revenue_estimate, cs) })}
                {data.latest_revenue_surprise_pct != null && (
                  <span className={data.latest_revenue_surprise_pct >= 0 ? "text-gain" : "text-loss"}>
                    {" "}
                    ({data.latest_revenue_surprise_pct >= 0 ? "+" : ""}
                    {data.latest_revenue_surprise_pct.toFixed(1)}%)
                  </span>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <div className="card !p-4 mb-3">
        <h4 className="mb-2 section-title">
          {t("EPS surprise history")}
        </h4>
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="label" tick={AXIS_TICK_STYLE} minTickGap={16} />
              <YAxis tick={AXIS_TICK_STYLE} width={surpriseAxisWidth} tickFormatter={(v) => `${Math.round(v)}%`} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${v?.toFixed(1)}%`, t("Surprise")]} />
              <Bar dataKey="surprise" radius={[7, 7, 0, 0]}>
                {chartData.map((d, i) => (
                  <Cell key={i} fill={d.surprise >= 0 ? GAIN_COLOR : LOSS_COLOR} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {recentBuyback && (
        <div className="card !p-4">
          <h4 className="mb-1 section-title">
            {t("Buyback trend")}
          </h4>
          <p className="text-sm text-muted">
            {recentBuyback.equity_issuance_repayment < 0
              ? t("Q{quarter} {year}: net repurchase of {amount}", {
                quarter: recentBuyback.quarter,
                year: recentBuyback.year,
                amount: fmtCompact(Math.abs(recentBuyback.equity_issuance_repayment), cs),
              })
              : t("Q{quarter} {year}: net issuance of {amount}", {
                quarter: recentBuyback.quarter,
                year: recentBuyback.year,
                amount: fmtCompact(Math.abs(recentBuyback.equity_issuance_repayment), cs),
              })}
          </p>
        </div>
      )}
    </div>
  );
}

const VALUATION_RANGES = [
  { label: "1Y", years: 1 },
  { label: "5Y", years: 5 },
  { label: "10Y", years: 10 },
  { label: "Max", years: 33 },
];

function ValuationHistorySection({ ticker }) {
  const t = useT();
  const [range, setRange] = useState(VALUATION_RANGES[2]);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["shibui-valuation-history", ticker, range.years],
    queryFn: () => fetchShibuiValuationHistory(ticker, range.years),
    staleTime: 60 * 60 * 1000,
    enabled: !!ticker,
    retry: false,
    // Keep the old points while another range loads, so the strip (and the chart
    // the user has open) is not unmounted and reset to P/E on every range switch.
    placeholderData: keepPreviousData,
  });

  if (isError) return null;
  const points = data?.points || [];

  return (
    <div id={VALUATION_HISTORY_ID}>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="section-title">
          {t("Valuation History")}
          {data?.granularity && (
            <span className="ml-2 text-muted normal-case tracking-normal">
              · {data.granularity} points
            </span>
          )}
        </h3>
        <SegmentedControl
          aria-label={t("Valuation history range")}
          value={range.label}
          onChange={(label) => setRange(VALUATION_RANGES.find((r) => r.label === label) ?? range)}
          options={VALUATION_RANGES.map((r) => ({ value: r.label, label: r.label === "Max" ? t("Max") : r.label }))}
        />
      </div>

      {isLoading && <p className="text-sm text-muted">{t("Loading…")}</p>}
      {!isLoading && points.length === 0 && (
        <p className="text-sm text-muted">{t("No valuation history available.")}</p>
      )}

      {points.length > 0 && (
        <ValuationHistoryCharts points={points} />
      )}
    </div>
  );
}

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Month names are English source text (see DividendBarsCard's MONTH_LABELS),
// translated with `t`.
function formatWeekTick(ts, t) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return `${t(MONTH_LABELS[d.getUTCMonth()])} '${String(d.getUTCFullYear()).slice(-2)}`;
}

// Renders every insider buy/sell dot directly onto the chart's SVG via
// Recharts' Customized layer (the same technique TtmUnderlay uses above),
// converting each dot's (x, y) data value to pixel space with the axis
// scales Recharts hands us. This sidesteps a Recharts <Scatter> quirk: when
// a Scatter's own `data` array happens to have the same length as the
// ComposedChart's shared `data` array (a real, non-contrived collision —
// e.g. a ticker with exactly one buy per week over the 52-week window),
// Recharts silently substitutes the chart-level row object as the custom
// shape's payload instead of the Scatter item's own richer object, breaking
// hover state and the info box for that series. Drawing dots ourselves
// avoids the per-series data-length coincidence entirely.
function InsiderDotsLayer({ xAxisMap, yAxisMap, offset, dots, hoveredDot, onEnter, onLeave }) {
  const xScale = xAxisMap && Object.values(xAxisMap)[0]?.scale;
  const yScale = yAxisMap && Object.values(yAxisMap)[0]?.scale;
  if (!xScale || !yScale || !dots.length) return null;
  const rightEdge = (offset?.left ?? 0) + (offset?.width ?? 0) * 0.65;

  return (
    <g>
      {dots.map((dot) => {
        const cx = xScale(dot.x);
        const cy = yScale(dot.y) + jitterOffsetPx(dot.jitterIndex);
        if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
        const color = dot.side === "buy" ? GAIN_COLOR : LOSS_COLOR;
        const isHovered = hoveredDot?.key === dot.key;
        const faded = hoveredDot != null && hoveredDot.side !== dot.side;
        return (
          <circle
            key={dot.key}
            cx={cx}
            cy={cy}
            r={isHovered ? 7 : 4}
            fill={color}
            fillOpacity={faded ? 0.05 : 1}
            stroke={color}
            strokeOpacity={isHovered ? 0.5 : 0}
            strokeWidth={isHovered ? 2 : 0}
            pointerEvents={faded ? "none" : "auto"}
            style={{ cursor: "pointer", transition: "fill-opacity 120ms ease" }}
            onMouseEnter={() => onEnter({ ...dot, cx, cy, flipX: cx > rightEdge })}
            onMouseLeave={onLeave}
          />
        );
      })}
    </g>
  );
}

function InsiderVolumeChart({ ticker, transactions, currencyCode }) {
  const t = useT();
  const cs = currencySymbol(currencyCode);
  const [hoveredDot, setHoveredDot] = useState(null);

  const { data: hist } = useQuery({
    queryKey: ["history", ticker, "1y"],
    queryFn: () => fetchHistory(ticker, "1y"),
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: false,
  });

  const buckets = useMemo(() => buildWeeklyBuckets(hist?.data, 52), [hist]);

  const chartData = useMemo(
    () => buckets.map((b) => ({ x: b.weekTs, y: b.close })),
    [buckets],
  );
  const monthTicks = useMemo(() => {
    const months = new Set();
    return buckets.filter((bucket) => {
      const month = bucket.weekKey.slice(0, 7);
      if (months.has(month)) return false;
      months.add(month);
      return true;
    }).map((bucket) => bucket.weekTs);
  }, [buckets]);

  const dots = useMemo(() => {
    const raw = assignTransactionsToWeeks(transactions, buckets);
    const groupCounts = new Map();
    return raw.map((d) => {
      const groupKey = `${d.weekKey}_${d.side}`;
      const idx = groupCounts.get(groupKey) ?? 0;
      groupCounts.set(groupKey, idx + 1);
      return { ...d, x: d.weekTs, y: d.close, jitterIndex: idx };
    });
  }, [transactions, buckets]);

  const hasPriceData = chartData.some((r) => r.y != null);
  if (!dots.length && !hasPriceData) return null;

  const closes = chartData.map((r) => r.y).filter((v) => v != null);
  const priceTicks = buildPriceAxis(closes);
  const formatPriceTick = (value) => `${cs}${value.toLocaleString("en-US", {
    maximumFractionDigits: 0,
  })}`;
  const priceAxisWidth = Math.max(80, formatPriceTick(priceTicks[4]).length * 8 + 24);

  return (
    <div>
      <h3 className="mb-3 section-title">
        {t("Insider Trading Volume")}
      </h3>
      <div className="card !p-4">
        <ul className="flex flex-wrap gap-x-6 gap-y-2 mb-4 text-sm leading-5 text-ink" aria-label={t("Insider trading chart legend")}>
          {[
            { label: t("Close Price"), color: CATEGORICAL[0], line: true },
            { label: t("Insider Buys"), color: GAIN_COLOR },
            { label: t("Insider Sells"), color: LOSS_COLOR },
          ].map((item) => (
            <li key={item.label} className="inline-flex items-center gap-2">
              <span
                aria-hidden="true"
                className={item.line ? "w-4 h-0.5 shrink-0" : "w-2.5 h-2.5 rounded-full shrink-0"}
                style={{ backgroundColor: item.color }}
              />
              {item.label}
            </li>
          ))}
        </ul>
        <div className="relative h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 16, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
              <XAxis
                dataKey="x"
                type="number"
                domain={["dataMin", "dataMax"]}
                ticks={monthTicks}
                tickFormatter={(ts) => formatWeekTick(ts, t)}
                tick={{ ...AXIS_TICK, fill: "var(--ink)", fontSize: 13, fontWeight: 500 }}
                interval="preserveStartEnd"
                minTickGap={8}
                tickMargin={12}
                height={40}
                padding={{ left: 8, right: 8 }}
                tickLine={false}
                axisLine={{ stroke: GRID_STROKE }}
              />
              <YAxis
                domain={[priceTicks[0], priceTicks[4]]}
                ticks={priceTicks}
                interval={0}
                allowDecimals={false}
                tick={{ ...AXIS_TICK, fill: "var(--ink)", fontSize: 13, fontWeight: 500 }}
                tickFormatter={formatPriceTick}
                tickMargin={12}
                minTickGap={8}
                tickCount={5}
                tickLine={false}
                axisLine={false}
                width={priceAxisWidth}
              />
              <Line
                type="monotone"
                dataKey="y"
                stroke={CATEGORICAL[0]}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Customized
                component={(cp) => (
                  <InsiderDotsLayer
                    {...cp}
                    dots={dots}
                    hoveredDot={hoveredDot}
                    onEnter={setHoveredDot}
                    onLeave={() => setHoveredDot(null)}
                  />
                )}
              />
            </ComposedChart>
          </ResponsiveContainer>
          {hoveredDot && (
            <div
              className="absolute z-10 pointer-events-none bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm leading-5 tabular-nums shadow-lg space-y-1 whitespace-nowrap"
              style={{
                left: hoveredDot.cx,
                top: hoveredDot.cy,
                transform: hoveredDot.flipX ? "translate(calc(-100% - 14px), -50%)" : "translate(14px, -50%)",
              }}
            >
              <div className="text-ink font-semibold truncate max-w-[180px]">
                {hoveredDot.insider || "—"}
              </div>
              <div className="text-muted">{hoveredDot.date}</div>
              <div className="text-ink">
                {hoveredDot.shares != null ? t("{shares} sh", { shares: fmtCompact(hoveredDot.shares, "") }) : "—"}
              </div>
              <div className={hoveredDot.side === "buy" ? "text-gain" : "text-loss"}>
                {hoveredDot.value != null ? fmtCompact(hoveredDot.value, cs) : "—"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const insiderTypeOf = (t) => (t.side === "buy" ? "buy" : t.side === "sell" ? "sell" : "other");

const TX_CODE_LABELS = {
  P: msg("Open-market buy"), S: msg("Open-market sale"), A: msg("Grant/award"), D: msg("Disposition to issuer"),
  F: msg("Tax-withholding disposition"), M: msg("Option/derivative exercise"), G: msg("Gift"),
  C: msg("Conversion of derivative"), X: msg("In-the-money option exercise"),
};

const secKey = (date, shares) =>
  date && shares != null ? `${String(date).slice(0, 10)}|${Math.round(Math.abs(shares))}` : null;

// Attaches the SEC Form 4 transaction code to the yfinance rows by matching
// date + share count, and lets the code (not yfinance's text guess) decide
// buy/sell. Rows with no SEC match are returned untouched.
export function attachSecCodes(transactions, secRows) {
  if (!transactions?.length || !secRows?.length) return transactions;
  const byKey = new Map();
  for (const r of secRows) {
    const key = secKey(r.tx_date, r.shares);
    if (key && !byKey.has(key)) byKey.set(key, r.tx_code);
  }
  return transactions.map((t) => {
    const code = byKey.get(secKey(t.date, t.shares));
    if (!code) return t;
    return { ...t, code, side: code === "P" ? "buy" : code === "S" ? "sell" : "other" };
  });
}

// Fetches the SEC-coded Form 4 data (Pro plan; silently absent otherwise) and
// hands it to the yfinance-backed table as codes + cluster-buy banners.
function InsiderTransactionsWithSec({ ticker, transactions, ...rest }) {
  const { data } = useQuery({
    queryKey: ["shibui-insiders", ticker],
    queryFn: () => fetchShibuiInsiders(ticker),
    staleTime: 30 * 60 * 1000,
    enabled: !!ticker,
    retry: false,
  });
  const enriched = useMemo(
    () => attachSecCodes(transactions, data?.transactions),
    [transactions, data],
  );
  return <InsiderTransactionsSection transactions={enriched} clusters={data?.cluster_buys} {...rest} />;
}

export function InsiderTransactionsSection({ transactions, currencyCode, currentPrice, clusters = [] }) {
  const t = useT();
  const [activeTypes, setActiveTypes] = useState(() => new Set());
  const INSIDER_ROWS_PER_PAGE = 25;
  const [insiderPage, setInsiderPage] = useState(0);
  if (!transactions || !transactions.length) return null;
  const cs = currencySymbol(currencyCode);
  const gridCols = "grid-cols-[1fr_auto_auto_auto_auto_auto_auto]";

  const typeCounts = transactions.reduce((acc, txn) => {
    const key = insiderTypeOf(txn);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const typeOptions = Object.keys(YF_TYPE_META)
    .filter((key) => typeCounts[key])
    .map((key) => ({ value: key, count: typeCounts[key], ...YF_TYPE_META[key] }));
  const toggleType = (value) =>
    setActiveTypes((prev) => toggleSetValue(prev, value, typeOptions.length));
  const visibleTransactions =
    activeTypes.size === 0 ? transactions : transactions.filter((txn) => activeTypes.has(insiderTypeOf(txn)));

  // Reset to page 1 whenever the active type filter changes the row count,
  // so a stale page index can never point past the end of a shorter list.
  useEffect(() => setInsiderPage(0), [activeTypes]);
  const pagedTransactions = visibleTransactions.slice(
    insiderPage * INSIDER_ROWS_PER_PAGE,
    (insiderPage + 1) * INSIDER_ROWS_PER_PAGE
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h3 className="section-title">
          {t("Latest Insider Transactions")}
        </h3>
        <TypeFilterChips
          options={typeOptions}
          active={activeTypes}
          onToggle={toggleType}
          onReset={() => setActiveTypes(new Set())}
        />
      </div>
      {clusters.length > 0 && (
        <div className="mb-3 space-y-2">
          {clusters.map((c, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-xl px-3 py-2 text-sm"
              style={{ background: "color-mix(in srgb, var(--chart-3) 14%, var(--surface-card))" }}
            >
              <Flame size={14} className="shrink-0 mt-0.5" style={{ color: "var(--chart-3)" }} />
              <div>
                <span className="font-semibold text-ink">{t("Cluster buy detected")}</span>
                <span className="text-muted">
                  {" "}— {t("{count} insiders bought between {start} and {end}:", { count: c.buyers.length, start: c.start, end: c.end })}{" "}
                </span>
                <span className="text-ink">{c.buyers.join(", ")}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="card !p-0 overflow-x-auto">
        <div className={`grid ${gridCols} min-w-[700px] gap-3 px-4 py-2 border-b border-surface-border text-xs uppercase tracking-wider text-muted font-medium`}>
          <span>{t("Insider")}</span>
          <span className="w-32 text-left">{t("Type · Transaction")}</span>
          <span className="w-20 text-right">{t("Shares")}</span>
          <span className="w-20 text-right">{t("Price")}</span>
          <span className="w-24 text-right">{t("Value")}</span>
          <span className="w-24 text-right" title={t("Unrealized P&L vs current price")}>{t("P&L (vs now)")}</span>
          <span className="w-24 text-right">{t("Date")}</span>
        </div>
        <ul className="min-w-[700px]">
          {!pagedTransactions.length && (
            <li className="px-4 py-6 text-center text-sm text-muted">
              {t("No transactions match the selected filter.")}
            </li>
          )}
          {pagedTransactions.map((txn, i) => {
            const isBuy = txn.side === "buy";
            const isSell = txn.side === "sell";
            // The badge carries buy/sell; rows are not tinted.
            const sideColor = isBuy ? "text-gain" : isSell ? "text-loss" : "text-muted";
            const sideLabel = isBuy ? t("Buy") : isSell ? t("Sell") : t("Other");
            const sideTone = isBuy ? "gain" : isSell ? "loss" : "neutral";
            const Icon = isBuy ? ArrowUpRight : isSell ? ArrowDownRight : null;

            // Derive the executed price from value / shares. yfinance reports
            // both as positive magnitudes so this stays valid for either side.
            const shares = txn.shares != null ? Math.abs(txn.shares) : null;
            const value = txn.value != null ? Math.abs(txn.value) : null;
            // A zero value (grants, gifts, option exercises) has no price: show a dash.
            const pricePerShare =
              shares && shares > 0 && value ? value / shares : null;

            // P&L on the position the insider still notionally holds — only
            // makes sense for buys (mark-to-market the entry vs. today). Sells
            // realised cash at the time, so there's no live P&L to show.
            let pnl = null;
            let pnlPct = null;
            if (
              isBuy &&
              pricePerShare != null &&
              pricePerShare > 0 &&
              shares != null &&
              currentPrice != null
            ) {
              pnl = (currentPrice - pricePerShare) * shares;
              pnlPct = (currentPrice / pricePerShare - 1) * 100;
            }
            const pnlColor =
              pnl == null
                ? "text-muted"
                : pnl > 0
                  ? "text-gain"
                  : pnl < 0
                    ? "text-loss"
                    : "text-muted";
            const pnlPrefix = pnl != null && pnl > 0 ? "+" : pnl != null && pnl < 0 ? "−" : "";

            return (
              <li
                key={i}
                className={`grid ${gridCols} gap-3 items-center px-4 py-2 border-b border-surface-border last:border-0 text-sm transition-colors hover:bg-surface-hover`}
              >
                <div className="min-w-0">
                  <div className="text-ink truncate" title={txn.insider || ""}>
                    {txn.insider || "—"}
                  </div>
                  {txn.position && (
                    <div className="text-xs text-muted truncate" title={txn.position}>
                      {txn.position}
                    </div>
                  )}
                </div>
                <div className="w-32 flex items-center gap-1.5">
                  <Badge size="sm" tone={sideTone} className="uppercase tracking-wider">
                    {sideLabel}
                  </Badge>
                  {txn.code ? (
                    <Badge size="sm" tone="neutral" title={TX_CODE_LABELS[txn.code] ? t(TX_CODE_LABELS[txn.code]) : t("SEC Form 4 transaction code")} className="uppercase">
                      {txn.code}
                    </Badge>
                  ) : (
                    <span
                      className={`truncate text-xs ${sideColor}`}
                      title={txn.transaction || ""}
                    >
                      {txn.transaction || "—"}
                    </span>
                  )}
                </div>
                <div className="w-20 text-right tabular-nums text-ink flex items-center justify-end gap-1">
                  {Icon && <Icon size={11} className={sideColor} />}
                  {shares != null ? fmtCompact(shares, "") : "—"}
                </div>
                <div
                  className="w-20 text-right tabular-nums text-ink"
                  title={
                    pricePerShare != null
                      ? t("{price} / share", { price: `${cs}${pricePerShare.toFixed(4)}` })
                      : ""
                  }
                >
                  {pricePerShare != null ? `${cs}${pricePerShare.toFixed(2)}` : "—"}
                </div>
                <div className={`w-24 text-right tabular-nums font-medium ${sideColor}`}>
                  {value ? fmtCompact(value, cs) : "—"}
                </div>
                <div
                  className={`w-24 text-right tabular-nums font-medium ${pnlColor}`}
                  title={
                    pnl != null
                      ? t("Buy held to now: {amount}", {
                        amount: `${pnlPrefix}${fmtCompact(Math.abs(pnl), cs)}${pnlPct != null ? ` (${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(1)}%)` : ""}`,
                      })
                      : ""
                  }
                >
                  {pnl == null ? (
                    "—"
                  ) : (
                    <>
                      {pnlPrefix}
                      {fmtCompact(Math.abs(pnl), cs)}
                      {pnlPct != null && (
                        <div className="text-xs font-normal opacity-80">
                          {pnlPct >= 0 ? "+" : ""}
                          {pnlPct.toFixed(1)}%
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div className="w-24 text-right text-muted tabular-nums text-xs">
                  {formatTableDate(txn.date)}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="px-4">
          <Pagination
            offset={insiderPage * INSIDER_ROWS_PER_PAGE}
            limit={INSIDER_ROWS_PER_PAGE}
            total={visibleTransactions.length}
            onOffsetChange={(next) => setInsiderPage(Math.floor(next / INSIDER_ROWS_PER_PAGE))}
            ariaLabel={t("Insider transactions pages")}
          />
        </div>
      </div>
      <div className="text-xs text-muted mt-2">
        {t("Source: yfinance · SEC transaction codes and cluster buys from Form 4/5 (Pro) · P&L shown for buys only (held-to-now mark vs. current price).")}
      </div>
    </div>
  );
}
