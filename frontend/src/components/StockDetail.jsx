import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Customized, Legend,
  Line, Pie, PieChart, ReferenceArea, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  ArrowDownRight, ArrowUpRight, Building2, ChevronDown, ChevronUp,
  ExternalLink, Eye, EyeOff, Flame, Globe, Info, Landmark, RotateCcw, Settings2,
  TrendingDown, TrendingUp, Users, X,
} from "lucide-react";
import {
  fetchHistory, fetchStockDividendGrowth, fetchShibuiFilings, fetchShibuiInsiders,
  fetchShibuiActivistStakes, fetchShibuiStrategicInvestors, fetchShibuiOwnershipDetail,
  fetchShibuiEarningsRecap, fetchShibuiValuationHistory, fetchPoliticianTrades,
} from "../api";
import { columnChanges, ttmUnderlayRect } from "../lib/chartChanges";
import { formatShortDate } from "../lib/format";
import { buildWeeklyBuckets, assignTransactionsToWeeks, jitterOffsetPx } from "../lib/insiderWeekly";
import useStockReportConfig, { ALL_SECTIONS } from "../hooks/useStockReportConfig";
import {
  CATEGORICAL, NEUTRAL_COLOR, GAIN_COLOR, LOSS_COLOR, AXIS_TICK, GRID_STROKE, TOOLTIP_STYLE,
} from "../lib/chartTheme";
import { KpiBox } from "./ui";
import Pagination from "./ui/Pagination";
import ShinyText from "./reactbits/ShinyText";
import { TickerLink } from "./TickerLink";

const TTM_COLOR = "#9b7bd1";
const TTM_SIDE_REVEAL = 2;
const TTM_RADIUS = 4;
const PERIOD_LABEL_MIN_GAP = 3;
const PERIOD_LABEL_MIN_FONT_SIZE = 7;
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

function fmtPctValue(v) {
  if (v == null) return "—";
  return `${v.toFixed(1)}%`;
}

function fmtSignedNumber(v, digits = 2) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;
}

// Each row of the ratios table — value (focal stock), sector (median across
// constituents), and direction-aware Δ colouring. lowerIsBetter is true for
// valuation multiples (cheaper = greener) and leverage; false for quality
// metrics (margins, ROE, ROA, yield, liquidity).
const RATIO_ROWS = [
  { key: "pe", label: "P/E (TTM)", lowerIsBetter: true,
    tooltip: `Price to Earnings, Trailing Twelve Months. Share price ÷ EPS over the last 12 reported months — how much you pay for one unit of the company's annual profit. High P/E = the market expects growth, or the stock is expensive; low P/E = cheaper or low growth expectations. "Trailing" means it's based on actual, already-reported results (not forecasts).` },
  { key: "forward_pe", label: "Forward P/E", lowerIsBetter: true, yearKey: "forward_pe_fy1_year", labelYearSuffix: true,
    tooltip: `Forward Price to Earnings. Like P/E, but the denominator is analysts' estimated EPS for a future fiscal year. Current share price ÷ estimated future EPS. Because earnings are usually expected to grow, forward P/E is typically lower than trailing P/E. Reliability drops the further out the projected year, since estimates get less accurate.` },
  { key: "forward_pe_2y", label: "Forward P/E", lowerIsBetter: true, yearKey: "forward_pe_fy2_year", labelYearSuffix: true, noSector: true,
    tooltip: `Forward Price to Earnings (the fiscal year after next). Current share price ÷ analysts' estimated EPS two years out. Same idea as forward P/E but projected further ahead, so it's the least reliable of the P/E variants — estimates get less accurate the further out they go.` },
  { key: "ps", label: "P/S", lowerIsBetter: true,
    tooltip: `Price to Sales. Market capitalization ÷ annual revenue (or share price ÷ revenue per share). Measures how much you pay for each unit of the company's sales, regardless of whether those sales are profitable. Useful for comparing companies with thin or negative earnings. Very high P/S is typical only of high-margin, high-growth businesses.` },
  { key: "pb", label: "P/B", lowerIsBetter: true,
    tooltip: `Price to Book. Market cap ÷ book value of equity (or share price ÷ book value per share), where book value = total assets − total liabilities (the accounting net worth). Shows how much you pay relative to the company's net assets on the balance sheet. A very high P/B usually signals heavy intangible value (brand, IP) or a small/depleted equity base — often from large share buybacks.` },
  { key: "pfcf", label: "P/FCF", lowerIsBetter: true,
    tooltip: `Price to Free Cash Flow. Market cap ÷ free cash flow (or share price ÷ FCF per share), where FCF = operating cash flow − capital expenditures — the cash the business actually generates and can return to shareholders. Many investors prefer this to P/E because cash flow is harder to manipulate than accounting earnings.` },
  { key: "peg", label: "PEG", lowerIsBetter: true,
    tooltip: `Price/Earnings to Growth. P/E ÷ the expected annual earnings growth rate (in %). Contextualizes P/E by accounting for growth. Rule of thumb: ≈1 is fairly valued, below 1 may be undervalued relative to growth, above 1 may be overvalued. Only as good as the growth estimate plugged in.` },
  { key: "ev_ebitda", label: "EV/EBITDA", lowerIsBetter: true,
    tooltip: `Enterprise Value to EBITDA. EV (= market cap + total debt − cash, the theoretical cost to acquire the whole business) ÷ EBITDA (Earnings Before Interest, Taxes, Depreciation & Amortization, a proxy for core operating profitability). Capital-structure-neutral — it ignores how the firm is financed — making it ideal for comparing companies with different debt levels.` },
  { key: "ev_revenue", label: "EV/Revenue", lowerIsBetter: true,
    tooltip: `Enterprise Value to Revenue. EV ÷ annual revenue. Like P/S, but uses EV (which adds debt and subtracts cash) instead of just market cap, giving a more complete picture for leveraged companies. Useful when earnings are negative or volatile.` },
  { key: "de", label: "D/E", lowerIsBetter: true,
    tooltip: `Debt to Equity. Total debt ÷ shareholders' equity. Measures financial leverage — how much the company is funded by borrowing versus owners' capital. A high D/E indicates heavy reliance on debt. Nuance: aggressive buybacks shrink the equity base and can inflate D/E, overstating true financial risk for cash-rich firms.` },
  { key: "current_ratio", label: "Current Ratio", lowerIsBetter: false,
    tooltip: `Current assets ÷ current liabilities. A short-term liquidity test: can the company cover obligations due within one year using assets convertible to cash within one year? Above 1.0 means current assets exceed current liabilities; higher indicates a more comfortable liquidity cushion.` },
  { key: "quick_ratio", label: "Quick Ratio", lowerIsBetter: false,
    tooltip: `Quick Ratio (acid-test). (Current assets − inventory) ÷ current liabilities. A stricter version of the current ratio that excludes inventory, since inventory can be hard to convert to cash quickly. For asset-light businesses with little inventory, it's usually close to the current ratio.` },
  { key: "roe", label: "ROE", pct: true, lowerIsBetter: false,
    tooltip: `Return on Equity. Net income ÷ shareholders' equity. Measures how efficiently the company generates profit from owners' capital. A very high ROE can be inflated by a small equity base (from buybacks) or by heavy leverage, so interpret it alongside ROIC.` },
  { key: "roa", label: "ROA", pct: true, lowerIsBetter: false,
    tooltip: `Return on Assets. Net income ÷ total assets. Shows how efficiently the company turns its entire asset base into profit, independent of financing. Because it includes debt-funded assets, it's less flattered by leverage than ROE — and lower than ROE by definition when the firm uses debt.` },
  { key: "roic", label: "ROIC", pct: true, lowerIsBetter: false,
    tooltip: `Return on Invested Capital. NOPAT (Net Operating Profit After Tax) ÷ invested capital, where invested capital = total debt + equity − cash (the total capital actually deployed in the business). Measures how efficiently the company generates profit from all capital invested, regardless of how it's financed. Generally considered the highest-quality profitability metric because — unlike ROE — it is not distorted by leverage or buybacks. The key test: ROIC should exceed the company's cost of capital (WACC); if it does, the business is creating value.` },
  { key: "gross_margin", label: "Gross Margin", pct: true, lowerIsBetter: false,
    tooltip: `(Revenue − cost of goods sold) ÷ revenue, as a %. The share of each sales dollar left after the direct costs of producing the product/service. High gross margin indicates strong pricing power or a low-cost product (typical of software).` },
  { key: "operating_margin", label: "Operating Margin", pct: true, lowerIsBetter: false,
    tooltip: `Operating income ÷ revenue, as a %. Profit remaining after both COGS and operating expenses (R&D, sales, admin), but before interest and taxes. Reflects the profitability of core operations.` },
  { key: "net_margin", label: "Net Margin", pct: true, lowerIsBetter: false,
    tooltip: `Net income ÷ revenue, as a %. The "bottom line" — the share of each sales dollar that becomes profit after all costs: operating expenses, interest, and taxes. A net margin very close to the operating margin can signal large non-operating gains or a very low tax burden.` },
  { key: "div_yield", label: "Div Yield", pct: true, lowerIsBetter: false,
    tooltip: `Dividend Yield. Annual dividend per share ÷ share price, as a %. The cash return you receive in dividends relative to the stock's price. A low yield is typical of a growth company that reinvests profits rather than paying them out; a high yield suits income-focused stocks (though a very high yield can also signal risk).` },
  { key: "payout_ratio", label: "Payout Ratio", pct: true, lowerIsBetter: true,
    tooltip: `Dividends paid ÷ net income, as a %. The share of profits returned to shareholders as dividends. A low ratio means the company retains most earnings to fund growth or buybacks (leaving room to sustain or raise the dividend); a high ratio means most profit is paid out, which can be harder to sustain.` },
];

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

// Keep every period visible while guaranteeing a small visual gutter between
// adjacent labels. Start with a smaller axis font, shrink it when that is
// enough, and rotate only once a horizontal label would use the 3px gutter.
export function financialPeriodAxisLayout(labels, containerWidth, isQuarterly = false) {
  const count = labels?.length || 0;
  const maxFontSize = isQuarterly ? 8 : 9;
  if (!count) return { fontSize: maxFontSize, angle: 0 };

  const plotWidth = Math.max(1, containerWidth - PERIOD_AXIS_RESERVED_WIDTH);
  const availableWidth = Math.max(1, plotWidth / count - PERIOD_LABEL_MIN_GAP);
  const longestLabelLength = Math.max(...labels.map((label) => String(label ?? "").length), 1);
  // 0.72em is intentionally conservative for tabular digits in the UI fonts.
  const estimatedWidthAt = (fontSize) => longestLabelLength * fontSize * 0.72;
  const horizontalFontSize = Math.floor(availableWidth / (longestLabelLength * 0.72));

  if (horizontalFontSize >= PERIOD_LABEL_MIN_FONT_SIZE) {
    return { fontSize: Math.min(maxFontSize, horizontalFontSize), angle: 0 };
  }

  const fontSize = PERIOD_LABEL_MIN_FONT_SIZE;
  const textWidth = estimatedWidthAt(fontSize);
  const textHeight = fontSize * 1.15;
  const angles = [-45, -55, -65, -72, -78, -82, -90];
  const angle = angles.find((candidate) => {
    const radians = Math.abs(candidate) * Math.PI / 180;
    const projectedWidth = textWidth * Math.cos(radians) + textHeight * Math.sin(radians);
    return projectedWidth <= availableWidth;
  }) ?? -90;

  // At -90 degrees the projected width is the text height. Extremely dense
  // series therefore get one final font reduction instead of overlapping.
  const rotatedFontSize = angle === -90 && textHeight > availableWidth
    ? Math.max(5, Math.floor(availableWidth / 1.15))
    : fontSize;
  return { fontSize: rotatedFontSize, angle };
}

// Two-line x-axis tick for the financials bar charts: period label on top,
// vs-previous-column % change (see columnChanges) beneath it. Rendering the
// change inside the tick keeps it centred under its column at any chart
// width. The change line uses the darker 700-shade green/red plus a bold
// weight so it stays readable at chart-axis size.
function ChangeTick({
  x,
  y,
  payload,
  index,
  changes,
  fontSize = 11,
  changeFontSize = 11,
  changeDecimals = 1,
  periodAngle = 0,
  changeAngle = -45,
  showChange = true,
}) {
  const change = changes?.[payload?.index ?? index] ?? null;
  const periodY = 10;
  const changeY = periodAngle ? 36 : 28;
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        y={periodY}
        textAnchor={periodAngle ? "end" : "middle"}
        transform={periodAngle ? `rotate(${periodAngle}, 0, ${periodY})` : undefined}
        fill={AXIS_TICK.fill}
        fontSize={fontSize}
      >
        {payload.value}
      </text>
      {showChange && change != null && (
        <text
          y={changeY}
          textAnchor="end"
          transform={`rotate(${changeAngle}, 0, ${changeY})`}
          fill={change >= 0 ? "#047857" : "#b91c1c"}
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
  const cs = currencySymbol(currencyCode);
  const { name, years, values, yoy, cagr } = metric;
  const isQuarterly = period === "quarterly";
  const [chartRef, chartWidth] = useElementWidth();

  if (!years?.length) {
    return (
      <div className="bg-surface rounded-lg p-4 flex flex-col h-full">
        <h3 className="text-sm font-semibold text-muted uppercase tracking-wider mb-1">{name}</h3>
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          No data
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
  // Only widen the y-domain when the TTM level falls outside the bars' own
  // range — a functional domain costs recharts its nice round ticks, so keep
  // the default auto axis whenever the overlay already fits.
  const vals = rows.map((r) => r.value).filter((v) => v != null);
  const ttmOutside =
    showTtmOverlay && vals.length > 0 &&
    (ttm > Math.max(0, ...vals) || ttm < Math.min(0, ...vals));

  const headlineChange = isQuarterly
    ? changes[changes.length - 1]
    : yoy && yoy.length
      ? yoy[yoy.length - 1]
      : null;
  const headlineChangeLabel = isQuarterly ? "QoQ" : "YoY";

  return (
    <div className="bg-surface rounded-lg p-4 flex flex-col">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-semibold text-muted uppercase tracking-wider">{name}</h3>
        <div className="flex flex-col items-end text-[10px] gap-0.5">
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
        style={{ height: periodAxis.angle ? 192 : 176 }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rowsWithChange} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
            <XAxis
              dataKey="year"
              tick={
                <ChangeTick
                  changes={changes}
                  fontSize={periodAxis.fontSize}
                  changeFontSize={rows.length > 7 ? 9 : 11}
                  changeDecimals={rows.length > 7 ? 0 : 1}
                  periodAngle={periodAxis.angle}
                  changeAngle={changeAngle}
                  showChange={showChangeLine}
                />
              }
              tickLine={false}
              axisLine={{ stroke: GRID_STROKE }}
              interval={0}
              minTickGap={PERIOD_LABEL_MIN_GAP}
              height={showChangeLine ? (periodAxis.angle ? 76 : 62) : periodAxis.angle ? 50 : 20}
            />
            <YAxis
              tick={{ ...AXIS_TICK, fontSize: 10 }}
              tickFormatter={(v) =>
                isPerShare ? v.toFixed(1) : fmtCompact(v, "", 0)
              }
              tickLine={false}
              axisLine={false}
              width={48}
              // The TTM overlay isn't a bar, so when it exceeds every bar the
              // domain must be widened by hand (with 5% headroom) or the
              // overlay would draw past the plot area.
              domain={
                ttmOutside
                  ? [(dataMin) => Math.min(0, dataMin, ttm) * 1.05, (dataMax) => Math.max(0, dataMax, ttm) * 1.05]
                  : undefined
              }
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
                        YoY {fmtPct(row.yoy, 2)}
                      </div>
                    )}
                    {isQuarterly && row.change != null && (
                      <div className={changeColor(row.change)}>
                        QoQ {fmtPct(row.change, 2)}
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
            <Bar dataKey="value" radius={[3, 3, 0, 0]}>
              {rows.map((d, i) => (
                <Cell key={i} fill={isCount ? CATEGORICAL[3] : d.value >= 0 ? GAIN_COLOR : LOSS_COLOR} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RatingPill({ children, color = "text-muted bg-slate-600/10" }) {
  return (
    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${color}`}>
      {children}
    </span>
  );
}

function ratingColor(score) {
  if (score == null) return "text-muted bg-slate-500/10";
  if (score <= 1.5) return "text-gain bg-gain/10";
  if (score <= 2.5) return "text-green-600 bg-green-600/10";
  if (score <= 3.5) return "text-yellow-600 bg-yellow-600/10";
  if (score <= 4.5) return "text-orange-600 bg-orange-600/10";
  return "text-loss bg-loss/10";
}

function AnalystBar({ label, count, total, color }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-20 text-muted">{label}</span>
      <div className="flex-1 bg-surface rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="tabular-nums text-muted w-6 text-right font-medium">{count}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Valuation models: multiples + 2-stage DCF + sensitivity grid
// ---------------------------------------------------------------------------

function upsideColor(u) {
  if (u == null) return "text-muted";
  if (u >= 20) return "text-gain";
  if (u >= 5) return "text-green-600";
  if (u >= -5) return "text-yellow-600";
  if (u >= -20) return "text-orange-600";
  return "text-loss";
}

// Map a fair-value-vs-current pct into a heatmap bg color. Same scale as
// upsideColor but rendered as a translucent fill suitable for a grid cell.
function sensitivityBg(u) {
  if (u == null) return "bg-surface-hover/40";
  if (u >= 30) return "bg-emerald-500/30";
  if (u >= 15) return "bg-green-500/25";
  if (u >= 5) return "bg-green-500/15";
  if (u >= -5) return "bg-yellow-500/15";
  if (u >= -15) return "bg-orange-500/20";
  if (u >= -30) return "bg-red-500/25";
  return "bg-red-500/35";
}

function ValuationMethodRow({ row, currentPrice, cs }) {
  const fv = row.fair_value;
  const upside = row.upside;
  const inputs = row.inputs || {};

  // Compact summary of the inputs that produced the fair value.
  const inputBits = [];
  if (inputs.eps != null) {
    inputBits.push(`EPS ${cs}${inputs.eps.toFixed(2)} (${inputs.eps_basis})`);
  }
  if (inputs.ebitda != null) {
    inputBits.push(`EBITDA ${fmtCompact(inputs.ebitda, cs)}`);
  }
  if (inputs.fcf0 != null) {
    inputBits.push(`FCF₀ ${fmtCompact(inputs.fcf0, cs)}`);
  }
  if (inputs.multiple != null) {
    inputBits.push(`× ${inputs.multiple.toFixed(2)} (${inputs.multiple_source})`);
  }
  if (inputs.growth_pct != null) {
    inputBits.push(`g₁ ${inputs.growth_pct.toFixed(1)}% (${inputs.growth_source})`);
  }
  if (inputs.terminal_growth_pct != null) {
    inputBits.push(`g∞ ${inputs.terminal_growth_pct.toFixed(1)}%`);
  }
  if (inputs.wacc_pct != null) {
    inputBits.push(`WACC ${inputs.wacc_pct.toFixed(1)}%`);
  }

  return (
    <div className="grid grid-cols-[1fr_auto_auto] gap-3 items-baseline py-2 border-b border-surface-border last:border-0">
      <div className="min-w-0">
        <div className="text-base text-ink font-medium">{row.method}</div>
        {inputBits.length > 0 && (
          <div className="text-[10px] text-muted mt-0.5 truncate" title={inputBits.join(" · ")}>
            {inputBits.join(" · ")}
          </div>
        )}
      </div>
      <div className="text-base font-semibold tabular-nums text-ink w-24 text-right">
        {fv == null ? "—" : `${cs}${fv.toFixed(2)}`}
      </div>
      <div className={`text-base font-medium tabular-nums w-20 text-right ${upsideColor(upside)}`}>
        {upside == null ? "—" : fmtPct(upside, 1)}
      </div>
    </div>
  );
}

function DcfSensitivityTable({ sensitivity, currentPrice, cs }) {
  if (!sensitivity || !sensitivity.grid?.length) return null;
  const { wacc_pct, terminal_growth_pct, grid, base_wacc_pct, base_terminal_pct } = sensitivity;

  return (
    <div className="bg-surface rounded-lg p-4">
      <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
        <div>
          <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
            DCF Sensitivity
          </h3>
          <div className="text-[10px] text-muted mt-0.5">
            Fair value per share · g₁ {sensitivity.growth_pct.toFixed(1)}% · {sensitivity.years}y stage 1
          </div>
        </div>
        <div className="text-[10px] text-muted flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-sm bg-green-500/25" />Above price
          <span className="inline-block w-3 h-3 rounded-sm bg-yellow-500/15 ml-1" />~Fair
          <span className="inline-block w-3 h-3 rounded-sm bg-red-500/25 ml-1" />Below price
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr>
              <th className="text-left text-[10px] uppercase tracking-wider text-muted font-medium px-2 py-1.5">
                WACC ↓ / g∞ →
              </th>
              {terminal_growth_pct.map((t) => (
                <th
                  key={t}
                  className={`text-right text-[10px] uppercase tracking-wider font-medium px-2 py-1.5 ${
                    t === base_terminal_pct ? "text-ink" : "text-muted"
                  }`}
                >
                  {t.toFixed(1)}%
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.map((row, i) => {
              const w = wacc_pct[i];
              return (
                <tr key={w}>
                  <td
                    className={`text-left text-[10px] uppercase tracking-wider font-medium px-2 py-1.5 ${
                      w === base_wacc_pct ? "text-ink" : "text-muted"
                    }`}
                  >
                    {w.toFixed(1)}%
                  </td>
                  {row.map((fv, j) => {
                    const t = terminal_growth_pct[j];
                    const upside =
                      fv == null || !currentPrice ? null : ((fv / currentPrice) - 1) * 100;
                    const isBase = w === base_wacc_pct && t === base_terminal_pct;
                    return (
                      <td
                        key={`${w}-${t}`}
                        className={`text-right px-2 py-1.5 rounded ${sensitivityBg(upside)} ${
                          isBase ? "ring-1 ring-brand/70" : ""
                        }`}
                        title={
                          fv == null
                            ? "Degenerate (WACC ≤ g∞)"
                            : `FV ${cs}${fv.toFixed(2)} · ${upside == null ? "" : fmtPct(upside, 1)} vs current`
                        }
                      >
                        <div className="text-ink font-medium">
                          {fv == null ? "—" : `${cs}${fv.toFixed(0)}`}
                        </div>
                        {upside != null && (
                          <div className={`text-[10px] ${upsideColor(upside)}`}>
                            {fmtPct(upside, 0)}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ValuationSection({ valuation, currencyCode }) {
  if (!valuation || (!valuation.methods?.length && !valuation.sensitivity)) {
    return null;
  }
  const cs = currencySymbol(currencyCode);
  const methods = valuation.methods || [];
  const currentPrice = valuation.price;

  // Summary stats: average and span of fair values across all methods so the
  // user can eyeball a target range.
  const fvs = methods.map((m) => m.fair_value).filter((v) => v != null);
  const avgFv = fvs.length ? fvs.reduce((a, b) => a + b, 0) / fvs.length : null;
  const minFv = fvs.length ? Math.min(...fvs) : null;
  const maxFv = fvs.length ? Math.max(...fvs) : null;
  const avgUpside =
    avgFv != null && currentPrice ? ((avgFv / currentPrice) - 1) * 100 : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
          Valuation Models
        </h3>
        <div className="text-[10px] text-muted">
          Heuristic models, not investment advice. Inputs from yfinance.
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="bg-surface rounded-lg p-4">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-muted mb-1 pb-1 border-b border-surface-border">
            <span>Method</span>
            <div className="flex items-center">
              <span className="w-24 text-right">Fair Value</span>
              <span className="w-20 text-right">vs Price</span>
            </div>
          </div>
          {methods.length === 0 ? (
            <div className="text-muted text-sm py-3 text-center">
              Not enough data to compute valuation methods.
            </div>
          ) : (
            methods.map((m) => (
              <ValuationMethodRow
                key={m.method}
                row={m}
                currentPrice={currentPrice}
                cs={cs}
              />
            ))
          )}
          {fvs.length >= 2 && (
            <div className="mt-3 pt-3 border-t border-surface-border flex items-center justify-between text-sm">
              <span className="text-muted">
                Average · Range
              </span>
              <div className="flex items-center gap-3 tabular-nums">
                <span className="text-muted">
                  {cs}{minFv.toFixed(2)}–{cs}{maxFv.toFixed(2)}
                </span>
                <span className="text-ink font-semibold w-24 text-right">
                  {cs}{avgFv.toFixed(2)}
                </span>
                <span className={`font-medium w-20 text-right ${upsideColor(avgUpside)}`}>
                  {avgUpside == null ? "—" : fmtPct(avgUpside, 1)}
                </span>
              </div>
            </div>
          )}
        </div>

        <DcfSensitivityTable
          sensitivity={valuation.sensitivity}
          currentPrice={currentPrice}
          cs={cs}
        />
      </div>
    </div>
  );
}

function SectionCustomizer({ config, toggle, moveUp, moveDown, reset, isVisible }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-base rounded-lg border border-surface-border text-muted hover:text-ink hover:border-slate-300 transition-colors"
        title="Customize report sections"
      >
        <Settings2 size={14} />
        Customize
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-72 z-50 bg-surface-card border border-surface-border rounded-xl shadow-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-surface-border">
              <span className="text-sm font-semibold text-muted uppercase tracking-wider">Report Sections</span>
              <button
                type="button"
                onClick={reset}
                className="inline-flex items-center gap-1 text-[10px] text-muted hover:text-ink transition-colors"
              >
                <RotateCcw size={10} /> Reset
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
                      title={visible ? "Hide section" : "Show section"}
                    >
                      {visible ? <Eye size={14} /> : <EyeOff size={14} />}
                    </button>
                    <span className={`flex-1 text-base ${visible ? "text-ink" : "text-muted"}`}>
                      {section.label}
                    </span>
                    <div className="flex items-center gap-0.5">
                      <button
                        type="button"
                        onClick={() => moveUp(id)}
                        disabled={idx === 0}
                        className="text-muted hover:text-ink disabled:opacity-20 transition-colors p-0.5"
                      >
                        <ChevronUp size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveDown(id)}
                        disabled={idx === config.order.length - 1}
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
  const { data, isLoading } = useQuery({
    queryKey: ["dividend-growth", ticker],
    queryFn: () => fetchStockDividendGrowth(ticker),
    staleTime: 5 * 60 * 1000,
    enabled: !!ticker,
  });

  if (isLoading || !data || !data.payments?.length) return null;

  const lastExDate = data.payments[data.payments.length - 1]?.ex_date;
  const oneYearAgo = new Date();
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
  if (!lastExDate || new Date(lastExDate) < oneYearAgo) return null;

  const sym = currencySymbol(currency);
  const tiles = [
    { label: "Growth streak", value: data.streak_years > 0 ? `${data.streak_years} yrs` : "—" },
    { label: `${data.cagr_years_used || 5}yr CAGR`, value: data.cagr_pct != null ? `${data.cagr_pct.toFixed(1)}%` : "—" },
    { label: "YoY", value: data.yoy_pct != null ? `${data.yoy_pct.toFixed(1)}%` : "—" },
  ];

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold text-muted uppercase tracking-wider">Dividend history</h3>
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <KpiBox key={t.label} size="sm" label={t.label} value={t.value} />
        ))}
      </div>
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data.payments} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="ex_date" tick={{ ...AXIS_TICK, fontSize: 12 }} tickFormatter={(d) => String(d).slice(0, 7)} minTickGap={24} />
            <YAxis tick={{ ...AXIS_TICK, fontSize: 12 }} width={52} tickFormatter={(v) => `${sym}${v}`} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.03)" }}
              contentStyle={{ background: "var(--surface-card-elevated)", border: "1px solid var(--hairline)", borderRadius: 8, fontSize: 13 }}
              formatter={(v) => [`${sym}${v}`, "Per share"]}
            />
            <Bar dataKey="amount" fill={GAIN_COLOR} radius={[3, 3, 0, 0]} />
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
}) {
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

  // 52w range progress
  const range = (() => {
    if (!data.fifty_two_week_low || !data.fifty_two_week_high || !data.price) return null;
    const lo = data.fifty_two_week_low;
    const hi = data.fifty_two_week_high;
    const p = Math.max(0, Math.min(100, ((data.price - lo) / (hi - lo)) * 100));
    return { lo, hi, pct: p };
  })();

  const sections = {
    quickStats: (
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        <KpiBox size="sm" label="Market Cap" value={fmtCompact(data.market_cap, cs)} />
        <KpiBox size="sm" label="P/E (TTM)" value={fmtRatio(ratios.pe)} />
        <KpiBox size="sm" label="EPS (TTM)" value={ttm.eps != null ? `${cs}${ttm.eps.toFixed(2)}` : "—"} />
        <KpiBox size="sm" label="Div Yield" value={ratios.div_yield != null ? `${ratios.div_yield.toFixed(2)}%` : "—"} />
        <KpiBox size="sm" label="Beta" value={fmtRatio(data.beta)} />
        <KpiBox size="sm" label="EV/EBITDA" value={fmtRatio(ratios.ev_ebitda)} />
      </div>
    ),

    weekRange: range ? (
      <div className="bg-surface rounded-[var(--radius-card)] px-4 py-3">
        <div className="flex items-center justify-between text-[10px] text-muted uppercase tracking-wider mb-2">
          <span>52-Week Range</span>
          {data.fifty_day_avg != null && (
            <span>50D Avg {cs}{data.fifty_day_avg.toFixed(2)} · 200D Avg {cs}{data.two_hundred_day_avg?.toFixed(2) ?? "—"}</span>
          )}
        </div>
        <div className="relative h-2 bg-surface-hover rounded-full">
          <div
            className="absolute top-0 h-2 w-1 bg-brand rounded"
            style={{ left: `calc(${range.pct}% - 2px)` }}
          />
        </div>
        <div className="flex items-center justify-between text-sm mt-1.5 tabular-nums">
          <span className="text-loss">{cs}{range.lo.toFixed(2)}</span>
          <span className="text-muted">Current {cs}{data.price.toFixed(2)}</span>
          <span className="text-gain">{cs}{range.hi.toFixed(2)}</span>
        </div>
      </div>
    ) : null,

    dividendGrowth: <DividendGrowthSection ticker={data.ticker} currency={data.currency} />,

    financials: (
      <div>
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
            {period === "quarterly" ? "Quarterly Financials" : "Annual Financials"}
            {periodsCount > 0 && (
              <span className="ml-2 text-muted normal-case tracking-normal">
                · {periodsCount} {period === "quarterly" ? "quarters" : "years"}
              </span>
            )}
          </h3>
          <div className="inline-flex bg-surface rounded-md p-0.5 text-sm">
            <button
              type="button"
              onClick={() => setPeriod("annual")}
              className={`px-3 py-1 rounded transition-colors ${
                period === "annual"
                  ? "bg-surface-card text-brand font-semibold shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
            >
              Annual
            </button>
            <button
              type="button"
              onClick={() => setPeriod("quarterly")}
              disabled={!hasQuarterly}
              className={`px-3 py-1 rounded transition-colors ${
                period === "quarterly"
                  ? "bg-surface-card text-brand font-semibold shadow-sm"
                  : "text-muted hover:text-ink"
              } ${!hasQuarterly ? "opacity-40 cursor-not-allowed" : ""}`}
              title={hasQuarterly ? "" : "No quarterly data available"}
            >
              Quarterly
            </button>
          </div>
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
            <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
              Valuation & Quality
            </h3>
            {sector.sample_size > 0 && (
              <span className="text-[10px] text-muted">
                Sector = median of {sector.sample_size} {data.sector}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {RATIO_ROWS.map((r) => {
              const year = r.yearKey ? ratios[r.yearKey] : null;
              const label =
                r.labelYearSuffix && year != null
                  ? `${r.label} (${year})`
                  : r.label;
              const fmt = r.pct ? fmtPctValue : fmtRatio;
              const value = ratios[r.key];
              const sectorVal = r.noSector ? null : sector[r.key];
              const delta = value != null && sectorVal != null ? value - sectorVal : null;
              const favourable = delta == null ? null : (r.lowerIsBetter ? delta < 0 : delta > 0);
              const direction = r.lowerIsBetter ? "Lower is better." : "Higher is better.";
              return (
                <KpiBox
                  key={r.key}
                  size="sm"
                  label={label}
                  value={fmt(value)}
                  info={r.tooltip ? { title: label, what: r.tooltip, note: direction } : { title: label, what: direction }}
                  sub={r.noSector ? null : `Sector ${fmt(sectorVal)} · Δ ${delta == null ? "—" : fmtSignedNumber(delta, 2)}`}
                  subTone={favourable == null ? "muted" : favourable ? "gain" : "loss"}
                />
              );
            })}
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-surface rounded-[var(--radius-card)] p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
                Analyst Rating
              </h3>
              {analyst.rating && (
                <RatingPill color={ratingColor(analyst.score)}>{analyst.rating}</RatingPill>
              )}
            </div>
            {analyst.total > 0 ? (
              <>
                <div className="flex items-baseline gap-3 mb-3">
                  <span className="text-4xl font-bold tabular-nums">
                    {analyst.score != null ? analyst.score.toFixed(2) : "—"}
                  </span>
                  <span className="text-sm text-muted">
                    consensus · {analyst.total} analysts
                  </span>
                </div>
                <div className="space-y-1.5">
                  <AnalystBar label="Strong Buy" count={analyst.strong_buy || 0} total={analyst.total} color="bg-emerald-500" />
                  <AnalystBar label="Buy" count={analyst.buy || 0} total={analyst.total} color="bg-green-500" />
                  <AnalystBar label="Hold" count={analyst.hold || 0} total={analyst.total} color="bg-yellow-500" />
                  <AnalystBar label="Sell" count={analyst.sell || 0} total={analyst.total} color="bg-orange-500" />
                  <AnalystBar label="Strong Sell" count={analyst.strong_sell || 0} total={analyst.total} color="bg-red-500" />
                </div>
              </>
            ) : (
              <div className="text-muted text-sm">No analyst coverage available.</div>
            )}
          </div>

          <div className="bg-surface rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
                Price Targets
              </h3>
              {analyst.target_mean != null && analyst.upside != null && (
                <span className={`text-sm font-medium ${analyst.upside >= 0 ? "text-gain" : "text-loss"}`}>
                  {fmtPct(analyst.upside)} avg upside
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
              <div className="text-muted text-sm">No price targets available.</div>
            )}
          </div>

          {data.description && (
            <div className="bg-surface rounded-lg p-4">
              <h3 className="text-base font-semibold text-muted uppercase tracking-wider mb-2">
                About
              </h3>
              <p className="text-sm text-muted leading-relaxed line-clamp-6">
                {data.description}
              </p>
            </div>
          )}
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
      <InsiderTransactionsSection
        transactions={data.insider_transactions}
        currencyCode={data.currency}
        currentPrice={data.price}
      />
    ),

    valuation: (
      <ValuationSection valuation={data.valuation} currencyCode={data.currency} />
    ),

    ownership: (
      <OwnershipSection ownership={data.ownership} currencyCode={data.currency} />
    ),

    earningsRecap: <EarningsRecapSection ticker={data.ticker} currencyCode={data.currency} />,

    valuationHistory: <ValuationHistorySection ticker={data.ticker} />,

    shibuiFilings: <ShibuiFilingsSection ticker={data.ticker} />,

    shibuiInsiderActivity: (
      <ShibuiInsiderActivitySection ticker={data.ticker} currencyCode={data.currency} />
    ),

    politicalTrades: (
      <PoliticalTradesSection ticker={data.ticker} currencyCode={data.currency} currentPrice={data.price} />
    ),

    shibuiOwnershipFilings: <ShibuiOwnershipFilingsSection ticker={data.ticker} />,
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
              <span className="text-[10px] text-muted uppercase tracking-wider">{data.exchange}</span>
            )}
            {data.fundamentals_source && (
              <span
                title={
                  data.fundamentals_source === "shibui"
                    ? "Financials and ratios below are sourced from Shibui Finance (analyst rating/estimates are always from yfinance -- Shibui doesn't cover those)."
                    : "Shibui doesn't cover this ticker, or is unavailable right now (e.g. rate-limited) -- financials and ratios below fell back to yfinance."
                }
                className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full uppercase tracking-wider cursor-help ${
                  data.fundamentals_source === "shibui"
                    ? "bg-brand/10 text-brand"
                    : "bg-amber-500/15 text-amber-500"
                }`}
              >
                <Info size={10} />
                {data.fundamentals_source === "shibui" ? "Shibui" : "yfinance fallback"}
              </span>
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

function AnalystForecastCone({ low, high, mean, current, cs }) {
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

  // Each target is coloured by direction vs. current: above → green, below → red.
  const colorFor = (v) =>
    v > current
      ? "bg-green-500 text-green-50"
      : v < current
        ? "bg-red-500 text-red-50"
        : "bg-gray-500 text-gray-50";
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
            margin={{ top: CONE_MARGIN_TOP, right: 96, bottom: CONE_MARGIN_BOTTOM, left: 4 }}
          >
            <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
            <XAxis
              dataKey="label"
              height={CONE_XAXIS_HEIGHT}
              tick={{ ...AXIS_TICK, fontSize: 12 }}
              tickLine={false}
              axisLine={{ stroke: GRID_STROKE }}
            />
            <YAxis
              domain={[yMin, yMax]}
              allowDataOverflow={true}
              orientation="right"
              tick={{ ...AXIS_TICK, fontSize: 11 }}
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
              fill="#ef4444"
              fillOpacity={0.18}
              isAnimationActive={false}
            />
            <Area
              type="linear"
              dataKey="upper"
              stroke="none"
              fill="#10b981"
              fillOpacity={0.18}
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
                    <div className="text-muted mb-1">{row.label}</div>
                    {row.label === "Now" ? (
                      <div className="text-ink">Current {cs}{current.toFixed(2)}</div>
                    ) : (
                      <>
                        <div className="text-gain">Max {cs}{high.toFixed(2)} <span className="text-muted">({pct(upsideMax)})</span></div>
                        <div className="text-green-600">Avg {cs}{mean.toFixed(2)} <span className="text-muted">({pct(upsideAvg)})</span></div>
                        <div className="text-loss">Min {cs}{low.toFixed(2)} <span className="text-muted">({pct(upsideMin)})</span></div>
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
          { value: high, color: colorFor(high), label: `Max ${pct(upsideMax)}` },
          { value: mean, color: colorFor(mean), label: `Avg ${pct(upsideAvg)}` },
          { value: current, color: "bg-blue-500 text-blue-50", label: "Current" },
          { value: low, color: colorFor(low), label: `Min ${pct(upsideMin)}` },
        ]}
        yMin={yMin}
        yMax={yMax}
        cs={cs}
      />
      <div className="absolute left-1/2 -translate-x-1/2 bottom-0 px-3 py-1 rounded-full bg-surface border border-surface-border text-[10px] uppercase tracking-wider text-muted">
        1Y Forecast
      </div>
    </div>
  );
}

function RightEdgePills({ items, yMin, yMax, cs }) {
  // Plot area = total height − top margin − (bottom margin + XAxis height).
  // Pills are positioned proportionally on that band; nudge to avoid overlap.
  const plotTop = CONE_MARGIN_TOP;
  const plotBottom = CONE_MARGIN_BOTTOM + CONE_XAXIS_HEIGHT;
  const usable = CONE_CHART_HEIGHT - plotTop - plotBottom;
  const yFor = (v) => plotTop + ((yMax - v) / (yMax - yMin)) * usable;

  const sorted = [...items]
    .map((it) => ({ ...it, y: yFor(it.value) }))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].y - sorted[i - 1].y < 18) sorted[i].y = sorted[i - 1].y + 18;
  }

  return (
    <div className="absolute inset-0 pointer-events-none">
      {sorted.map((it, i) => (
        <div
          key={i}
          className={`absolute right-1 flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold tabular-nums whitespace-nowrap ${it.color}`}
          style={{ top: `${it.y - 9}px` }}
        >
          <span>{it.label}</span>
          <span className="opacity-90">{cs}{it.value.toFixed(2)}</span>
        </div>
      ))}
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
  const cs = currencySymbol(currencyCode);
  const isQuarterly = data?.some((d) => /^Q[1-4]/.test(d.label));
  const [chartRef, chartWidth] = useElementWidth();
  if (!data?.length) {
    return (
      <div className="bg-surface rounded-lg p-4 flex flex-col h-full">
        <h3 className="text-sm font-semibold text-muted uppercase tracking-wider mb-1">{name}</h3>
        <div className="flex-1 flex items-center justify-center text-muted text-sm">No data</div>
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
  const headlineGrowthLabel = isQuarterly ? "QoQ" : "YoY";
  // Forecast labels are wider than plain years, so include the actual rendered
  // labels in the same width-aware sizing used by the historical cards.
  const periodAxis = financialPeriodAxisLayout(rows.map((row) => row.label), chartWidth, isQuarterly);
  const changeAngle = rows.length > 12 ? -65 : rows.length > 7 ? -55 : -45;
  // Only widen the y-domain when the TTM level falls outside the bars' own
  // range — a functional domain costs recharts its nice round ticks, so keep
  // the default auto axis whenever the overlay already fits.
  const vals = rows.map((r) => r.value).filter((v) => v != null);
  const ttmOutside =
    showTtm && vals.length > 0 &&
    (ttm > Math.max(0, ...vals) || ttm < Math.min(0, ...vals));

  return (
    <div className="bg-surface rounded-lg p-4 flex flex-col">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-semibold text-muted uppercase tracking-wider">{name}</h3>
        <div className="flex flex-col items-end text-[10px] gap-0.5">
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
          <div className="text-[10px] text-muted">{lastActual.label}</div>
        )}
      </div>
      <div
        ref={chartRef}
        className="mt-2"
        style={{ height: periodAxis.angle ? 192 : 176 }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rowsWithChange} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
            <XAxis
              dataKey="label"
              tick={
                <ChangeTick
                  changes={changes}
                  fontSize={periodAxis.fontSize}
                  changeFontSize={rows.length > 7 ? 9 : 11}
                  changeDecimals={rows.length > 7 ? 0 : 1}
                  periodAngle={periodAxis.angle}
                  changeAngle={changeAngle}
                  showChange={showChangeLine}
                />
              }
              tickLine={false}
              axisLine={{ stroke: GRID_STROKE }}
              interval={0}
              minTickGap={PERIOD_LABEL_MIN_GAP}
              height={showChangeLine ? (periodAxis.angle ? 76 : 62) : periodAxis.angle ? 50 : 20}
            />
            <YAxis
              tick={{ ...AXIS_TICK, fontSize: 10 }}
              tickFormatter={(v) => (isPerShare ? v.toFixed(1) : fmtCompact(v, "", 0))}
              tickLine={false}
              axisLine={false}
              width={48}
              // The TTM overlay isn't a bar, so when it exceeds every bar the
              // domain must be widened by hand (with 5% headroom) or the
              // overlay would draw past the plot area.
              domain={
                ttmOutside
                  ? [(dataMin) => Math.min(0, dataMin, ttm) * 1.05, (dataMax) => Math.max(0, dataMax, ttm) * 1.05]
                  : undefined
              }
            />
            <Tooltip
              cursor={{ fill: "rgba(0,0,0,0.04)" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload;
                return (
                  <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm shadow-lg">
                    <div className="text-muted">
                      {row.label}{row.isEstimate ? " · estimate" : " · actual"}
                    </div>
                    <div className="font-semibold text-ink">
                      {row.value == null
                        ? "—"
                        : isPerShare
                          ? `${cs}${row.value.toFixed(2)}`
                          : fmtCompact(row.value, cs)}
                    </div>
                    {row.isEstimate && row.low != null && row.high != null && (
                      <div className="text-muted text-[10px]">
                        Range {isPerShare
                          ? `${cs}${row.low.toFixed(2)}–${cs}${row.high.toFixed(2)}`
                          : `${fmtCompact(row.low, cs)}–${fmtCompact(row.high, cs)}`}
                      </div>
                    )}
                    {row.isEstimate && row.analysts > 0 && (
                      <div className="text-muted text-[10px]">{row.analysts} analysts</div>
                    )}
                    {row.growth != null && (
                      <div className={row.growth >= 0 ? "text-gain text-[10px]" : "text-loss text-[10px]"}>
                        {row.isEstimate ? "Fcst growth" : "YoY"} {fmtPct(row.growth, 2)}
                      </div>
                    )}
                    {isQuarterly && row.change != null && (
                      <div className={row.change >= 0 ? "text-gain text-[10px]" : "text-loss text-[10px]"}>
                        QoQ {fmtPct(row.change, 2)}
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
            <Bar dataKey="value" radius={[3, 3, 0, 0]}>
              {rows.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.isEstimate ? CATEGORICAL[0] : (d.value >= 0 ? GAIN_COLOR : LOSS_COLOR)}
                  fillOpacity={d.isEstimate ? 0.75 : 1}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center gap-3 mt-2 text-[10px] text-muted">
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 bg-gain rounded-sm" />Actual</span>
        {showTtm && (
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: TTM_COLOR }} />TTM</span>
        )}
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm opacity-75" style={{ backgroundColor: CATEGORICAL[0] }} />Estimate</span>
      </div>
    </div>
  );
}

function TargetRangeBar({ low, high, mean, median, current, cs }) {
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
          className="absolute top-0 h-2 rounded-full bg-gradient-to-r from-red-500/30 via-yellow-500/30 to-green-500/30"
          style={{ left: 0, right: 0 }}
        />
        {medianPct != null && (
          <div
            className="absolute top-[-2px] h-3 w-0.5 bg-slate-400"
            style={{ left: `calc(${medianPct}% - 1px)` }}
            title={`Median ${cs}${median.toFixed(2)}`}
          />
        )}
        <div
          className="absolute top-[-3px] h-4 w-0.5 bg-brand rounded"
          style={{ left: `calc(${meanPct}% - 1px)` }}
          title={`Mean ${cs}${mean.toFixed(2)}`}
        />
        <div
          className="absolute top-[-4px] h-5 w-1 bg-slate-800 rounded"
          style={{ left: `calc(${currentPct}% - 2px)` }}
          title={`Current ${cs}${current.toFixed(2)}`}
        />
      </div>
      <div className="flex items-center justify-between text-[10px] text-muted mt-2">
        <span>Low {cs}{low.toFixed(2)}</span>
        <span>High {cs}{high.toFixed(2)}</span>
      </div>
      <div className="flex items-center gap-3 text-[10px] text-muted mt-1">
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 bg-slate-800 rounded-sm" />Current</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 bg-brand rounded-sm" />Mean</span>
        {median != null && (
          <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 bg-slate-400 rounded-sm" />Median {cs}{median.toFixed(2)}</span>
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
const OWNERSHIP_RETAIL_COLOR = "#374151";

function OwnershipSection({ ownership, currencyCode }) {
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
        name: "Other institutions",
        pct: otherInst,
        color: OWNERSHIP_OTHER_COLOR,
      });
    }
  }
  if (insiderPct != null && insiderPct > 0) {
    slices.push({
      key: "insiders",
      kind: "insiders",
      name: "Insiders",
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
      name: "Retail / public float",
      pct: retailPct,
      color: OWNERSHIP_RETAIL_COLOR,
    });
  }

  return (
    <div>
      <h3 className="text-base font-semibold text-muted uppercase tracking-wider mb-3">
        Ownership Breakdown
      </h3>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="bg-surface rounded-lg p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <KpiBox
              size="sm"
              label="Institutions"
              value={instPct != null ? `${instPct.toFixed(1)}%` : "—"}
            />
            <KpiBox
              size="sm"
              label="Insiders"
              value={insiderPct != null ? `${insiderPct.toFixed(1)}%` : "—"}
            />
            <KpiBox
              size="sm"
              label="Top holders"
              value={
                ownership.institutions_count != null
                  ? `${ownership.institutions_count}`
                  : "—"
              }
            />
            <KpiBox
              size="sm"
              label="Short interest"
              value={shortPct != null ? `${(shortPct * 100).toFixed(2)}%` : "—"}
            />
          </div>
          {slices.length > 0 ? (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={slices}
                    dataKey="pct"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={110}
                    paddingAngle={1}
                    stroke={GRID_STROKE}
                    strokeWidth={1}
                    isAnimationActive={false}
                  >
                    {slices.map((s) => (
                      <Cell key={s.key} fill={s.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    cursor={{ fill: "rgba(0,0,0,0.04)" }}
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const row = payload[0].payload;
                      return (
                        <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm shadow-lg max-w-xs">
                          <div className="font-semibold text-ink truncate">{row.name}</div>
                          <div className="text-muted tabular-nums">
                            {row.pct.toFixed(2)}% of shares
                          </div>
                          {row.shares != null && (
                            <div className="text-muted text-[10px] tabular-nums">
                              {fmtCompact(row.shares, "")} shares
                              {row.value != null && (
                                <> · {fmtCompact(row.value, cs)}</>
                              )}
                            </div>
                          )}
                          {row.date && (
                            <div className="text-muted text-[10px] mt-0.5">
                              As of {row.date}
                            </div>
                          )}
                        </div>
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-72 flex items-center justify-center text-muted text-sm">
              No ownership data available.
            </div>
          )}
        </div>

        <div className="bg-surface rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-semibold text-muted uppercase tracking-wider flex items-center gap-1.5">
              <Users size={12} />
              Top Institutional Holders
            </h4>
            <span className="text-[10px] text-muted">% of shares · value</span>
          </div>
          {holders.length === 0 ? (
            <div className="text-muted text-sm">No institutional holders reported.</div>
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
// Shibui-backed sections: SEC filings, structured insider activity + cluster
// buys, beneficial ownership (13D/13G), earnings recap, historical
// valuation multiples, and (button-gated) political trades. Each fetches
// its own data independently (same pattern as DividendGrowthSection above)
// and renders nothing when Shibui doesn't cover the ticker, so these are
// silent no-ops for foreign/delisted/thinly-covered names.
// ---------------------------------------------------------------------------

function Chip({ children, title, tone = "neutral" }) {
  const toneClass =
    tone === "brand"
      ? "bg-brand/15 text-brand border-brand/30"
      : tone === "warn"
        ? "bg-amber-500/20 text-amber-600 border-amber-500/40"
        : tone === "danger"
          ? "bg-red-500/20 text-red-700 border-red-500/40"
          : "bg-slate-500/20 text-muted border-slate-500/40";
  return (
    <span
      title={title}
      className={`text-[9px] uppercase px-1.5 py-0.5 rounded border shrink-0 ${toneClass}`}
    >
      {children}
    </span>
  );
}

const FORM_TYPE_LABELS = {
  "10-K": "Annual report", "10-Q": "Quarterly report", "20-F": "Foreign annual report",
  "6-K": "Foreign current report", "8-K": "Current report", "DEF 14A": "Proxy statement",
  "DEF 14C": "Information statement", "SC 13G": "Passive stake (>5%)", "SC 13D": "Activist stake (>5%)",
  "S-1": "IPO registration", "S-3": "Shelf registration", "S-8": "Employee stock plan",
  "4": "Insider transaction", "3": "Initial insider ownership", "5": "Annual insider ownership",
};

const EIGHT_K_ITEM_LABELS = {
  "1.01": "Entry into agreement", "2.02": "Results of operations", "5.02": "Officer/director change",
  "7.01": "Reg FD disclosure", "8.01": "Other events", "9.01": "Financial exhibits",
};

// Multi-select transaction-type filter, shared by the yfinance and Shibui
// insider tables below. An empty `active` set means "no filter, show all" --
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

const FILTER_CHIP_TONE_ON = {
  buy: "bg-green-500/25 text-green-700 border-green-500/40",
  sell: "bg-red-500/25 text-red-700 border-red-500/40",
  neutral: "bg-slate-500/30 text-ink border-slate-500/50",
};
const FILTER_CHIP_OFF =
  "bg-surface-hover text-muted border-transparent hover:text-ink hover:bg-surface-card-elevated";

function TypeFilterChips({ options, active, onToggle, onReset, className = "" }) {
  if (!options || options.length <= 1) return null;
  const noFilter = active.size === 0;
  return (
    <div className={`flex items-center gap-1.5 flex-wrap ${className}`}>
      <button
        type="button"
        onClick={onReset}
        aria-pressed={noFilter}
        className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full border transition-colors ${
          noFilter ? "bg-brand/15 text-brand border-brand/30" : FILTER_CHIP_OFF
        }`}
      >
        All
      </button>
      {options.map((opt) => {
        const isOn = noFilter || active.has(opt.value);
        return (
          <button
            key={opt.value}
            type="button"
            title={opt.description}
            aria-pressed={isOn}
            onClick={() => onToggle(opt.value)}
            className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full border transition-colors ${
              isOn ? FILTER_CHIP_TONE_ON[opt.tone] || FILTER_CHIP_TONE_ON.neutral : FILTER_CHIP_OFF
            }`}
          >
            {opt.label}
            <span className="ml-1 font-normal normal-case opacity-60">{opt.count}</span>
          </button>
        );
      })}
    </div>
  );
}

const YF_TYPE_META = {
  buy: { label: "Buy", tone: "buy", description: "Insider purchased shares in the open market." },
  sell: { label: "Sell", tone: "sell", description: "Insider sold shares in the open market." },
  other: {
    label: "Other",
    tone: "neutral",
    description: "Grants, option exercises, gifts, and other non-market Form 4 transactions.",
  },
};

export function ShibuiFilingsSection({ ticker }) {
  const [expanded, setExpanded] = useState(false);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["shibui-filings", ticker],
    queryFn: () => fetchShibuiFilings(ticker),
    staleTime: 60 * 60 * 1000,
    enabled: !!ticker,
    retry: false,
  });

  if (isLoading || isError || !data?.filings?.length) return null;

  return (
    <div>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 mb-3 group"
      >
        <h3 className="text-base font-semibold text-muted uppercase tracking-wider group-hover:text-ink transition-colors">
          SEC Filings
        </h3>
        <span className="text-[10px] text-muted">({data.filings.length})</span>
        {expanded ? (
          <ChevronUp size={14} className="text-muted group-hover:text-ink transition-colors" />
        ) : (
          <ChevronDown size={14} className="text-muted group-hover:text-ink transition-colors" />
        )}
      </button>
      {expanded && (
        <div className="bg-surface rounded-lg overflow-hidden">
          <div className="grid grid-cols-[5.5rem_1fr_3.5rem] gap-3 px-4 py-2 border-b border-surface-border text-[10px] uppercase tracking-wider text-muted font-medium">
            <span>Date</span>
            <span>Type</span>
            <span className="text-right">Link</span>
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {data.filings.map((f, i) => (
              <li
                key={`${f.filing_url}-${i}`}
                className="grid grid-cols-[5.5rem_1fr_3.5rem] gap-3 items-center px-4 py-2 text-sm border-b border-surface-border last:border-0 hover:bg-surface-hover"
              >
                <span className="tabular-nums text-muted">{f.filing_date}</span>
                <span className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-ink font-medium">{f.raw_form_type}</span>
                  <span className="text-muted">{FORM_TYPE_LABELS[f.form_type] || ""}</span>
                  {f.is_amendment && <Chip>Amended</Chip>}
                  {(f.items || []).map((code) => (
                    <Chip key={code} tone="brand" title={EIGHT_K_ITEM_LABELS[code] || code}>
                      {code}
                    </Chip>
                  ))}
                </span>
                <a
                  href={f.filing_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-right text-brand hover:underline inline-flex items-center justify-end gap-0.5"
                >
                  View <ExternalLink size={10} />
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

const TX_CODE_LABELS = {
  P: "Open-market buy", S: "Open-market sale", A: "Grant/award", D: "Disposition to issuer",
  F: "Tax-withholding disposition", M: "Option/derivative exercise", G: "Gift",
  C: "Conversion of derivative", X: "In-the-money option exercise",
};

function ShibuiInsiderActivitySection({ ticker, currencyCode }) {
  const cs = currencySymbol(currencyCode);
  const [activeTypes, setActiveTypes] = useState(() => new Set());
  const { data, isLoading, isError } = useQuery({
    queryKey: ["shibui-insiders", ticker],
    queryFn: () => fetchShibuiInsiders(ticker),
    staleTime: 30 * 60 * 1000,
    enabled: !!ticker,
    retry: false,
  });

  if (isLoading || isError || !data?.transactions?.length) return null;
  const clusters = data.cluster_buys || [];

  const codeCounts = data.transactions.reduce((acc, t) => {
    acc[t.tx_code] = (acc[t.tx_code] || 0) + 1;
    return acc;
  }, {});
  const codeOrder = [...new Set([...Object.keys(TX_CODE_LABELS), ...Object.keys(codeCounts)])];
  const typeOptions = codeOrder
    .filter((code) => codeCounts[code])
    .map((code) => ({
      value: code,
      label: code,
      count: codeCounts[code],
      description: TX_CODE_LABELS[code] || "SEC Form 4/5 transaction code",
      tone: code === "P" ? "buy" : code === "S" ? "sell" : "neutral",
    }));
  const toggleType = (value) =>
    setActiveTypes((prev) => toggleSetValue(prev, value, typeOptions.length));
  const visibleTransactions =
    activeTypes.size === 0
      ? data.transactions
      : data.transactions.filter((t) => activeTypes.has(t.tx_code));

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
          Insider Activity (SEC)
        </h3>
        <span className="text-[10px] text-muted">Form 4/5 · last {data.months} months</span>
      </div>

      <TypeFilterChips
        options={typeOptions}
        active={activeTypes}
        onToggle={toggleType}
        onReset={() => setActiveTypes(new Set())}
        className="mb-3"
      />

      {clusters.length > 0 && (
        <div className="mb-3 space-y-2">
          {clusters.map((c, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm"
            >
              <Flame size={14} className="text-amber-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-ink">Cluster buy detected</span>
                <span className="text-muted">
                  {" "}— {c.buyers.length} insiders bought between {c.start} and {c.end}:{" "}
                </span>
                <span className="text-ink">{c.buyers.join(", ")}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-surface rounded-lg overflow-hidden">
        <div className="grid grid-cols-[1fr_4rem_5rem_6rem_5rem] gap-3 px-4 py-2 border-b border-surface-border text-[10px] uppercase tracking-wider text-muted font-medium">
          <span>Insider</span>
          <span className="text-center">Code</span>
          <span className="text-right">Shares</span>
          <span className="text-right">Value</span>
          <span className="text-right">Date</span>
        </div>
        <ul className="max-h-96 overflow-y-auto">
          {!visibleTransactions.length && (
            <li className="px-4 py-6 text-center text-sm text-muted">
              No transactions match the selected filter.
            </li>
          )}
          {visibleTransactions.map((t, i) => {
            const isBuy = t.direction === "buy";
            const rowBg = isBuy ? "bg-green-500/10 hover:bg-green-500/15" : "bg-red-500/10 hover:bg-red-500/15";
            return (
              <li
                key={i}
                className={`grid grid-cols-[1fr_4rem_5rem_6rem_5rem] gap-3 items-center px-4 py-2 text-sm ${rowBg}`}
              >
                <div className="min-w-0">
                  <div className="truncate text-ink font-medium">{t.owner_canonical_name || "—"}</div>
                  <div className="flex items-center gap-1 flex-wrap mt-0.5">
                    {t.officer_title && <span className="text-[10px] text-muted">{t.officer_title}</span>}
                    {t.is_director && <Chip>Director</Chip>}
                    {t.is_officer && <Chip>Officer</Chip>}
                    {t.is_ten_pct_owner && <Chip>10%+ owner</Chip>}
                    {t.is_10b5_1 && <Chip title="Pre-scheduled 10b5-1 trading plan">10b5-1</Chip>}
                    {t.is_gift && <Chip>Gift</Chip>}
                    {t.is_tax_withholding && <Chip>Tax withholding</Chip>}
                    {t.is_auto_plan && <Chip>Auto plan</Chip>}
                    {t.is_avg_price && <Chip title="Executed at a volume-weighted average price">Avg price</Chip>}
                  </div>
                </div>
                <span className="text-center">
                  <span
                    title={TX_CODE_LABELS[t.tx_code] || t.tx_code}
                    className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border ${
                      isBuy
                        ? "bg-green-500/25 text-green-700 border-green-500/40"
                        : "bg-red-500/25 text-red-700 border-red-500/40"
                    }`}
                  >
                    {t.tx_code}
                  </span>
                </span>
                <span className="text-right tabular-nums text-ink">
                  {t.shares != null ? Math.round(t.shares).toLocaleString() : "—"}
                </span>
                <span className="text-right tabular-nums text-muted">
                  {t.value ? fmtCompact(t.value, cs) : "—"}
                </span>
                <span className="text-right tabular-nums text-muted">{t.tx_date}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

// Shows the shares-owned/%-of-class pair once known (either attached eagerly
// by the backend for the 10 most recent filings, or fetched lazily below).
function OwnershipStat({ sharesOwned, percentOfClass }) {
  if (sharesOwned == null && percentOfClass == null) {
    return <span className="text-[11px] text-muted">Podíl nedostupný</span>;
  }
  return (
    <span className="text-[11px] text-muted tabular-nums">
      {sharesOwned != null ? `${Math.round(sharesOwned).toLocaleString()} ks` : "—"}
      {percentOfClass != null ? ` · ${percentOfClass.toFixed(1)} %` : ""}
    </span>
  );
}

// Filings past the backend's eager top-10 cutoff carry accession_number/
// filer_cik/primary_document but not shares_owned/percent_of_class -- this
// fetches that detail from EDGAR on click rather than up front for all 50.
function OwnershipDetail({ stake }) {
  const hasEagerData = stake.shares_owned !== undefined || stake.percent_of_class !== undefined;
  const canFetch = !!(stake.accession_number && stake.filer_cik && stake.primary_document);
  const detailQ = useQuery({
    queryKey: ["shibui-ownership-detail", stake.accession_number],
    queryFn: () => fetchShibuiOwnershipDetail(stake.filer_cik, stake.accession_number, stake.primary_document),
    enabled: false,
    staleTime: Infinity,
  });

  if (hasEagerData) {
    return <OwnershipStat sharesOwned={stake.shares_owned} percentOfClass={stake.percent_of_class} />;
  }
  if (!canFetch) return null;
  if (detailQ.data) {
    return <OwnershipStat sharesOwned={detailQ.data.shares_owned} percentOfClass={detailQ.data.percent_of_class} />;
  }
  if (detailQ.isFetching) {
    return <span className="text-[11px] text-muted">Načítám…</span>;
  }
  return (
    <button
      type="button"
      onClick={() => detailQ.refetch()}
      className="text-[11px] text-brand hover:underline"
    >
      Zobrazit podíl
    </button>
  );
}

export function ShibuiOwnershipFilingsSection({ ticker }) {
  const stakesQ = useQuery({
    queryKey: ["shibui-activist-stakes", ticker],
    queryFn: () => fetchShibuiActivistStakes(ticker),
    staleTime: 60 * 60 * 1000,
    enabled: !!ticker,
    retry: false,
  });
  const investorsQ = useQuery({
    queryKey: ["shibui-strategic-investors", ticker],
    queryFn: () => fetchShibuiStrategicInvestors(ticker),
    staleTime: 60 * 60 * 1000,
    enabled: !!ticker,
    retry: false,
  });

  const stakes = stakesQ.data?.stakes || [];
  const investors = investorsQ.data?.investors || [];
  if (!stakes.length && !investors.length) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
        Beneficial Ownership (13D/13G)
      </h3>

      {investors.length > 0 && (
        <div className="bg-surface rounded-lg p-4">
          <h4 className="text-sm font-semibold text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Landmark size={12} /> Corporate strategic investors
          </h4>
          <ul className="space-y-1.5">
            {investors.map((inv, i) => (
              <li
                key={i}
                className="flex items-center justify-between gap-3 text-sm py-1 border-b border-surface-border last:border-0"
              >
                <span className="text-ink truncate">
                  {inv.filer_name}{" "}
                  <TickerLink ticker={inv.filer_ticker} className="text-brand font-mono text-[11px]" />
                </span>
                <span className="flex items-center gap-2 text-muted shrink-0">
                  <Chip>{inv.schedule_type}</Chip>
                  <span className="tabular-nums">{inv.filing_date}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {stakes.length > 0 && (
        <div className="bg-surface rounded-lg p-4">
          <h4 className="text-sm font-semibold text-muted uppercase tracking-wider mb-2">
            13D/13G filers (up to 50 most recent)
          </h4>
          <ul className="max-h-64 overflow-y-auto space-y-1">
            {stakes.map((s, i) => (
              <li key={i} className="py-1 border-b border-surface-border last:border-0">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-ink truncate">{s.filer_canonical_name || s.filer_name}</span>
                  <span className="flex items-center gap-2 text-muted shrink-0">
                    {s.filer_is_activist && <Chip tone="danger">Activist</Chip>}
                    <Chip tone={s.schedule_type === "13D" ? "warn" : "neutral"}>{s.schedule_type}</Chip>
                    <span className="tabular-nums">{s.filing_date}</span>
                  </span>
                </div>
                <div className="mt-0.5">
                  <OwnershipDetail stake={s} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

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
  const common = { fill, stroke: "#fff", strokeWidth: 1, onClick, style: { cursor: "pointer" } };
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
function formatTradeTooltip(t, cs) {
  const name = t.politician_canonical || t.politician;
  const midValue = (Number(t.amount_min) + Number(t.amount_max)) / 2;
  const lines = [name, t.transaction_date];

  if (Number.isFinite(midValue) && t.tradePrice > 0) {
    const estShares = midValue / t.tradePrice;
    lines.push(`~${cs}${Math.round(midValue).toLocaleString()} · ~${Math.round(estShares).toLocaleString()} sh`);
    if (t.isBuy && t.currentPrice != null) {
      const pnlDollar = estShares * (t.currentPrice - t.tradePrice);
      const pnlPct = (t.currentPrice / t.tradePrice - 1) * 100;
      const sign = pnlDollar >= 0 ? "+" : "";
      lines.push(`Unrealized: ${sign}${cs}${Math.round(pnlDollar).toLocaleString()} (${sign}${pnlPct.toFixed(1)}%)`);
    } else if (!t.isBuy) {
      lines.push("Position sold — no unrealized P&L");
    }
  }
  return lines.join("\n");
}

function PoliticalTradesChart({ ticker, trades, currencyCode, currentPrice, onSelect }) {
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
    <div className="bg-surface rounded-lg p-4 mb-3">
      <h4 className="text-sm font-semibold text-muted uppercase tracking-wider mb-2">
        Trades on price chart
      </h4>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="date" tick={{ ...AXIS_TICK, fontSize: 12 }} tickFormatter={(d) => String(d).slice(0, 7)} minTickGap={40} />
            <YAxis tick={{ ...AXIS_TICK, fontSize: 12 }} width={52} domain={["auto", "auto"]} tickFormatter={(v) => `${cs}${v}`} />
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
                    tooltip={formatTradeTooltip(d, cs)}
                    onClick={() => onSelect(d)}
                  />
                )}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[10px] text-muted mt-2">
        ● stock trade · ◆ option-flagged trade · green = buy, red = sell — hover a marker for
        name/date/value/shares/unrealized P&amp;L, click it (or a table row below) for full details.
      </p>
    </div>
  );
}

function TradeDetailCard({ trade, onClose }) {
  const isBuy = isPoliticalTradeBuy(trade);
  const reportLag = daysBetween(trade.transaction_date, trade.filed_date);

  return (
    <div className="bg-surface rounded-lg p-4 mb-3 border border-brand/30">
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
        <button onClick={onClose} className="text-muted hover:text-ink text-sm">
          ✕
        </button>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
        <div>
          <div className="text-[10px] text-muted uppercase tracking-wider">Type</div>
          <div className={`text-sm font-semibold ${isBuy ? "text-gain" : "text-loss"}`}>
            {isBuy ? "BUY" : "SELL"}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-muted uppercase tracking-wider">Amount</div>
          <div className="text-sm text-ink tabular-nums">
            ${Number(trade.amount_min).toLocaleString()}–${Number(trade.amount_max).toLocaleString()}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-muted uppercase tracking-wider">Owner</div>
          <div className="text-sm text-ink">{trade.owner_code || "—"}</div>
        </div>
        <div>
          <div className="text-[10px] text-muted uppercase tracking-wider">Transaction date</div>
          <div className="text-sm text-ink tabular-nums">{trade.transaction_date}</div>
        </div>
      </div>
      {trade.filed_date && (
        <p className="text-[11px] text-muted mt-2">
          Reported {trade.filed_date}
          {reportLag != null && reportLag > 0 && ` — ${reportLag} day${reportLag === 1 ? "" : "s"} after the trade`}
        </p>
      )}
      {trade.is_likely_option && (
        <div className="mt-3 pt-3 border-t border-surface-border">
          <Chip tone="warn">Options trade</Chip>
          <p className="text-[11px] text-muted mt-1.5">{trade.asset_name}</p>
          <p className="text-[10px] text-muted mt-1">
            Exact strike/expiration aren't in the data available here — can't automatically tell
            if this is a "deep ITM" style bet.
          </p>
        </div>
      )}
    </div>
  );
}

function PoliticalTradesSection({ ticker, currencyCode, currentPrice }) {
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
        <h3 className="text-base font-semibold text-muted uppercase tracking-wider">Political Trades</h3>
        {!enabled && (
          <button
            onClick={() => setEnabled(true)}
            className="text-sm px-3 py-1.5 rounded-md bg-surface hover:bg-surface-hover border border-surface-border text-ink transition-colors"
          >
            Load political trades
          </button>
        )}
      </div>

      {!enabled && (
        <p className="text-sm text-muted">
          Congressional (STOCK Act) trades referencing this ticker. Loaded only on request —
          never fetched automatically.
        </p>
      )}

      {enabled && isLoading && <p className="text-sm text-muted">Loading…</p>}

      {enabled && isError && (
        <p className="text-sm text-muted">
          {error?.response?.status === 503
            ? "Political trades aren't configured — set ALPHA_VANTAGE_API_KEY on the backend to enable this."
            : "Could not load political trades."}
        </p>
      )}

      {enabled && data && data.trades.length === 0 && (
        <p className="text-sm text-muted">No disclosed congressional trades found for this ticker.</p>
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
          <div className="bg-surface rounded-lg overflow-hidden">
            <div className="grid grid-cols-[1fr_3.5rem_3.5rem_9rem_5.5rem] gap-3 px-4 py-2 border-b border-surface-border text-[10px] uppercase tracking-wider text-muted font-medium">
              <span>Politician</span>
              <span className="text-center">Party</span>
              <span className="text-center">Type</span>
              <span className="text-right">Amount</span>
              <span className="text-right">Date</span>
            </div>
            <ul className="max-h-96 overflow-y-auto">
              {data.trades.map((t, i) => {
                const isBuy = isPoliticalTradeBuy(t);
                return (
                  <li
                    key={i}
                    onClick={() => setSelected(t)}
                    className="grid grid-cols-[1fr_3.5rem_3.5rem_9rem_5.5rem] gap-3 items-center px-4 py-2 text-sm border-b border-surface-border last:border-0 hover:bg-surface-hover cursor-pointer"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-ink font-medium">
                        {t.politician_canonical || t.politician}
                      </div>
                      <div className="text-[10px] text-muted truncate">
                        {t.chamber} · {t.state}
                        {t.state_district ? ` (${t.state_district})` : ""} · {t.owner_code}
                        {t.is_likely_option && <span className="ml-1 text-amber-500">◆ Option</span>}
                      </div>
                    </div>
                    <span className="text-center text-muted">{t.party}</span>
                    <span
                      className={`text-center text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border ${
                        isBuy
                          ? "bg-green-500/25 text-green-700 border-green-500/40"
                          : "bg-red-500/25 text-red-700 border-red-500/40"
                      }`}
                    >
                      {isBuy ? "BUY" : "SELL"}
                    </span>
                    <span className="text-right tabular-nums text-muted">
                      ${Number(t.amount_min).toLocaleString()}–${Number(t.amount_max).toLocaleString()}
                    </span>
                    <span className="text-right tabular-nums text-muted">{t.transaction_date}</span>
                  </li>
                );
              })}
            </ul>
            {data.truncated && (
              <div className="px-4 py-2 text-[10px] text-muted border-t border-surface-border">
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

  return (
    <div>
      <h3 className="text-base font-semibold text-muted uppercase tracking-wider mb-3">Earnings</h3>

      <div className="bg-surface rounded-lg p-4 mb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="text-[10px] text-muted uppercase tracking-wider">
              Latest report · Q{latest.quarter} {latest.year} · {latest.report_date}
            </div>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span
                className={`text-sm font-semibold uppercase px-2 py-0.5 rounded border ${
                  beat
                    ? "bg-green-500/25 text-green-700 border-green-500/40"
                    : "bg-red-500/25 text-red-700 border-red-500/40"
                }`}
              >
                {beat ? "Beat" : "Miss"}
              </span>
              <span className="text-base text-ink tabular-nums">
                EPS {cs}
                {latest.eps_actual?.toFixed(2)} vs {cs}
                {latest.eps_estimate?.toFixed(2)} est.
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
              8-K press release <ExternalLink size={10} />
            </a>
          )}
        </div>
        {latest.revenue_actual != null && (
          <div className="text-sm text-muted mt-2 tabular-nums">
            Revenue: {fmtCompact(latest.revenue_actual, cs)}
            {data.latest_revenue_estimate != null && (
              <>
                {" "}
                vs est. {fmtCompact(data.latest_revenue_estimate, cs)}
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

      <div className="bg-surface rounded-lg p-4 mb-3">
        <h4 className="text-sm font-semibold text-muted uppercase tracking-wider mb-2">
          EPS surprise history
        </h4>
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="label" tick={{ ...AXIS_TICK, fontSize: 12 }} minTickGap={16} />
              <YAxis tick={{ ...AXIS_TICK, fontSize: 12 }} width={36} tickFormatter={(v) => `${v}%`} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${v?.toFixed(1)}%`, "Surprise"]} />
              <Bar dataKey="surprise" radius={[3, 3, 0, 0]}>
                {chartData.map((d, i) => (
                  <Cell key={i} fill={d.surprise >= 0 ? GAIN_COLOR : LOSS_COLOR} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {recentBuyback && (
        <div className="bg-surface rounded-lg p-4">
          <h4 className="text-sm font-semibold text-muted uppercase tracking-wider mb-1">
            Buyback trend
          </h4>
          <p className="text-sm text-muted">
            Q{recentBuyback.quarter} {recentBuyback.year}: net{" "}
            {recentBuyback.equity_issuance_repayment < 0 ? "repurchase" : "issuance"} of{" "}
            {fmtCompact(Math.abs(recentBuyback.equity_issuance_repayment), cs)}
          </p>
        </div>
      )}
    </div>
  );
}

const VALUATION_MULTIPLES = [
  { key: "trailing_pe", label: "P/E", pctileKey: "pe_pctile", fmt: (v) => v?.toFixed(1) },
  { key: "ev_ebitda", label: "EV/EBITDA", pctileKey: "ev_ebitda_pctile", fmt: (v) => v?.toFixed(1) },
  { key: "price_to_sales", label: "P/S", pctileKey: "ps_pctile", fmt: (v) => v?.toFixed(2) },
  { key: "price_to_cash_flow", label: "P/FCF", pctileKey: "pfcf_pctile", fmt: (v) => v?.toFixed(1) },
  { key: "price_to_book", label: "P/B", pctileKey: "pb_pctile", fmt: (v) => v?.toFixed(2) },
];

const VALUATION_RANGES = [
  { label: "1Y", years: 1 },
  { label: "5Y", years: 5 },
  { label: "10Y", years: 10 },
  { label: "Max", years: 33 },
];

function ordinal(n) {
  const suffixes = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${suffixes[(v - 20) % 10] || suffixes[v] || suffixes[0]}`;
}

function ValuationHistorySection({ ticker }) {
  const [range, setRange] = useState(VALUATION_RANGES[2]);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["shibui-valuation-history", ticker, range.years],
    queryFn: () => fetchShibuiValuationHistory(ticker, range.years),
    staleTime: 60 * 60 * 1000,
    enabled: !!ticker,
    retry: false,
  });

  if (isError) return null;
  const points = data?.points || [];

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
          Valuation History
          {data?.granularity && (
            <span className="ml-2 text-muted normal-case tracking-normal">
              · {data.granularity} points
            </span>
          )}
        </h3>
        <div className="inline-flex bg-surface rounded-md p-0.5 text-sm">
          {VALUATION_RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => setRange(r)}
              className={`px-2.5 py-1 rounded transition-colors ${
                range.label === r.label ? "bg-brand text-white" : "text-muted hover:text-ink"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {!isLoading && points.length === 0 && (
        <p className="text-sm text-muted">No valuation history available.</p>
      )}

      {points.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
          {VALUATION_MULTIPLES.map((m) => (
            <ValuationSparkline key={m.key} multiple={m} points={points} />
          ))}
        </div>
      )}
    </div>
  );
}

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

function ValuationSparkline({ multiple, points }) {
  const [expanded, setExpanded] = useState(false);
  const series = points
    .map((p) => ({ bucket: p.bucket, value: p[multiple.key] }))
    .filter((p) => p.value != null);

  if (!series.length) {
    return (
      <div className="bg-surface rounded-lg p-3">
        <div className="text-[10px] text-muted uppercase tracking-wider">{multiple.label}</div>
        <div className="text-sm text-muted mt-2">No data</div>
      </div>
    );
  }

  const last = points[points.length - 1];
  const currentValue = last?.[multiple.key];
  const currentPctile = last?.[multiple.pctileKey];
  const sortedValues = series.map((p) => p.value).slice().sort((a, b) => a - b);
  const bandLo = sortedValues[Math.max(0, Math.round(0.1 * (sortedValues.length - 1)))];
  const bandHi = sortedValues[Math.max(0, Math.round(0.9 * (sortedValues.length - 1)))];
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
  const expandedYAxisWidth = estimateAxisWidth([minValue, maxValue].map((v) => multiple.fmt(v)), 7, 44, 14);

  return (
    <div
      className="bg-surface rounded-lg p-3 cursor-pointer transition-colors hover:bg-surface-hover"
      onClick={() => setExpanded(true)}
      title="Click to expand"
    >
      <div className="text-[10px] text-muted uppercase tracking-wider">{multiple.label}</div>
      <div className="text-xl font-bold tabular-nums text-ink">
        {currentValue != null ? multiple.fmt(currentValue) : "—"}
      </div>
      <div className="text-[10px] text-muted mb-1">
        {currentPctile != null
          ? `${ordinal(Math.round(currentPctile * 100))} percentile`
          : "—"}
      </div>
      <div className="h-16">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 6, right: 2, left: 0, bottom: 6 }}>
            <YAxis
              domain={[minValue, maxValue]}
              ticks={yTicks}
              interval={0}
              tick={AXIS_TICK}
              width={yAxisWidth}
              tickFormatter={(v) => multiple.fmt(v)}
            />
            <ReferenceArea y1={bandLo} y2={bandHi} fill={NEUTRAL_COLOR} fillOpacity={0.15} strokeWidth={0} />
            <Area
              type="monotone"
              dataKey="value"
              stroke={CATEGORICAL[0]}
              strokeWidth={1.5}
              fill="none"
              isAnimationActive={false}
              dot={false}
            />
            <Tooltip content={<BucketDateTooltip valueFormatter={multiple.fmt} />} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {expanded && (
        <div
          className="fixed inset-0 z-50 bg-surface flex flex-col p-6 sm:p-10 cursor-default"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => setExpanded(false)}
            className="absolute top-4 right-4 sm:top-6 sm:right-6 p-2 rounded-full text-muted hover:text-ink hover:bg-surface-hover transition-colors"
          >
            <X size={22} />
          </button>
          <div className="mb-4 px-12">
            <h3 className="text-base font-bold text-muted uppercase tracking-wider text-center">
              {multiple.label} Valuation History
            </h3>
            <div className="text-3xl font-bold tabular-nums text-ink mt-1 text-center">
              {currentValue != null ? multiple.fmt(currentValue) : "—"}
              {currentPctile != null && (
                <span className="text-sm font-normal text-muted ml-2">
                  {ordinal(Math.round(currentPctile * 100))} percentile
                </span>
              )}
            </div>
          </div>
          <div className="flex-1 min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series} margin={{ top: 10, right: 24, left: 10, bottom: 10 }}>
                <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="bucket"
                  tick={{ ...AXIS_TICK, fontSize: 12 }}
                  tickFormatter={(b) => formatShortDate(b, { month: "short", year: "numeric" })}
                  minTickGap={40}
                />
                <YAxis
                  domain={[minValue, maxValue]}
                  tick={{ ...AXIS_TICK, fontSize: 12 }}
                  width={expandedYAxisWidth}
                  tickFormatter={(v) => multiple.fmt(v)}
                />
                <ReferenceArea y1={bandLo} y2={bandHi} fill={NEUTRAL_COLOR} fillOpacity={0.15} strokeWidth={0} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={CATEGORICAL[0]}
                  strokeWidth={2}
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
      )}
    </div>
  );
}

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatWeekTick(ts) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return MONTH_LABELS[d.getUTCMonth()];
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
  const minClose = closes.length ? Math.min(...closes) : 0;
  const maxClose = closes.length ? Math.max(...closes) : 1;
  const pad = (maxClose - minClose) * 0.1 || maxClose * 0.05 || 1;

  return (
    <div>
      <h3 className="text-base font-semibold text-muted uppercase tracking-wider mb-3">
        Insider Trading Volume
      </h3>
      <div className="bg-surface rounded-lg p-4">
        <div className="relative h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
              <XAxis
                dataKey="x"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={formatWeekTick}
                tick={{ ...AXIS_TICK, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: GRID_STROKE }}
              />
              <YAxis
                domain={[Math.max(0, minClose - pad), maxClose + pad]}
                tick={{ ...AXIS_TICK, fontSize: 11 }}
                tickFormatter={(v) => `${cs}${v.toFixed(2)}`}
                tickLine={false}
                axisLine={false}
                width={64}
              />
              <Line
                type="monotone"
                dataKey="y"
                stroke={CATEGORICAL[0]}
                strokeWidth={1.5}
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
              <Legend
                verticalAlign="top"
                align="left"
                height={20}
                iconType="square"
                iconSize={9}
                wrapperStyle={{ paddingBottom: 4 }}
                formatter={(v) => <span className="text-[10px] text-muted uppercase tracking-wider">{v}</span>}
                payload={[
                  { value: "Close Price", type: "line", color: CATEGORICAL[0] },
                  { value: "Insider Buys", type: "square", color: GAIN_COLOR },
                  { value: "Insider Sells", type: "square", color: LOSS_COLOR },
                ]}
              />
            </ComposedChart>
          </ResponsiveContainer>
          {hoveredDot && (
            <div
              className="absolute z-10 pointer-events-none bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-sm shadow-lg space-y-0.5 whitespace-nowrap"
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
                {hoveredDot.shares != null ? fmtCompact(hoveredDot.shares, "") : "—"} sh
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

export function InsiderTransactionsSection({ transactions, currencyCode, currentPrice }) {
  const [activeTypes, setActiveTypes] = useState(() => new Set());
  const INSIDER_ROWS_PER_PAGE = 25;
  const [insiderPage, setInsiderPage] = useState(0);
  if (!transactions || !transactions.length) return null;
  const cs = currencySymbol(currencyCode);
  const gridCols = "grid-cols-[1fr_auto_auto_auto_auto_auto_auto]";

  const typeCounts = transactions.reduce((acc, t) => {
    const key = insiderTypeOf(t);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const typeOptions = Object.keys(YF_TYPE_META)
    .filter((key) => typeCounts[key])
    .map((key) => ({ value: key, count: typeCounts[key], ...YF_TYPE_META[key] }));
  const toggleType = (value) =>
    setActiveTypes((prev) => toggleSetValue(prev, value, typeOptions.length));
  const visibleTransactions =
    activeTypes.size === 0 ? transactions : transactions.filter((t) => activeTypes.has(insiderTypeOf(t)));

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
        <h3 className="text-base font-semibold text-muted uppercase tracking-wider">
          Latest Insider Transactions
        </h3>
        <TypeFilterChips
          options={typeOptions}
          active={activeTypes}
          onToggle={toggleType}
          onReset={() => setActiveTypes(new Set())}
        />
      </div>
      <div className="bg-surface rounded-lg overflow-x-auto">
        <div className={`grid ${gridCols} min-w-[700px] gap-3 px-4 py-2 border-b border-surface-border text-[10px] uppercase tracking-wider text-muted font-medium`}>
          <span>Insider</span>
          <span className="w-32 text-left">Type · Transaction</span>
          <span className="w-20 text-right">Shares</span>
          <span className="w-20 text-right">Price</span>
          <span className="w-24 text-right">Value</span>
          <span className="w-24 text-right" title="Unrealized P&L vs current price">P&amp;L (vs now)</span>
          <span className="w-20 text-right">Date</span>
        </div>
        <ul className="min-w-[700px]">
          {!pagedTransactions.length && (
            <li className="px-4 py-6 text-center text-sm text-muted">
              No transactions match the selected filter.
            </li>
          )}
          {pagedTransactions.map((t, i) => {
            const isBuy = t.side === "buy";
            const isSell = t.side === "sell";
            const rowBg = isBuy
              ? "bg-green-500/10 hover:bg-green-500/15"
              : isSell
                ? "bg-red-500/10 hover:bg-red-500/15"
                : "hover:bg-surface-hover";
            const sideColor = isBuy
              ? "text-green-700"
              : isSell
                ? "text-red-700"
                : "text-muted";
            const sideLabel = isBuy ? "BUY" : isSell ? "SELL" : "OTHER";
            const sidePill = isBuy
              ? "bg-green-500/25 text-green-700 border-green-500/40"
              : isSell
                ? "bg-red-500/25 text-red-700 border-red-500/40"
                : "bg-slate-500/20 text-muted border-slate-500/40";
            const Icon = isBuy ? ArrowUpRight : isSell ? ArrowDownRight : null;

            // Derive the executed price from value / shares. yfinance reports
            // both as positive magnitudes so this stays valid for either side.
            const shares = t.shares != null ? Math.abs(t.shares) : null;
            const value = t.value != null ? Math.abs(t.value) : null;
            const pricePerShare =
              shares && shares > 0 && value != null ? value / shares : null;

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
                className={`grid ${gridCols} gap-3 items-center px-4 py-2 border-b border-surface-border last:border-0 text-sm transition-colors ${rowBg}`}
              >
                <div className="min-w-0">
                  <div className="text-ink truncate" title={t.insider || ""}>
                    {t.insider || "—"}
                  </div>
                  {t.position && (
                    <div className="text-[10px] text-muted truncate" title={t.position}>
                      {t.position}
                    </div>
                  )}
                </div>
                <div className="w-32 flex items-center gap-1.5">
                  <span
                    className={`text-[10px] font-bold tracking-wider px-1.5 py-0.5 rounded border ${sidePill}`}
                  >
                    {sideLabel}
                  </span>
                  <span
                    className={`truncate text-[11px] ${sideColor}`}
                    title={t.transaction || ""}
                  >
                    {t.transaction || "—"}
                  </span>
                </div>
                <div className="w-20 text-right tabular-nums text-ink flex items-center justify-end gap-1">
                  {Icon && <Icon size={11} className={sideColor} />}
                  {shares != null ? fmtCompact(shares, "") : "—"}
                </div>
                <div
                  className="w-20 text-right tabular-nums text-ink"
                  title={
                    pricePerShare != null
                      ? `${cs}${pricePerShare.toFixed(4)} / share`
                      : ""
                  }
                >
                  {pricePerShare != null ? `${cs}${pricePerShare.toFixed(2)}` : "—"}
                </div>
                <div className={`w-24 text-right tabular-nums font-medium ${sideColor}`}>
                  {value != null ? fmtCompact(value, cs) : "—"}
                </div>
                <div
                  className={`w-24 text-right tabular-nums font-medium ${pnlColor}`}
                  title={
                    pnl != null
                      ? `Buy held to now: ${pnlPrefix}${fmtCompact(Math.abs(pnl), cs)}${pnlPct != null ? ` (${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(1)}%)` : ""}`
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
                        <div className="text-[10px] font-normal opacity-80">
                          {pnlPct >= 0 ? "+" : ""}
                          {pnlPct.toFixed(1)}%
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div className="w-20 text-right text-muted tabular-nums text-[11px]">
                  {t.date || "—"}
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
            ariaLabel="Insider transactions pages"
          />
        </div>
      </div>
      <div className="text-[10px] text-muted mt-2">
        Source: yfinance · transaction types from Form 4 filings · P&amp;L shown
        for buys only (held-to-now mark vs. current price).
      </div>
    </div>
  );
}
