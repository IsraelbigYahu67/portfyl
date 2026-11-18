// Pure maths for the shared showcase panels (the public /demo pages and the
// landing-page mini demos). No clock, no window: "now" always comes from the
// caller (an `asOf` date), so the same input gives the same output on the
// server, in the browser and in tests.

const PERIODS_PER_YEAR = 52;

function finite(value) {
  return Number.isFinite(value) ? value : 0;
}

const GROUP_LABEL = {
  holdings: (holding) => holding.symbol,
  sectors: (holding) => holding.sector,
  countries: (holding) => holding.country,
  currencies: (holding) => holding.currency,
  assetTypes: (holding) => holding.assetType,
};

// key: holdings | sectors | countries | currencies | assetTypes
export function groupHoldings(holdings, key) {
  const labelFor = GROUP_LABEL[key];
  if (!labelFor) throw new Error(`Unknown allocation grouping: ${key}`);
  const rows = new Map();
  for (const holding of holdings) {
    const name = labelFor(holding);
    const current = rows.get(name) || { name, value: 0, weight: 0 };
    current.value += holding.marketValue;
    current.weight += holding.weight;
    rows.set(name, current);
  }
  return [...rows.values()].map((row) => ({
    ...row,
    value: Number(row.value.toFixed(2)),
    weight: Number(row.weight.toFixed(2)),
  }));
}

export function buildSummary(data) {
  const lastPoint = data.performance.at(-1);
  const previousPoint = data.performance.at(-2) || lastPoint;
  const totalValue = data.holdings.reduce((sum, holding) => sum + holding.marketValue, 0);
  const totalInvested = lastPoint.invested;
  const totalPnl = totalValue - data.transactions.reduce((sum, transaction) => sum + transaction.amount, 0);
  const dayChange = lastPoint.value - previousPoint.value;
  const dayChangePercent = previousPoint.value === 0 ? 0 : (dayChange / previousPoint.value) * 100;

  return {
    net_worth: totalValue + data.cash,
    total_value: totalValue,
    cash: data.cash,
    total_invested: totalInvested,
    total_pnl: totalPnl,
    total_dividends: data.dividendTotal,
    holdings_count: data.holdings.length,
    day_change: dayChange,
    day_change_percent: dayChangePercent,
  };
}

export function calculateMetrics(performance) {
  const values = performance.map((point) => point.value);
  const weeklyReturns = values.slice(1).map((value, index) => finite(value / values[index] - 1));
  const totalReturn = finite(values.at(-1) / values[0] - 1);
  const annualizedReturn = finite((1 + totalReturn) ** (PERIODS_PER_YEAR / weeklyReturns.length) - 1);
  const mean = weeklyReturns.reduce((sum, value) => sum + value, 0) / weeklyReturns.length;
  const variance = weeklyReturns.length > 1
    ? weeklyReturns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (weeklyReturns.length - 1)
    : 0;
  const volatility = finite(Math.sqrt(variance) * Math.sqrt(PERIODS_PER_YEAR));
  const sharpe = volatility === 0 ? 0 : finite(annualizedReturn / volatility);

  let peak = values[0];
  let maximumDrawdown = 0;
  for (const value of values) {
    peak = Math.max(peak, value);
    maximumDrawdown = Math.min(maximumDrawdown, finite(value / peak - 1));
  }

  const months = new Map();
  for (const point of performance) {
    const key = point.date.slice(0, 7);
    const period = months.get(key) || { key, first: point.value, last: point.value };
    period.last = point.value;
    months.set(key, period);
  }
  const monthReturns = [...months.values()].map((month) => ({
    ...month,
    pct: finite(month.last / month.first - 1),
  }));
  const bestMonth = monthReturns.reduce((best, month) => month.pct > best.pct ? month : best, monthReturns[0]);
  const worstMonth = monthReturns.reduce((worst, month) => month.pct < worst.pct ? month : worst, monthReturns[0]);

  return {
    totalReturn, annualizedReturn, volatility, sharpe, maximumDrawdown, bestMonth, worstMonth,
    growth: performance.map((point) => ({
      ...point,
      pnl_pct: finite(point.value / values[0] - 1) * 100,
    })),
  };
}

export function quarterKey(date) {
  const year = date.slice(0, 4);
  const quarter = Math.floor((Number(date.slice(5, 7)) - 1) / 3) + 1;
  return `${year} Q${quarter}`;
}

export function sumBy(rows, keyFor) {
  const groups = new Map();
  for (const row of rows) {
    const key = keyFor(row);
    groups.set(key, (groups.get(key) || 0) + row.amount);
  }
  return [...groups.entries()].map(([key, amount]) => ({ key, amount })).sort((a, b) => b.key.localeCompare(a.key));
}

export function stockHeaderData(holding) {
  const f = holding.fundamentals;
  return {
    ticker: holding.symbol, name: holding.name, currency: holding.currency,
    price: f.price, change: holding.dayChange, change_percent: holding.dayChangePercent,
    sector: holding.sector, country: holding.country, market_cap: f.marketCap,
    ratios: { pe: f.pe, forward_pe: f.forwardPe, div_yield: f.dividendYield },
    fifty_two_week_low: f.week52Low, fifty_two_week_high: f.week52High,
  };
}

// Portfyl values a stock against its own five-year average P/E, not today's
// P/E. Averages the `trailing_pe` of every point in the five years up to the
// last point; points without a P/E are ignored. null when nothing is left.
export function fiveYearAveragePe(points) {
  const dated = (points || []).filter((point) => point?.bucket);
  if (!dated.length) return null;
  const last = dated.reduce((latest, point) => (point.bucket > latest ? point.bucket : latest), dated[0].bucket);
  const windowStart = `${Number(last.slice(0, 4)) - 5}${last.slice(4)}`;
  const values = dated
    .filter((point) => point.bucket >= windowStart && point.bucket <= last)
    .map((point) => point.trailing_pe)
    .filter((value) => Number.isFinite(value));
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function sumByTicker(rows, status) {
  const byTicker = new Map();
  for (const row of rows) byTicker.set(row.symbol, (byTicker.get(row.symbol) || 0) + row.amount);
  return [...byTicker.entries()]
    .map(([ticker, amount]) => ({ ticker, status, amount }))
    .sort((a, b) => b.amount - a.amount || a.ticker.localeCompare(b.ticker));
}

function total(rows) {
  return rows.reduce((sum, row) => sum + row.amount, 0);
}

function round2(value) {
  return Math.round(value * 100) / 100;
}

// A dividend forecast in the shape /portfolio/dividends/forecast returns (and
// lib/dashboardSummaries.splitDividendForecast reads), built from sample
// dividend events. "Now" is `asOf` (YYYY-MM-DD), never the clock:
// - `months`: the calendar year of `asOf`; `paid` only up to `asOf`.
// - `outlook`: the 12 months starting with the month of `asOf`. It repeats the
//   same months of the previous year as an estimate (`forecasted`); payments
//   already dated after `asOf` count as `confirmed`.
export function buildDividendForecast(dividends, asOf) {
  const year = Number(asOf.slice(0, 4));
  const monthIndex = Number(asOf.slice(5, 7)) - 1;
  const inMonth = (row, y, m) => Number(row.date.slice(0, 4)) === y && Number(row.date.slice(5, 7)) - 1 === m;

  const months = MONTHS.map((month, m) => {
    const paidRows = dividends.filter((row) => inMonth(row, year, m) && row.date <= asOf);
    const estimatedRows = m > monthIndex ? dividends.filter((row) => inMonth(row, year - 1, m)) : [];
    return {
      month,
      paid: round2(total(paidRows)),
      estimated: round2(total(estimatedRows)),
      entries: [...sumByTicker(paidRows, "paid"), ...sumByTicker(estimatedRows, "estimated")],
    };
  });

  const outlookMonths = Array.from({ length: 12 }, (_, offset) => {
    const m = (monthIndex + offset) % 12;
    const y = year + Math.floor((monthIndex + offset) / 12);
    const confirmedRows = dividends.filter((row) => inMonth(row, y, m) && row.date > asOf);
    const paidRows = dividends.filter((row) => inMonth(row, y, m) && row.date <= asOf);
    const previousRows = dividends.filter((row) => inMonth(row, y - 1, m));
    const forecasted = Math.max(0, total(previousRows) - total(paidRows) - total(confirmedRows));
    const forecastShare = total(previousRows) > 0 ? forecasted / total(previousRows) : 0;
    const forecastRows = previousRows.map((row) => ({ ...row, amount: row.amount * forecastShare }));
    return {
      month: MONTHS[m],
      year: y,
      confirmed: round2(total(confirmedRows)),
      forecasted: round2(forecasted),
      entries: [...sumByTicker(confirmedRows, "confirmed"), ...sumByTicker(forecastRows.filter((row) => row.amount > 0), "forecasted")],
    };
  });

  return {
    year,
    months,
    outlook: { months: outlookMonths },
    total_paid_all_time: round2(total(dividends.filter((row) => row.date <= asOf))),
  };
}
