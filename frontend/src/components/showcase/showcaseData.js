// Made-up sample data for the landing-page mini demos (and the shared demo
// panels). Nothing here comes from a real person, account or quote: the
// numbers are invented and the landing page labels them as such. The data is
// frozen, versioned (`portfyl-showcase-v1`) and has no clock: "now" is
// SHOWCASE_AS_OF, never the current date.

export const SHOWCASE_AS_OF = "2026-09-18";

// One fixed sample rate so every figure is reproducible. 1 EUR = 25 CZK,
// 1 USD = 23 CZK. This is not a live rate and the demo says so.
export const SHOWCASE_RATES_TO_CZK = { CZK: 1, EUR: 25, USD: 23 };

const ID_PREFIX = "portfyl-showcase-v1";

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}

function holding(portfolioKey, symbol, name, sector, country, currency, assetType, marketValue) {
  return {
    id: `${ID_PREFIX}-${portfolioKey}-${symbol}`,
    symbol, name, sector, country, currency, assetType, marketValue,
  };
}

export const SHOWCASE_PORTFOLIOS = deepFreeze([
  {
    id: `${ID_PREFIX}-long`,
    key: "long",
    baseCurrency: "EUR",
    cash: 1200,
    holdings: [
      holding("long", "VWCE", "Vanguard FTSE All-World UCITS ETF", "Diversified ETF", "Ireland", "EUR", "ETF", 18400),
      holding("long", "ASML", "ASML Holding", "Information Technology", "Netherlands", "EUR", "Stock", 6150.5),
      holding("long", "SAP", "SAP SE", "Information Technology", "Germany", "EUR", "Stock", 4820),
      holding("long", "SIE", "Siemens AG", "Industrials", "Germany", "EUR", "Stock", 3980.25),
      holding("long", "MC", "LVMH", "Consumer Discretionary", "France", "EUR", "Stock", 3105.75),
    ],
  },
  {
    id: `${ID_PREFIX}-dividend`,
    key: "dividend",
    baseCurrency: "USD",
    cash: 2400,
    holdings: [
      holding("dividend", "SCHD", "Schwab US Dividend Equity ETF", "Diversified ETF", "United States", "USD", "ETF", 12980),
      holding("dividend", "KO", "Coca-Cola", "Consumer Staples", "United States", "USD", "Stock", 9120.4),
      holding("dividend", "JNJ", "Johnson & Johnson", "Health Care", "United States", "USD", "Stock", 8040),
      holding("dividend", "O", "Realty Income", "Real Estate", "United States", "USD", "Stock", 6310.75),
      holding("dividend", "XOM", "Exxon Mobil", "Energy", "United States", "USD", "Stock", 5470.2),
      holding("dividend", "VZ", "Verizon", "Communication Services", "United States", "USD", "Stock", 4260.9),
    ],
  },
  {
    id: `${ID_PREFIX}-growth`,
    key: "growth",
    baseCurrency: "CZK",
    cash: 85000,
    holdings: [
      holding("growth", "CEZ", "ČEZ", "Utilities", "Czech Republic", "CZK", "Stock", 142500),
      holding("growth", "KOMB", "Komerční banka", "Financials", "Czech Republic", "CZK", "Stock", 118300),
      holding("growth", "MONET", "Moneta Money Bank", "Financials", "Czech Republic", "CZK", "Stock", 64900),
      holding("growth", "CSPX", "iShares Core S&P 500 UCITS ETF", "Diversified ETF", "Ireland", "USD", "ETF", 6100),
      holding("growth", "NVDA", "NVIDIA", "Information Technology", "United States", "USD", "Stock", 3150),
      holding("growth", "AMZN", "Amazon", "Consumer Discretionary", "United States", "USD", "Stock", 2480.6),
    ],
  },
]);

const QUARTER_DATES = [
  "2021-12-15", "2022-03-15", "2022-06-15", "2022-09-15", "2022-12-15",
  "2023-03-15", "2023-06-15", "2023-09-15", "2023-12-15", "2024-03-15",
  "2024-06-15", "2024-09-15", "2024-12-15", "2025-03-15", "2025-06-15",
  "2025-09-15", "2025-12-15", "2026-03-15", "2026-06-15", "2026-09-15",
];

const PE_VALUES = {
  MSFT: [31.8, 33.4, 29.9, 28.1, 27.4, 29.6, 31.2, 32.7, 30.5, 31.9, 33.8, 35.1, 34.4, 33.0, 32.2, 33.9, 35.6, 36.2, 35.0, 34.2],
  JNJ: [17.2, 16.8, 16.1, 15.4, 15.9, 16.7, 17.5, 17.1, 16.3, 15.6, 14.9, 14.4, 15.2, 15.8, 16.4, 16.0, 15.5, 15.1, 15.4, 15.8],
  PG: [26.1, 25.4, 24.6, 23.9, 24.8, 25.9, 26.7, 26.2, 25.3, 24.4, 23.6, 22.9, 23.5, 24.2, 25.1, 25.6, 25.0, 24.4, 23.9, 24.3],
};

// Five years of quarterly trailing P/E per ticker (the same shape the stock
// page's valuation history uses). The last point matches the P/E of the
// holding in demoPortfolio.js.
export const SHOWCASE_PE_HISTORY = deepFreeze(Object.fromEntries(
  Object.entries(PE_VALUES).map(([symbol, values]) => [
    symbol,
    values.map((trailing_pe, index) => ({ bucket: QUARTER_DATES[index], trailing_pe })),
  ]),
));

function round2(value) {
  return Math.round(value * 100) / 100;
}

export function convertAmount(amount, from, to) {
  const fromRate = SHOWCASE_RATES_TO_CZK[from];
  const toRate = SHOWCASE_RATES_TO_CZK[to];
  if (fromRate == null || toRate == null) throw new Error(`Unknown showcase currency: ${from} -> ${to}`);
  if (from === to) return round2(amount);
  return round2((amount * fromRate) / toRate);
}

// Weights rounded to 2 decimals that add up to exactly 100: the rounding
// remainder goes to the largest row.
function weightsOf(values) {
  const total = values.reduce((sum, value) => sum + value, 0);
  const weights = values.map((value) => (total > 0 ? round2((value / total) * 100) : 0));
  if (total > 0) {
    const largest = values.indexOf(Math.max(...values));
    const drift = round2(100 - weights.reduce((sum, weight) => sum + weight, 0));
    weights[largest] = round2(weights[largest] + drift);
  }
  return weights;
}

// Every holding of every sample portfolio with `marketValue` converted to
// `displayCurrency` (at the fixed sample rate). `currency` stays the currency
// the holding is quoted in, so grouping by currency still shows all of them.
export function showcaseHoldings(displayCurrency) {
  const rows = SHOWCASE_PORTFOLIOS.flatMap((portfolio) => portfolio.holdings.map((item) => ({
    ...item,
    portfolioKey: portfolio.key,
    marketValue: convertAmount(item.marketValue, item.currency, displayCurrency),
  })));
  const weights = weightsOf(rows.map((row) => row.marketValue));
  return rows.map((row, index) => ({ ...row, weight: weights[index] }));
}

// Net worth of each sample portfolio (positions + cash) in `displayCurrency`.
export function portfolioTotals(displayCurrency) {
  const holdings = showcaseHoldings(displayCurrency);
  const rows = SHOWCASE_PORTFOLIOS.map((portfolio) => {
    const positions = holdings
      .filter((row) => row.portfolioKey === portfolio.key)
      .reduce((sum, row) => sum + row.marketValue, 0);
    const cash = convertAmount(portfolio.cash, portfolio.baseCurrency, displayCurrency);
    return { key: portfolio.key, value: round2(positions + cash), cash };
  });
  const weights = weightsOf(rows.map((row) => row.value));
  return rows.map((row, index) => ({ ...row, weight: weights[index] }));
}
