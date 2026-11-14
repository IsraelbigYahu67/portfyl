import { ArrowDown, ArrowUp, TrendingDown, TrendingUp } from "lucide-react";
import { TickerLink } from "./TickerLink";
import Select from "./ui/Select";
import { formatPercent, formatQuantity } from "../lib/format";
import { hasPriceProblem, priceFreshnessTitle } from "../lib/priceFreshness";
import { msg, useT } from "../i18n/I18nProvider";

// Phone layout of the Allocation tables (DESIGN.md section 8): one card per
// position instead of a 10-column table, so value, P&L and weight sit on the
// screen instead of behind a sideways scroll. Same data and formatters as the
// desktop table; the page chooses which one to mount.

export const SORT_OPTIONS = [
  { key: "market_value", label: msg("Value") },
  { key: "pnl", label: msg("P&L") },
  { key: "pnl_percent", label: msg("P&L %") },
  { key: "weight", label: msg("Weight") },
  { key: "ticker", label: msg("Ticker") },
];

export const SOLD_SORT_OPTIONS = [
  { key: "pnl_if_held", label: msg("Return if not sold") },
  { key: "missed_out", label: msg("Missed out on") },
  { key: "pnl_if_held_pct", label: msg("P&L if held") },
];

// Native select (16px text so iOS does not zoom the page) + a direction button.
// Picking the active key again flips the direction, like the desktop headers.
// Option labels are English source text, translated here; `label` comes in
// already translated.
export function CardSortBar({ sort, onSort, options = SORT_OPTIONS, label }) {
  const t = useT();
  const active = sort?.key ?? options[0].key;
  return (
    <div className="mb-3 flex items-center gap-2">
      <Select
        aria-label={label ?? t("Sort holdings")}
        value={active}
        onChange={onSort}
        className="min-h-11 flex-1"
        options={options.map((o) => ({ value: o.key, label: t("Sort: {option}", { option: t(o.label) }) }))}
      />
      <button
        type="button"
        onClick={() => onSort(active)}
        aria-label={sort?.dir === "asc" ? t("Ascending, switch to descending") : t("Descending, switch to ascending")}
        className="btn-ghost grid h-11 w-11 shrink-0 place-items-center !p-0"
      >
        {sort?.dir === "asc" ? <ArrowUp size={16} /> : <ArrowDown size={16} />}
      </button>
    </div>
  );
}

function CardShell({ onOpen, children }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onOpen();
        }
      }}
      className="card block w-full cursor-pointer space-y-2 text-left"
    >
      {children}
    </div>
  );
}

export function HoldingCards({ holdings, currency, fmt, fmtSigned, fmtNative, onOpen }) {
  const t = useT();
  return (
    <ul className="space-y-3" aria-label={t("All holdings")}>
      {holdings.map((h) => {
        const up = h.pnl >= 0;
        const tone = up ? "text-gain" : "text-loss";
        return (
          <li key={h.ticker}>
            <CardShell onOpen={() => onOpen(h.ticker)}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <TickerLink ticker={h.ticker} className="inline-flex min-h-11 items-center font-mono text-base font-bold">
                    {h.ticker}
                  </TickerLink>
                  <div className="-mt-2 truncate text-sm text-muted">{h.name}</div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="font-display text-lg font-bold tabular-nums text-ink">{fmt(h.market_value)}</div>
                  <div className={`flex items-center justify-end gap-1 text-sm font-medium tabular-nums ${tone}`}>
                    {up ? <TrendingUp size={13} aria-hidden="true" /> : <TrendingDown size={13} aria-hidden="true" />}
                    {fmtSigned(h.pnl)} · {formatPercent(h.pnl_percent)}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="h-1.5 flex-1 rounded-full bg-surface-hover" role="presentation">
                  <div className="h-1.5 rounded-full bg-brand" style={{ width: `${Math.min(100, Math.max(0, h.weight))}%` }} />
                </div>
                <span className="financial-meta w-14 text-right tabular-nums">
                  {formatPercent(h.weight, { sign: false, digits: 2 })}
                </span>
              </div>

              <dl className="financial-meta grid grid-cols-3 gap-2 tabular-nums">
                <div>
                  <dt>{t("Shares")}</dt>
                  <dd className="text-ink">{formatQuantity(h.shares, currency)}</dd>
                </div>
                <div>
                  <dt>{t("Avg cost")}</dt>
                  <dd className="text-ink">{fmtNative(h.avg_cost, h.currency)}</dd>
                </div>
                <div>
                  <dt>{t("Price")}</dt>
                  <dd className="text-ink" title={priceFreshnessTitle(h, { t }) ?? undefined}>
                    {fmtNative(h.current_price, h.currency)}
                  </dd>
                </div>
              </dl>

              <div className="financial-meta flex flex-wrap items-center justify-between gap-x-3">
                <span>{t("Dividends {amount}", { amount: fmt(h.dividends) })}</span>
                {hasPriceProblem(h) && (
                  <span
                    className={h.price_status === "missing" ? "text-loss" : "text-[color:var(--chart-3)]"}
                    title={priceFreshnessTitle(h, { t })}
                  >
                    {h.price_status === "missing" ? t("no price") : t("out of date")}
                  </span>
                )}
              </div>
            </CardShell>
          </li>
        );
      })}
    </ul>
  );
}

export function SoldCards({ holdings, fmtSigned, fmtPct, missedOut, onOpen }) {
  const t = useT();
  const toneOf = (v) => ((v ?? 0) >= 0 ? "text-gain" : "text-loss");
  return (
    <ul className="space-y-3" aria-label={t("Sold positions")}>
      {holdings.map((h) => (
        <li key={h.ticker}>
          <CardShell onOpen={() => onOpen(h.ticker)}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <TickerLink ticker={h.ticker} className="inline-flex min-h-11 items-center font-mono text-base font-bold">
                  {h.ticker}
                </TickerLink>
                <span className="financial-meta ml-1.5 font-medium uppercase text-loss">{t("Sold")}</span>
                <div className="-mt-2 truncate text-sm text-muted">{h.name}</div>
              </div>
              <div className="shrink-0 text-right">
                <div className="financial-meta">{t("Sold for")}</div>
                <div className={`font-display text-lg font-bold tabular-nums ${toneOf(h.pnl)}`}>
                  {h.pnl != null ? fmtSigned(h.pnl) : "—"}
                </div>
              </div>
            </div>
            <dl className="financial-meta grid grid-cols-3 gap-2 tabular-nums">
              <div>
                <dt>{t("Return if not sold")}</dt>
                <dd className={toneOf(h.pnl_if_held)}>{h.pnl_if_held != null ? fmtSigned(h.pnl_if_held) : "—"}</dd>
              </div>
              <div>
                <dt>{t("Missed out on")}</dt>
                <dd className={toneOf(missedOut(h))}>
                  {h.pnl != null && h.pnl_if_held != null ? fmtSigned(missedOut(h)) : "—"}
                </dd>
              </div>
              <div>
                <dt>{t("P&L if held")}</dt>
                <dd className={toneOf(h.pnl_if_held_pct)}>{h.pnl_if_held_pct != null ? fmtPct(h.pnl_if_held_pct) : "—"}</dd>
              </div>
            </dl>
          </CardShell>
        </li>
      ))}
    </ul>
  );
}
