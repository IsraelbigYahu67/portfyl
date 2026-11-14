import { useLayoutEffect, useRef, useState } from "react";
import { Maximize2, UserCheck, X } from "lucide-react";
import { AsyncSection, EmptyState, SectionHeader, SkeletonRows } from "../ui";
import ZoomDialog from "../ui/ZoomDialog";
import Select from "../ui/Select";
import { TickerLink } from "../TickerLink";
import { useIsPhone } from "../../hooks/useMediaQuery";
import { formatCompact, formatMoney, formatQuantity, formatTableDate } from "../../lib/format";
import { useT } from "../../i18n/I18nProvider";

// Rows shown before the card has been measured (and in jsdom, which has no layout).
export const FALLBACK_ROWS = 8;
// Cards are taller than table rows, so a phone shows fewer before "view all".
const PHONE_ROWS = 5;

const thBase = "text-xs font-medium uppercase tracking-wider pb-2";

function sortBuys(buys, sort) {
  return [...buys].sort((a, b) => {
    if (sort === "value") return (Math.abs(b.value) || 0) - (Math.abs(a.value) || 0);
    if (sort === "pnl") return (b.pnl ?? -Infinity) - (a.pnl ?? -Infinity);
    return (b.date || "").localeCompare(a.date || "");
  });
}

// How many single-line table rows fit in `ref`'s box. Re-measured whenever
// the box resizes (the neighbouring heatmap sets the row height on desktop).
function useFittingRows(ref, enabled) {
  const [rows, setRows] = useState(null);
  useLayoutEffect(() => {
    const box = ref.current;
    if (!enabled || !box) return undefined;
    const measure = () => {
      const available = box.clientHeight;
      const head = box.querySelector("thead")?.offsetHeight ?? 0;
      const row = box.querySelector("tbody tr")?.offsetHeight;
      if (!available || !row) return;
      setRows(Math.max(1, Math.floor((available - head) / row)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, [ref, enabled]);
  return rows;
}

// One-decimal P&L percent with its sign. Rounding first keeps a tiny move
// such as -0.04 from rendering as a red "-0.0%"; it reads as a neutral 0.0%.
function signedPct(value) {
  const rounded = Math.round(value * 10) / 10 || 0;
  const tone = rounded > 0 ? "text-gain" : rounded < 0 ? "text-loss" : "text-muted";
  return { tone, text: `${rounded > 0 ? "+" : ""}${rounded.toFixed(1)}%` };
}

// The percent is split at its decimal point into two cells so the dot of every
// row (and the "&" of the heading) lands on one vertical line.
function PnlPctCells({ buy }) {
  const cell = "py-1.5 tabular-nums font-medium whitespace-nowrap";
  if (buy.pnl_pct == null) {
    return (
      <>
        <td className={`${cell} text-right text-muted`}>—</td>
        <td className={`${cell} pr-3`} />
      </>
    );
  }
  const { tone, text } = signedPct(buy.pnl_pct);
  const dot = text.indexOf(".");
  return (
    <>
      <td className={`${cell} text-right ${tone}`}>{text.slice(0, dot)}</td>
      <td className={`${cell} pr-3 text-left ${tone}`}>{text.slice(dot)}</td>
    </>
  );
}

function CompactTable({ buys }) {
  const t = useT();
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-surface-border">
          <th className={`${thBase} pr-3 text-left text-muted`}>{t("Ticker")}</th>
          <th className={`${thBase} text-left text-muted`}>{t("Insider")}</th>
          {/* Two header cells, like the body, so the "(" of the heading lines up with the rows' "(". */}
          <th className={`${thBase} text-right text-muted whitespace-nowrap`}>{t("Bought value")}</th>
          <th className={`${thBase} pl-1 pr-3 text-left text-muted whitespace-nowrap`}>(P&L)</th>
          {/* One word "P&L": the "&" is centred on the split between the percent cells (over the decimal dot) and the P and L hang off it, touching, on either side. */}
          <th className={`${thBase} text-right text-muted whitespace-nowrap`}>
            <span className="inline-block w-0 overflow-visible">
              <span className="relative inline-block translate-x-[calc(-50%+3px)]">
                &amp;
                <span className="absolute right-full top-0">P</span>
                <span className="absolute left-full top-0">L</span>
              </span>
            </span>
          </th>
          <th className={`${thBase} pr-3`} aria-hidden="true" />
          <th className={`${thBase} text-right text-muted`}>{t("Date")}</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-surface-border">
        {buys.map((b, i) => (
          <tr key={i} className="hover:bg-surface-hover transition-colors">
            <td className="py-1.5 pr-3 whitespace-nowrap">
              <TickerLink ticker={b.ticker} className="font-mono font-semibold" />
            </td>
            <td className="py-1.5 pr-3 text-muted max-w-[140px] truncate" title={`${b.insider || ""}${b.position ? ` — ${b.position}` : ""}`}>
              {b.insider || "—"}
            </td>
            {/* Value and its P&L amount are two cells so every "(" lines up in one column. */}
            <td className="py-1.5 pl-0 text-right tabular-nums text-ink font-medium whitespace-nowrap">
              {b.value != null ? formatCompact(Math.abs(b.value), b.currency) : "—"}
            </td>
            <td className={`py-1.5 pl-1 pr-3 text-left tabular-nums text-xs whitespace-nowrap ${b.pnl != null && b.pnl < 0 ? "text-loss" : "text-gain"}`}>
              {b.value != null && b.pnl != null && (
                <>({b.pnl >= 0 ? "+" : "-"}{formatCompact(Math.abs(b.pnl), b.currency)})</>
              )}
            </td>
            <PnlPctCells buy={b} />
            <td className="py-1.5 text-right tabular-nums text-muted text-xs whitespace-nowrap">
              {formatTableDate(b.date)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Phone layout: one card line per purchase instead of a 7-column table whose
// Insider and Value columns were cut off.
function BuyCards({ buys }) {
  const t = useT();
  return (
    <ul className="divide-y divide-hairline" aria-label={t("Insider buys")}>
      {buys.map((b, i) => {
        const { tone, text } = b.pnl_pct != null ? signedPct(b.pnl_pct) : { tone: "text-muted", text: "—" };
        return (
          <li key={i} className="py-2.5">
            <div className="flex items-center justify-between gap-3">
              <TickerLink ticker={b.ticker} className="inline-flex min-h-11 items-center font-mono font-semibold" />
              <span className="text-xs tabular-nums text-muted">{formatTableDate(b.date)}</span>
            </div>
            <div className="-mt-2 flex items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm text-ink">{b.insider || "—"}</p>
                {b.position && <p className="truncate text-xs text-muted">{b.position}</p>}
              </div>
              <div className="shrink-0 text-right tabular-nums">
                <p className="text-sm font-medium text-ink">{b.value != null ? formatCompact(Math.abs(b.value), b.currency) : "—"}</p>
                <p className={`text-xs font-medium ${tone}`}>{text}</p>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function FullTable({ buys, sort, onSort }) {
  const t = useT();
  // Sticky header cells need an opaque background to hide rows scrolling under them.
  // Cell radii only render with separated borders, so the row dividers live
  // on the cells instead of the rows.
  const th = `${thBase} sticky top-0 z-10 bg-surface-card pt-1 border-b border-surface-border first:pl-2 first:rounded-l-lg last:pr-2 last:rounded-r-lg`;
  const thSortable = (key, align) => `${th} ${align} cursor-pointer select-none transition-colors ${sort === key ? "text-brand" : "text-muted hover:text-ink"}`;
  const sortArrow = (key) => (sort === key ? " ▼" : "");
  return (
    <table className="w-full text-sm border-separate border-spacing-0">
      <thead>
        <tr>
          <th className={`${th} text-left text-muted`}>{t("Ticker")}</th>
          <th className={`${th} text-left text-muted`}>{t("Insider")}</th>
          <th className={`${th} text-right text-muted`}>{t("Shares")}</th>
          <th className={`${th} text-right text-muted`}>{t("Buy Price")}</th>
          <th className={thSortable("value", "text-right")} onClick={() => onSort("value")}>{t("Value")}{sortArrow("value")}</th>
          <th className={thSortable("pnl", "text-right")} onClick={() => onSort("pnl")}>P&L{sortArrow("pnl")}</th>
          <th className={thSortable("date", "text-right")} onClick={() => onSort("date")}>{t("Date")}{sortArrow("date")}</th>
        </tr>
      </thead>
      <tbody className="[&>tr+tr>td]:border-t [&>tr>td]:border-surface-border [&>tr>td:first-child]:pl-2 [&>tr>td:last-child]:pr-2">
        {buys.map((b, i) => {
          const pnlUp = b.pnl != null && b.pnl >= 0;
          return (
            <tr key={i} className="hover:bg-surface-hover transition-colors">
              <td className="py-1.5 pr-3">
                <TickerLink ticker={b.ticker} className="font-mono font-semibold" />
              </td>
              <td className="py-1.5 pr-3 text-muted max-w-[260px] truncate" title={`${b.insider || ""}${b.position ? ` — ${b.position}` : ""}`}>
                {b.insider || "—"}
                {b.position && <span className="text-muted text-xs ml-1">({b.position})</span>}
              </td>
              <td className="py-1.5 pr-3 text-right tabular-nums text-ink">
                {b.shares != null ? formatQuantity(Math.abs(b.shares), b.currency) : "—"}
              </td>
              <td className="py-1.5 pr-3 text-right tabular-nums text-ink">
                {b.buy_price != null ? formatMoney(b.buy_price, b.currency) : "—"}
              </td>
              <td className="py-1.5 pr-3 text-right tabular-nums text-ink font-medium">
                {b.value != null ? formatMoney(Math.abs(b.value), b.currency) : "—"}
              </td>
              <td className={`py-1.5 pr-3 text-right tabular-nums font-medium ${b.pnl == null ? "text-muted" : pnlUp ? "text-gain" : "text-loss"}`}>
                {b.pnl != null ? (
                  <span title={t("Current: {price}", { price: formatMoney(b.current_price, b.currency) })}>
                    {b.pnl >= 0 ? "+" : ""}{formatMoney(b.pnl, b.currency)}
                    {b.pnl_pct != null && <span className="text-xs ml-1">({signedPct(b.pnl_pct).text})</span>}
                  </span>
                ) : "—"}
              </td>
              <td className="py-1.5 text-right tabular-nums text-muted text-xs whitespace-nowrap">
                {formatTableDate(b.date)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// Dashboard card: as many of the newest insider purchases across current
// holdings as fit the card's height. The expand button zooms the full,
// sortable table (shares, buy price, P&L) out of the card into a dialog.
export default function InsiderBuysCard({ buys = [], isLoading, error, onRetry }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [sort, setSort] = useState("date");
  const isPhone = useIsPhone();
  const rootRef = useRef(null);
  const boxRef = useRef(null);
  const hasRows = !isLoading && !error && buys.length > 0;
  const fitting = useFittingRows(boxRef, hasRows);
  const newest = sortBuys(buys, "date");
  const shown = newest.slice(0, fitting ?? FALLBACK_ROWS);

  const expand = hasRows && (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-label={t("Expand insider buys")}
      title={t("Expand")}
      className="grid place-items-center w-8 h-8 rounded-lg text-muted hover:text-ink hover:bg-surface-hover transition-colors"
    >
      <Maximize2 size={15} />
    </button>
  );

  return (
    <div ref={rootRef} className="flex flex-col h-full">
      <SectionHeader icon={UserCheck} action={expand}>{t("Recent insider buys")}</SectionHeader>
      <AsyncSection
        isLoading={isLoading}
        error={error}
        onRetry={onRetry}
        loading={<SkeletonRows rows={FALLBACK_ROWS} cols={5} />}
        isEmpty={buys.length === 0}
        empty={<EmptyState icon={UserCheck} title={t("No insider buys")} hint={t("No insider purchases across your holdings in the last 12 months.")} />}
      >
        {/* The table is absolutely positioned so it never sets the card's
            height — the box takes whatever the row gives it, and the hook
            fills it with as many rows as fit. */}
        {isPhone ? (
          <div ref={boxRef}>
            <BuyCards buys={newest.slice(0, PHONE_ROWS)} />
          </div>
        ) : (
          <div ref={boxRef} className="relative flex-1 min-h-[240px]">
            <div className="absolute inset-0 overflow-hidden">
              <CompactTable buys={shown} />
            </div>
          </div>
        )}
        <p className="mt-2 text-xs text-muted">
          {(isPhone ? Math.min(PHONE_ROWS, buys.length) : shown.length) < buys.length ? (
            <button type="button" onClick={() => setOpen(true)} className="inline-flex min-h-11 items-center text-brand hover:text-brand/80 font-medium transition-colors">
              {t("{shown} of {total} buys · view all", { shown: isPhone ? Math.min(PHONE_ROWS, buys.length) : shown.length, total: buys.length })}
            </button>
          ) : (
            t("All buys from the last 12 months ({count})", { count: buys.length })
          )}
        </p>
      </AsyncSection>

      <ZoomDialog
        open={open}
        onClose={() => setOpen(false)}
        getOrigin={() => rootRef.current?.closest(".card") ?? rootRef.current}
        labelledBy="insider-buys-dialog-title"
        className="max-w-5xl"
      >
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-2">
            <span className="grid place-items-center w-7 h-7 rounded-lg bg-brand/10 text-brand shrink-0">
              <UserCheck size={14} />
            </span>
            <div>
              <h2 id="insider-buys-dialog-title" className="font-display text-base font-semibold text-ink">{t("Insider buys")}</h2>
              <p className="text-xs text-muted">{t("Purchases across your holdings: {count} · last 12 months", { count: buys.length })}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label={t("Close")}
            className="grid place-items-center w-8 h-8 rounded-lg text-muted hover:text-ink hover:bg-surface-hover transition-colors"
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {isPhone ? (
            <>
              <Select
                aria-label={t("Sort insider buys")}
                value={sort}
                onChange={setSort}
                className="mb-2 min-h-11"
                options={[
                  { value: "date", label: t("Sort: Newest") },
                  { value: "value", label: t("Sort: Value") },
                  { value: "pnl", label: t("Sort: P&L") },
                ]}
              />
              <BuyCards buys={sortBuys(buys, sort)} />
            </>
          ) : (
            <FullTable buys={sortBuys(buys, sort)} sort={sort} onSort={setSort} />
          )}
        </div>
      </ZoomDialog>
    </div>
  );
}
