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

function half(months, key, usdRate) {
  const rows = months.map((m) => ({ month: m.month, amount: (m[key] || 0) * usdRate }));
  const total = rows.reduce((sum, r) => sum + r.amount, 0);
  return { months: rows, total, monthlyAverage: rows.length ? total / rows.length : 0 };
}

// /portfolio/dividends/forecast covers the current calendar year in USD:
// `paid` for money already received, `estimated` for projected payments from
// this month on. The dashboard shows them as two cards, split at the current
// month (which can hold both a paid and a still-expected payment).
export function splitDividendForecast(forecast, { monthIndex, usdRate = 1 }) {
  if (!forecast?.months?.length) return { received: EMPTY_HALF, upcoming: EMPTY_HALF };
  return {
    received: half(forecast.months.slice(0, monthIndex + 1), "paid", usdRate),
    upcoming: half(forecast.months.slice(monthIndex), "estimated", usdRate),
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
