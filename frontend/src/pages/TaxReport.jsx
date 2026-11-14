import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { fetchTaxReport } from "../editions/localApi";
import { useCurrency } from "../App";
import MetricCard from "../components/MetricCard";
import Select from "../components/ui/Select";
import { FileText, Download, TrendingUp, TrendingDown, ShieldCheck, AlertTriangle, Hourglass } from "lucide-react";
import { TickerLink } from "../components/StockDetail";
import {
  formatMoney as formatSharedMoney,
  formatPercent,
  formatQuantity,
  formatTableDate,
} from "../lib/format";
import { AsyncSection, Badge } from "../components/ui";
import Pagination from "../components/ui/Pagination";
import { msg, useT } from "../i18n/I18nProvider";

// Czech §4 capital gains exemption rules. Kept on the client so the labels can
// be tweaked without touching the API.
const CZ = {
  TIME_TEST_YEARS: 3,
  VALUE_TEST_LIMIT: 100_000,
  TIME_TEST_CAP: 40_000_000,
};

const fmtCzk = (n) => {
  if (n == null) return "—";
  const sign = n < 0 ? "-" : "";
  return sign + Math.abs(n).toLocaleString("cs-CZ", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }) + " Kč";
};

// Row status for the Czech §4 exemption. The 3-year time test wins; otherwise
// a row is exempt only when the year it was sold in passed the value test
// (annual gross proceeds under the limit). A year that failed stays Taxable.
export function czRowStatus(gain, yearsByTaxYear) {
  if (gain?.cz_exempt_time_test) return "exempt_time";
  const sellYear = Number(String(gain?.sell_date ?? "").slice(0, 4));
  if (yearsByTaxYear?.[sellYear]?.value_test_passed === true) return "exempt_value";
  return "taxable";
}

function CzBadge({ gain, yearsByTaxYear }) {
  const t = useT();
  const status = czRowStatus(gain, yearsByTaxYear);
  const limit = CZ.VALUE_TEST_LIMIT.toLocaleString("cs-CZ");
  if (status === "exempt_time") {
    return (
      <Badge
        tone="gain"
        title={t("Held >3 years (§4 ZDP) — exempt from CZ income tax. Acquired {bought}, exempt from {exemptFrom}.", { bought: gain.buy_date, exemptFrom: gain.cz_exempt_date })}
      >
        {t("Exempt · 3y")}
      </Badge>
    );
  }
  if (status === "exempt_value") {
    return (
      <Badge
        tone="gain"
        title={t("Annual gross proceeds in the year of sale stayed within {limit} Kč (§4 ZDP value test) — exempt from CZ income tax.", { limit })}
      >
        {t("Exempt · value test")}
      </Badge>
    );
  }
  return (
    <Badge
      tone="warn"
      title={t("Held <3 years and the year's gross proceeds are above {limit} Kč — taxable in CZ. Would be exempt from {exemptFrom}.", { limit, exemptFrom: gain.cz_exempt_date })}
    >
      {t("Taxable")}
    </Badge>
  );
}

function TermBadge({ term }) {
  const t = useT();
  return (
    <Badge tone={term === "long" ? "brand" : "neutral"} size="sm">
      {term === "long" ? t("Long") : t("Short")}
    </Badge>
  );
}

function GainPercent({ value }) {
  const t = useT();
  if (value != null) return formatPercent(value, { sign: false });
  const note = t("Percentage is not meaningful for a basis below one cent.");
  return (
    <span title={note} aria-label={note}>
      —
    </span>
  );
}

// "1 trade" / "{count} trades": two literal keys, so the dictionaries can use
// a count-neutral form ("Obchody: 5") where a language has more plural forms.
const tradeCount = (t, count) => (count === 1 ? t("{count} trade", { count }) : t("{count} trades", { count }));

const csvFixed = (value, digits) => (
  value == null ? "" : Number(value).toFixed(digits)
);

function CzechTaxYearCard({ y }) {
  const t = useT();
  const limit = CZ.VALUE_TEST_LIMIT.toLocaleString("cs-CZ");
  // Cards collapse the per-year summary into actionable rows. Order matters:
  // value test first (because if it passes, the rest are moot), then time test,
  // then the 40M cap, then the bottom-line taxable amount.
  const taxablePositive = y.taxable_total_czk > 0;
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold flex items-center gap-2">
          <ShieldCheck size={14} className="text-brand" />
          {t("Czech Tax — {year}", { year: y.tax_year })}
        </h3>
        <span className="text-xs text-muted">§4 ZDP · {tradeCount(t, y.trades)}</span>
      </div>

      {y.incomplete_fx && (
        <div
          className="flex items-start gap-2 text-xs rounded-xl p-3"
          style={{
            color: "var(--chart-3)",
            background: "color-mix(in srgb, var(--chart-3) 10%, var(--surface-card))",
          }}
        >
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>
            {t("Some transactions are missing the CZK exchange rate — totals exclude those rows. Re-importing or refreshing FX rates will close the gap.")}
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="text-muted">{t("Gross sale proceeds")}</div>
        <div className="text-right tabular-nums">{fmtCzk(y.gross_proceeds_czk)}</div>

        <div className="text-muted">{t("Value test (≤ {limit} Kč)", { limit })}</div>
        <div className="text-right">
          {y.value_test_passed ? (
            <span className="text-gain font-medium">{t("✓ Passed — fully exempt")}</span>
          ) : (
            <span className="text-muted">{t("Above threshold")}</span>
          )}
        </div>

        <div className="text-muted">{t("Time-test exempt (> 3 yrs)")}</div>
        <div className="text-right tabular-nums text-gain">{fmtCzk(y.time_test_exempt_gain_czk)}</div>

        {y.time_test_cap_active && (
          <>
            <div className="text-muted">{t("40M cap status")}</div>
            <div className="text-right">
              {y.time_test_cap_excess_czk > 0 ? (
                <span className="text-loss">{t("Exceeded by {amount}", { amount: fmtCzk(y.time_test_cap_excess_czk) })}</span>
              ) : (
                <span className="text-gain">{t("Within cap")}</span>
              )}
            </div>
          </>
        )}

        <div className="text-muted">{t("Pre-cap taxable gain (< 3 yrs)")}</div>
        <div className="text-right tabular-nums text-muted">{fmtCzk(y.taxable_gain_czk_pre_cap)}</div>
      </div>

      <div className="border-t border-surface-border pt-3 grid grid-cols-2 gap-2 text-sm">
        <div className="text-muted">{t("Exempt total")}</div>
        <div className="text-right tabular-nums font-bold text-gain">{fmtCzk(y.exempt_total_czk)}</div>
        <div className="text-muted">{t("Taxable in CZ")}</div>
        <div
          className={`text-right tabular-nums font-bold ${taxablePositive ? "" : "text-muted"}`}
          style={taxablePositive ? { color: "var(--chart-3)" } : undefined}
        >
          {fmtCzk(y.taxable_total_czk)}
        </div>
      </div>
    </div>
  );
}

function CzechTaxPanel({ years, year }) {
  const t = useT();
  if (!years || years.length === 0) return null;
  const visible = year ? years.filter((y) => y.tax_year === year) : years;
  if (!visible.length) return null;
  // A lone card must not sit at one-third width: size the grid to the card count.
  const gridCols = visible.length >= 3
    ? "sm:grid-cols-2 xl:grid-cols-3"
    : visible.length === 2
      ? "sm:grid-cols-2"
      : "max-w-3xl";

  return (
    <section>
      <h2 className="mb-3 flex items-center gap-2 section-title">
        <ShieldCheck size={14} className="text-brand" />
        {t("Czech §4 Exemption Analysis")}
      </h2>
      <div className={`grid gap-6 ${gridCols}`}>
        {visible.map((y) => (
          <CzechTaxYearCard key={y.tax_year} y={y} />
        ))}
      </div>
    </section>
  );
}

// Table headings, translated where they are drawn.
const REALIZED_HEADINGS = [
  msg("Ticker"), msg("Buy Date"), msg("Sell Date"), msg("Shares"), msg("Cost Basis"), msg("Proceeds"),
  msg("Gain/Loss"), msg("Gain %"), msg("Days Held"), msg("Term"), msg("CZ Tax"),
];
const UNREALIZED_HEADINGS = [
  msg("Ticker"), msg("Buy Date"), msg("Shares"), msg("Cost Basis"), msg("Market Value"),
  msg("Unrealized G/L"), msg("Gain %"), msg("Days Held"), msg("Term"), msg("Tax-free In"),
];

export default function TaxReport() {
  const t = useT();
  const { currency, rate } = useCurrency();
  const [params, setParams] = useSearchParams();

  const year = params.get("year") ? Number(params.get("year")) : null;
  const tab = params.get("tab") || "realized";
  const page = Number(params.get("page") || 0);
  const ROWS_PER_PAGE = 50;

  const setTab = (next) => {
    const p = new URLSearchParams(params);
    p.set("tab", next);
    p.set("page", "0");
    setParams(p, { replace: true });
  };
  const setYear = (next) => {
    const p = new URLSearchParams(params);
    if (next == null) p.delete("year");
    else p.set("year", String(next));
    p.set("page", "0");
    setParams(p, { replace: true });
  };
  const setPage = (next) => {
    const p = new URLSearchParams(params);
    p.set("page", String(next));
    setParams(p, { replace: true });
  };

  const convert = (n) => (currency === "CZK" && rate ? n * rate : n);
  const fmt = (n) => formatSharedMoney(convert(n), currency);

  // For amounts the backend also provides in CZK at trade-time FX. In CZK mode
  // these are authoritative for Czech filing — use them instead of fmt()'s
  // approximate live-rate conversion of the USD figure.
  const fmtMoney = (usd, czk) =>
    currency === "CZK"
      ? formatSharedMoney(czk, "CZK")
      : formatSharedMoney(usd, "USD");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["tax-report", year],
    queryFn: () => fetchTaxReport(year),
  });

  const summary = data?.summary || {};
  const gains = data?.gains || [];
  const unrealized = data?.unrealized || [];
  const dividendIncome = data?.dividend_income || [];
  const availableYears = data?.available_years || [];
  const czechTax = data?.czech_tax || [];

  const yearsByTaxYear = Object.fromEntries(
    czechTax.map((y) => [y.tax_year, { value_test_passed: y.value_test_passed === true }]),
  );

  const shortGains = gains.filter((g) => g.term === "short");
  const longGains = gains.filter((g) => g.term === "long");

  const pagedGains = gains.slice(page * ROWS_PER_PAGE, (page + 1) * ROWS_PER_PAGE);
  const pagedUnrealized = unrealized.slice(page * ROWS_PER_PAGE, (page + 1) * ROWS_PER_PAGE);

  const exportCSV = () => {
    if (!gains.length && !dividendIncome.length) return;

    // USD columns are the raw lot figures; the *_czk columns use the FX captured
    // at each trade date (what a Czech filing needs), blank when unavailable.
    const czk = (n) => (n == null ? "" : n);
    let csv = "Section,Ticker,Buy Date,Sell Date,Shares,Cost Basis (USD),Proceeds (USD),Gain/Loss (USD),Cost Basis (CZK),Proceeds (CZK),Gain/Loss (CZK),Gain %,Holding Days,Term\n";
    for (const g of gains) {
      csv += `Realized,${g.ticker},${g.buy_date},${g.sell_date},${csvFixed(g.shares, 8)},${csvFixed(g.cost_basis, 6)},${csvFixed(g.proceeds, 6)},${csvFixed(g.gain, 6)},${csvFixed(g.cost_basis_czk, 6)},${csvFixed(g.proceeds_czk, 6)},${csvFixed(g.gain_czk, 6)},${g.gain_pct == null ? "" : g.gain_pct},${g.holding_days},${g.term}\n`;
    }
    if (dividendIncome.length) {
      csv += "\nSection,Ticker,Amount (USD),Amount (CZK)\n";
      for (const d of dividendIncome) {
        csv += `Dividend,${d.ticker},${d.amount},${czk(d.amount_czk)}\n`;
      }
    }
    if (unrealized.length) {
      csv += "\nSection,Ticker,Buy Date,Shares,Cost Basis,Market Value,Unrealized Gain,Gain %,Holding Days,Term\n";
      for (const u of unrealized) {
        csv += `Unrealized,${u.ticker},${u.buy_date},${csvFixed(u.shares, 8)},${csvFixed(u.cost_basis, 6)},${csvFixed(u.market_value, 6)},${csvFixed(u.unrealized_gain, 6)},${u.gain_pct == null ? "" : u.gain_pct},${u.holding_days},${u.term}\n`;
      }
    }

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `tax-report-${year || "all"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const TABS = [
    { key: "realized", label: t("Realized Gains"), count: gains.length },
    { key: "unrealized", label: t("Unrealized Gains"), count: unrealized.length },
    { key: "dividends", label: t("Dividend Income"), count: dividendIncome.length },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <FileText size={20} className="text-brand" />
            {t("Tax Report")}
          </h1>
          <p className="text-xs text-muted mt-0.5">{t("Capital gains, losses, and dividend income (FIFO method)")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={year || ""}
            onChange={(v) => setYear(v ? parseInt(v, 10) : null)}
            aria-label={t("Tax year")}
            className="text-sm"
            options={[{ value: "", label: t("All Years") }, ...availableYears.map((y) => ({ value: y, label: String(y) }))]}
          />
          <button
            onClick={exportCSV}
            disabled={!gains.length && !dividendIncome.length}
            className="btn-ghost flex items-center gap-2 whitespace-nowrap text-sm disabled:opacity-30"
          >
            <Download size={14} />
            {t("Export CSV")}
          </button>
        </div>
      </div>

      <AsyncSection
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        loading={(
          <div className="card animate-pulse h-32 flex items-center justify-center text-muted">
            {t("Generating tax report…")}
          </div>
        )}
      >
        <>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <MetricCard
              label={t("Total Realized P&L")}
              value={fmtMoney(summary.total_realized, summary.total_realized_czk)}
              positive={summary.total_realized >= 0}
              negative={summary.total_realized < 0}
            />
            <MetricCard
              label={t("Short-Term Gains")}
              value={fmtMoney(summary.short_term_gains, summary.short_term_gains_czk)}
              sub={tradeCount(t, summary.short_term_count || 0)}
              positive={summary.short_term_gains >= 0}
              negative={summary.short_term_gains < 0}
            />
            <MetricCard
              label={t("Long-Term Gains")}
              value={fmtMoney(summary.long_term_gains, summary.long_term_gains_czk)}
              sub={tradeCount(t, summary.long_term_count || 0)}
              positive={summary.long_term_gains >= 0}
              negative={summary.long_term_gains < 0}
            />
            <MetricCard
              label={t("Dividend Income")}
              value={fmtMoney(summary.total_dividends, summary.total_dividends_czk)}
              sub={dividendIncome.length === 1
                ? t("{count} stock", { count: 1 })
                : t("{count} stocks", { count: dividendIncome.length })}
            />
          </div>

          <CzechTaxPanel years={czechTax} year={year} />

          <div className="card p-0 overflow-hidden">
            <div className="flex border-b border-surface-border">
              {TABS.map((item) => (
                <button
                  key={item.key}
                  onClick={() => setTab(item.key)}
                  className={`px-5 py-3 text-sm font-medium transition-colors ${
                    tab === item.key
                      ? "text-brand border-b-2 border-brand"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  {item.label}
                  {item.count > 0 && (
                    <span className="ml-2 text-xs bg-surface-hover px-1.5 py-0.5 rounded-full">{item.count}</span>
                  )}
                </button>
              ))}
            </div>

            {tab === "realized" && (
              <>
              {!gains.length ? (
                <div className="text-muted text-sm text-center py-12">
                  {year ? t("No realized gains or losses in {year}.", { year }) : t("No realized gains or losses.")}
                </div>
              ) : (
                <>
                <ul className="md:hidden divide-y divide-surface-border">
                  {pagedGains.map((g, i) => {
                    const up = g.gain >= 0;
                    return (
                      <li key={i} className="flex items-start justify-between gap-3 px-4 py-3">
                        <div className="min-w-0 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono font-bold text-sm">
                              <TickerLink ticker={g.ticker}>{g.ticker}</TickerLink>
                            </span>
                            <TermBadge term={g.term} />
                            <CzBadge gain={g} yearsByTaxYear={yearsByTaxYear} />
                          </div>
                          <p className="text-sm text-muted tabular-nums">
                            {formatTableDate(g.buy_date)} → {formatTableDate(g.sell_date)} · {t("{shares} sh", { shares: formatQuantity(g.shares, "CZK") })} · {t("{days}d", { days: g.holding_days })}
                          </p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className={`flex items-center justify-end gap-1 tabular-nums text-sm font-medium ${up ? "text-gain" : "text-loss"}`}>
                            {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                            {fmtMoney(g.gain, g.gain_czk)}
                          </p>
                          <p className={`tabular-nums text-sm ${up ? "text-gain" : "text-loss"}`}>
                            <GainPercent value={g.gain_pct} />
                          </p>
                        </div>
                      </li>
                    );
                  })}
                  <li className="px-4 py-3 space-y-1 text-sm">
                    <p className="flex justify-between font-bold">
                      <span>{t("Short-Term Total")}</span>
                      <span className={`tabular-nums ${summary.short_term_gains >= 0 ? "text-gain" : "text-loss"}`}>
                        {fmtMoney(summary.short_term_gains, summary.short_term_gains_czk)}
                      </span>
                    </p>
                    <p className="flex justify-between font-bold">
                      <span>{t("Long-Term Total")}</span>
                      <span className={`tabular-nums ${summary.long_term_gains >= 0 ? "text-gain" : "text-loss"}`}>
                        {fmtMoney(summary.long_term_gains, summary.long_term_gains_czk)}
                      </span>
                    </p>
                  </li>
                </ul>
                <div className="hidden md:block overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b border-surface-border">
                      <tr>
                        {REALIZED_HEADINGS.map((h, i) => (
                          <th key={h} className={`${i >= 3 && i <= 8 ? "text-right" : "text-left"} px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider`}>{t(h)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {pagedGains.map((g, i) => {
                        const up = g.gain >= 0;
                        return (
                          <tr key={i} className="hover:bg-surface-hover transition-colors">
                            <td className="px-4 py-3 font-mono font-bold text-sm">
                              <TickerLink ticker={g.ticker}>{g.ticker}</TickerLink>
                            </td>
                            <td className="px-4 py-3 text-sm text-muted tabular-nums">{formatTableDate(g.buy_date)}</td>
                            <td className="px-4 py-3 text-sm text-muted tabular-nums">{formatTableDate(g.sell_date)}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{formatQuantity(g.shares, "CZK")}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{fmtMoney(g.cost_basis, g.cost_basis_czk)}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{fmtMoney(g.proceeds, g.proceeds_czk)}</td>
                            <td className={`px-4 py-3 text-sm text-right tabular-nums font-medium ${up ? "text-gain" : "text-loss"}`}>
                              <span className="flex items-center justify-end gap-1">
                                {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                {fmtMoney(g.gain, g.gain_czk)}
                              </span>
                            </td>
                            <td className={`px-4 py-3 text-sm text-right tabular-nums ${up ? "text-gain" : "text-loss"}`}>
                              <GainPercent value={g.gain_pct} />
                            </td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums text-muted">{t("{days}d", { days: g.holding_days })}</td>
                            <td className="px-4 py-3"><TermBadge term={g.term} /></td>
                            <td className="px-4 py-3"><CzBadge gain={g} yearsByTaxYear={yearsByTaxYear} /></td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot className="border-t-2 border-surface-border bg-surface">
                      <tr>
                        <td className="px-4 py-3 text-sm font-bold" colSpan={5}>{t("Short-Term Total")}</td>
                        <td className="px-4 py-3 text-sm text-right tabular-nums">{fmt(shortGains.reduce((s, g) => s + g.proceeds, 0))}</td>
                        <td className={`px-4 py-3 text-sm text-right tabular-nums font-bold ${summary.short_term_gains >= 0 ? "text-gain" : "text-loss"}`}>
                          {fmtMoney(summary.short_term_gains, summary.short_term_gains_czk)}
                        </td>
                        <td colSpan={4}></td>
                      </tr>
                      <tr>
                        <td className="px-4 py-3 text-sm font-bold" colSpan={5}>{t("Long-Term Total")}</td>
                        <td className="px-4 py-3 text-sm text-right tabular-nums">{fmt(longGains.reduce((s, g) => s + g.proceeds, 0))}</td>
                        <td className={`px-4 py-3 text-sm text-right tabular-nums font-bold ${summary.long_term_gains >= 0 ? "text-gain" : "text-loss"}`}>
                          {fmtMoney(summary.long_term_gains, summary.long_term_gains_czk)}
                        </td>
                        <td colSpan={4}></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
                </>
              )}
              {gains.length > ROWS_PER_PAGE && (
                <div className="px-4">
                  <Pagination
                    offset={page * ROWS_PER_PAGE}
                    limit={ROWS_PER_PAGE}
                    total={gains.length}
                    onOffsetChange={(nextOffset) => setPage(Math.floor(nextOffset / ROWS_PER_PAGE))}
                    ariaLabel={t("Tax report realized gains pages")}
                  />
                </div>
              )}
              </>
            )}

            {tab === "unrealized" && (
              <>
              <div className="overflow-x-auto">
                {!unrealized.length ? (
                  <div className="text-muted text-sm text-center py-12">{t("No open positions with lot data.")}</div>
                ) : (
                  <table className="w-full">
                    <thead className="border-b border-surface-border">
                      <tr>
                        {UNREALIZED_HEADINGS.map((h, i) => (
                          <th key={h} className={`${i >= 2 && i <= 7 ? "text-right" : "text-left"} px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider`}>{t(h)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {pagedUnrealized.map((u, i) => {
                        const up = u.unrealized_gain >= 0;
                        return (
                          <tr key={i} className="hover:bg-surface-hover transition-colors">
                            <td className="px-4 py-3 font-mono font-bold text-sm">
                              <TickerLink ticker={u.ticker}>{u.ticker}</TickerLink>
                            </td>
                            <td className="px-4 py-3 text-sm text-muted tabular-nums">{formatTableDate(u.buy_date)}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{formatQuantity(u.shares, "CZK")}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{formatSharedMoney(u.cost_basis, "USD")}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums font-medium">{formatSharedMoney(u.market_value, "USD")}</td>
                            <td className={`px-4 py-3 text-sm text-right tabular-nums font-medium ${up ? "text-gain" : "text-loss"}`}>
                              <span className="flex items-center justify-end gap-1">
                                {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                {formatSharedMoney(u.unrealized_gain, "USD")}
                              </span>
                            </td>
                            <td className={`px-4 py-3 text-sm text-right tabular-nums ${up ? "text-gain" : "text-loss"}`}>
                              <GainPercent value={u.gain_pct} />
                            </td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums text-muted">{t("{days}d", { days: u.holding_days })}</td>
                            <td className="px-4 py-3"><TermBadge term={u.term} /></td>
                            <td className="px-4 py-3 text-sm">
                              {u.cz_exempt_time_test ? (
                                <Badge tone="gain" title={t("Exempt from {date} (§4 ZDP)", { date: u.cz_exempt_date })}>{t("Exempt")}</Badge>
                              ) : (
                                <Badge
                                  tone="warn"
                                  className="tabular-nums"
                                  title={t("Tax-free if sold on or after {date} (§4 ZDP, 3-year time test)", { date: u.cz_exempt_date })}
                                >
                                  <Hourglass size={12} aria-hidden="true" />
                                  {t("{days}d", { days: u.cz_days_to_exemption })}
                                  <span className="font-normal">({formatTableDate(u.cz_exempt_date)})</span>
                                </Badge>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot className="border-t-2 border-surface-border bg-surface">
                      <tr>
                        <td className="px-4 py-3 text-sm font-bold" colSpan={3}>{t("Total Unrealized")}</td>
                        <td className="px-4 py-3 text-sm text-right tabular-nums font-medium">{fmt(unrealized.reduce((s, u) => s + u.cost_basis, 0))}</td>
                        <td className="px-4 py-3 text-sm text-right tabular-nums font-medium">{fmt(unrealized.reduce((s, u) => s + u.market_value, 0))}</td>
                        <td className={`px-4 py-3 text-sm text-right tabular-nums font-bold ${
                          unrealized.reduce((s, u) => s + u.unrealized_gain, 0) >= 0 ? "text-gain" : "text-loss"
                        }`}>
                          {fmt(unrealized.reduce((s, u) => s + u.unrealized_gain, 0))}
                        </td>
                        <td colSpan={4}></td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
              {unrealized.length > ROWS_PER_PAGE && (
                <div className="px-4">
                  <Pagination
                    offset={page * ROWS_PER_PAGE}
                    limit={ROWS_PER_PAGE}
                    total={unrealized.length}
                    onOffsetChange={(nextOffset) => setPage(Math.floor(nextOffset / ROWS_PER_PAGE))}
                    ariaLabel={t("Tax report unrealized gains pages")}
                  />
                </div>
              )}
              </>
            )}

            {tab === "dividends" && (
              <div className="overflow-x-auto">
                {!dividendIncome.length ? (
                  <div className="text-muted text-sm text-center py-12">
                    {year ? t("No dividend income in {year}.", { year }) : t("No dividend income.")}
                  </div>
                ) : (
                  <table className="w-full">
                    <thead className="border-b border-surface-border">
                      <tr>
                        <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">{t("Ticker")}</th>
                        <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">{t("Amount")}</th>
                        <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">{t("% of Total")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {dividendIncome.map((d) => (
                        <tr key={d.ticker} className="hover:bg-surface-hover transition-colors">
                          <td className="px-4 py-3 font-mono font-bold text-sm">
                            <TickerLink ticker={d.ticker}>{d.ticker}</TickerLink>
                          </td>
                          <td className="px-4 py-3 text-sm tabular-nums text-gain font-medium">{fmt(d.amount)}</td>
                          <td className="px-4 py-3 text-sm text-muted">
                            <div className="flex items-center gap-2">
                              <div className="w-24 bg-surface-hover rounded-full h-1.5">
                                <div
                                  className="bg-gain rounded-full h-1.5"
                                  style={{ width: `${summary.total_dividends > 0 ? (d.amount / summary.total_dividends * 100) : 0}%` }}
                                />
                              </div>
                              <span className="tabular-nums">
                                {summary.total_dividends > 0 ? (d.amount / summary.total_dividends * 100).toFixed(1) : 0}%
                              </span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="border-t-2 border-surface-border bg-surface">
                      <tr>
                        <td className="px-4 py-3 text-sm font-bold">{t("Total")}</td>
                        <td className="px-4 py-3 text-sm tabular-nums text-gain font-bold">{fmtMoney(summary.total_dividends, summary.total_dividends_czk)}</td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
            )}
          </div>
        </>
      </AsyncSection>
    </div>
  );
}
