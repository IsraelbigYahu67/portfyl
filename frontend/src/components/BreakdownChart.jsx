import { Fragment } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { CATEGORICAL, NEUTRAL_COLOR } from "../lib/chartTheme";
import { withSliceCorners } from "../lib/pieCorners";
import { formatCompact, formatMoney } from "../lib/format";
import { useIsPhone } from "../hooks/useMediaQuery";
import { PieTouchScrub } from "../hooks/usePieTouchScrub";
import { shortTickerLabels } from "../lib/tickerLabel";
import AlignedPercent, { maxDecimalsOf } from "./AlignedPercent";
import { msg, useT } from "../i18n/I18nProvider";

// Row names the frontend/API produce in English; every other name is data
// (a ticker, a sector from the data provider) and is shown as is.
const GROUP_NAMES = new Set([msg("Cash"), msg("Other")]);

// Cash has no sector/country/asset-type of its own — give it a fixed neutral
// slate color instead of whatever the palette-by-index lookup would assign,
// so it visually reads as "not an equity" in every dimension it appears in.
// "Other" (the grouped small-positions slice) is a catch-all the same way.
const colorFor = (item, i) =>
  item.name === "Cash" || item.name === "Other" ? NEUTRAL_COLOR : CATEGORICAL[i % CATEGORICAL.length];

// legendColumns=2 flows the legend into two newspaper-style columns (read
// down, then across) — used by the wide Positions card to halve its height.
// stacked puts the legend in one column beneath the donut (narrow cards that
// sit side by side) instead of beside it.
// shortenTickers (phone legend only) drops exchange suffixes — VWCE.DE shows as
// VWCE — unless that would make two entries look the same (see tickerLabel.js).
export default function BreakdownChart({ title, data, currencyLabel, legendColumns = 1, nameWidth = 70, stacked = false, shortenTickers = false }) {
  // Same formatter as the rest of the app, so separators follow the display
  // currency (CZK reads "5 224,05 Kč", not "5,224.05 Kč").
  const t = useT();
  const nameOf = (item) => (GROUP_NAMES.has(item.name) ? t(item.name) : item.name);
  const fmt = (n) => formatMoney(n, currencyLabel);
  const isPhone = useIsPhone();

  if (!data || data.length === 0) return null;

  const slices = withSliceCorners(data, { valueKey: "weight", inner: 40, outer: 75, corner: 7 });
  // Every legend % shows at least 2 decimals (2.5 reads 2.50%) and all share
  // the same count, so the decimal points sit under each other.
  const pctDecimals = Math.max(2, maxDecimalsOf(data.map((d) => d.weight)));

  return (
    <div className="card min-w-0">
      <h2 className="text-sm font-semibold text-muted mb-4 uppercase tracking-wider">
        {title}
      </h2>
      <div className={`flex flex-col items-stretch gap-6 ${stacked ? "" : "sm:flex-row sm:items-start"}`}>
        <PieTouchScrub className={`pie-pop w-48 h-48 shrink-0 self-center ${stacked ? "" : "sm:self-auto"}`}>
          {(tooltipProps) => (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={slices}
                dataKey="weight"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={75}
                paddingAngle={3}
                cornerRadius={7}
              >
                {data.map((item, i) => (
                  <Cell key={i} fill={colorFor(item, i)} />
                ))}
              </Pie>
              <Tooltip
                {...tooltipProps}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const item = payload[0].payload;
                  return (
                    <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-xs shadow-lg">
                      <div className="font-semibold text-ink">
                        {nameOf(item)} · <AlignedPercent value={item.weight} decimals={2} />
                      </div>
                      {/* Grouped slices (e.g. "Other" positions) carry their
                          members in `items` — list them on hover. */}
                      {item.items?.length > 0 && (
                        <div className="flex flex-wrap gap-x-2 mt-1 max-w-[240px] text-muted">
                          {item.items.map((sub) => (
                            <span key={sub.name} className="whitespace-nowrap">
                              {sub.name} <AlignedPercent value={sub.weight} decimals={2} />
                            </span>
                          ))}
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
        {(() => {
          // Names are shown in full; the column is sized to the longest one.
          const longestName = Math.max(...data.map((d) => String(d.name).length)) * 0.9;
          const renderRow = (item, i) => (
            <div key={item.name} className="flex items-center gap-2 text-sm">
              <div
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: colorFor(item, i) }}
              />
              <span className="text-ink whitespace-nowrap shrink-0" style={{ minWidth: `${nameWidth}px`, width: `${longestName}ch` }}>{nameOf(item)}</span>
              <span className="flex items-baseline shrink-0">
                <span className="tabular-nums text-muted min-w-[3.5rem] text-right"><AlignedPercent value={item.weight} decimals={pctDecimals} /></span>
                <span className="tabular-nums text-muted text-xs ml-[10px]">({fmt(item.value)})</span>
              </span>
            </div>
          );

          if (legendColumns !== 2) {
            return <div className="flex-1 min-w-0 flex flex-col gap-1.5">{data.map(renderRow)}</div>;
          }

          const half = Math.ceil(data.length / 2);

          // Phone: two equal columns that always sit side by side (the negative
          // margin wins back some card padding). Each column is the same
          // ticker / % / (value) grid as on desktop, so the % are aligned to the
          // longest ticker and the amounts line up too. The value is abbreviated
          // (41K Kč) and 12px (the design floor). The ticker track may shrink
          // (min 0) and truncates as a last resort, so the second column can
          // never drop below the first, whatever the phone width.
          if (isPhone) {
            const labels = shortenTickers ? shortTickerLabels(data.map((d) => d.name)) : null;
            const labelOf = (item) => labels?.get(String(item.name)) ?? nameOf(item);
            const phoneColumn = (items, offset) => (
              <div className="grid min-w-0 grid-cols-[minmax(0,auto)_auto_auto] content-start items-baseline justify-start gap-x-1 gap-y-1.5 text-xs">
                {items.map((item, i) => (
                  <Fragment key={item.name}>
                    <span className="inline-flex min-w-0 items-center gap-1 whitespace-nowrap text-ink">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colorFor(item, i + offset) }} />
                      <span className="min-w-0 truncate" title={String(item.name)}>{labelOf(item)}</span>
                    </span>
                    <span className="text-right text-muted"><AlignedPercent value={item.weight} decimals={pctDecimals} /></span>
                    <span className="whitespace-nowrap tabular-nums text-muted">({formatCompact(item.value, currencyLabel)})</span>
                  </Fragment>
                ))}
              </div>
            );
            return (
              <div className="-mx-4 grid min-w-0 flex-1 grid-cols-2 gap-x-2">
                {phoneColumn(data.slice(0, half), 0)}
                {phoneColumn(data.slice(half), half)}
              </div>
            );
          }

          // Wider screens: each legend column is a 3-column grid (ticker, %,
          // value), so a column is as wide as its longest ticker / longest % and
          // the gap between ticker and %, and between % and (value), is the same
          // 10px.
          const legendColumn = (items, offset) => (
            <div className="grid min-w-0 grid-cols-[auto_auto_auto] content-start items-baseline justify-start gap-x-2.5 gap-y-1.5 text-sm">
              {items.map((item, i) => (
                <Fragment key={item.name}>
                  <span className="inline-flex items-center gap-2 whitespace-nowrap text-ink">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: colorFor(item, i + offset) }} />
                    {nameOf(item)}
                  </span>
                  <span className="text-right text-muted"><AlignedPercent value={item.weight} decimals={pctDecimals} /></span>
                  <span className="tabular-nums whitespace-nowrap text-xs text-muted">({fmt(item.value)})</span>
                </Fragment>
              ))}
            </div>
          );
          return (
            <div className="flex min-w-0 flex-1 flex-wrap justify-start gap-x-[100px] gap-y-1.5">
              {legendColumn(data.slice(0, half), 0)}
              {legendColumn(data.slice(half), half)}
            </div>
          );
        })()}
      </div>
    </div>
  );
}
