// Pure derivations for the dashboard's summary cards (design variant A).
// Kept out of the components so the money math is unit-tested on its own.

// /portfolio/dividends reports annual_income in each ticker's own quote
// currency (pence for some UK listings), while /portfolio/holdings reports
// market_value in the display currency and current_price in the quote
// currency. market_value / (shares * current_price) is therefore exactly the
// rate the backend used for that holding, pence scaling included, so income
// converts with the same factor as the position's value.
export function summarizePassiveIncome({ dividends = [], holdings = [], totalValue = null, today }) {
  const byTicker = new Map(holdings.map((h) => [h.ticker, h]));
  let annualIncome = 0;
  let payers = 0;
  let next = null;

  for (const d of dividends) {
    if (d.income_status !== "estimated" || !(d.annual_income > 0)) continue;
    const h = byTicker.get(d.ticker);
    const quoteValue = h ? h.shares * h.current_price : 0;
    if (!(quoteValue > 0) || !(h.market_value > 0)) continue;
    annualIncome += d.annual_income * (h.market_value / quoteValue);
    payers += 1;
    if (d.ex_date && d.ex_date >= today && (!next || d.ex_date < next.date)) {
      next = { ticker: d.ticker, date: d.ex_date };
    }
  }

  const yieldPct = totalValue > 0 ? (annualIncome / totalValue) * 100 : totalValue == null ? null : 0;
  return { annualIncome, yieldPct, payers, next };
}

const EMPTY_HALF = { months: [], total: 0, monthlyAverage: 0 };

function convertEntries(entries = [], usdRate, keep) {
  return entries
    .filter((e) => keep(e.status))
    .map((e) => ({ ticker: e.ticker, name: e.name, status: e.status === "estimated" ? "forecasted" : e.status, amount: e.amount * usdRate }));
}

function finish(rows) {
  const total = rows.reduce((sum, r) => sum + r.amount, 0);
  return { months: rows, total, monthlyAverage: rows.length ? total / rows.length : 0 };
}

function receivedHalf(months, usdRate) {
  return finish(months.map((m) => ({
    month: m.month,
    amount: (m.paid || 0) * usdRate,
    entries: convertEntries(m.entries, usdRate, (s) => s === "paid"),
  })));
}

// Each upcoming month keeps its confirmed / forecasted split so the chart can
// stack them; `entries` carries the per-company payments for the tooltip.
function upcomingHalf(months, usdRate) {
  return finish(months.map((m) => {
    const confirmed = (m.confirmed || 0) * usdRate;
    const forecasted = (m.forecasted ?? m.estimated ?? 0) * usdRate;
    return {
      month: m.month,
      year: m.year,
      confirmed,
      forecasted,
      amount: confirmed + forecasted,
      entries: convertEntries(m.entries, usdRate, (s) => s !== "paid"),
    };
  }));
}

// /portfolio/dividends/forecast is in USD. `months` covers the current
// calendar year (`paid` = received, `estimated` = still expected); `outlook`
// is the rolling 12 months from this month, each payment confirmed (already
// dated by the provider) or forecasted (projected from past payments). The
// dashboard shows received-so-far (calendar year, up to the current month)
// beside the 12-month outlook. Older responses without `outlook` fall back to
// the rest of the calendar year.
export function splitDividendForecast(forecast, { monthIndex, usdRate = 1 }) {
  if (!forecast?.months?.length) return { received: EMPTY_HALF, upcoming: EMPTY_HALF };
  const outlook = forecast.outlook?.months;
  return {
    received: receivedHalf(forecast.months.slice(0, monthIndex + 1), usdRate),
    upcoming: upcomingHalf(outlook?.length ? outlook : forecast.months.slice(monthIndex), usdRate),
  };
}

// Allocation targets are optional and grouped by user-chosen names; a group
// whose name matches a breakdown category (e.g. "Stocks") supplies its target.
// Drift is measured against the weight shown in the same row so the numbers
// on screen always add up.
export function buildCompositionRows(breakdown = [], targetGroups = []) {
  const targets = new Map((targetGroups || []).map((g) => [String(g.group).trim().toLowerCase(), g.target_pct]));
  return breakdown.map((row) => {
    const targetPct = targets.has(row.name.toLowerCase()) ? targets.get(row.name.toLowerCase()) : null;
    return {
      name: row.name,
      value: row.value,
      weight: row.weight,
      targetPct,
      driftPct: targetPct == null ? null : Math.round((row.weight - targetPct) * 100) / 100,
    };
  });
}

// While a Trading 212 history backfill is still running, the transaction
// ledger is incomplete and the ledger-based net worth reads near zero. The
// broker's current positions snapshot is then the only current-value evidence,
// so the hero shows it instead. Returns null whenever the ledger should be
// trusted (no backfill, or it completed) or the snapshot cannot be valued in
// full in the display currency.
export function snapshotNetWorth({ positions, historyRun, currency }) {
  if (!historyRun || historyRun.state === "completed") return null;
  const rows = positions?.positions ?? [];
  if (!rows.length || positions.currency !== currency) return null;
  if (rows.some((p) => !Number.isFinite(p.market_value))) return null;
  return {
    positionsValue: rows.reduce((sum, p) => sum + p.market_value, 0),
    asOf: positions.as_of ?? null,
  };
}
