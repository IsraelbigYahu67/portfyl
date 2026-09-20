import { assertDemoPortfolio } from "./validateDemoPortfolio";

// Synthetic, versioned, fully client-side demo portfolio for the public
// /demo/* routes. No field here is derived from a real user's data, a live
// quote, or a real brokerage account -- see
// docs/superpowers/plans/2026-09-19-portfyl-public-demo.md's "Fixed product
// decisions" for the approved asset list, weights, and as-of date.

const AS_OF = "2026-09-18";
const CURRENCY = "USD";
const CASH = 5000;

function round2(n) {
  return Math.round(n * 100) / 100;
}

function round6(n) {
  return Math.round(n * 1e6) / 1e6;
}

function addDays(dateStr, days) {
  const d = new Date(`${dateStr}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function addMonths(dateStr, months) {
  const d = new Date(`${dateStr}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + months);
  return d.toISOString().slice(0, 10);
}

// Fixed product decisions (see the public-demo plan): symbol order, display
// names, sector/role, and weights are approved and must not change.
export const HOLDING_SEEDS = [
  {
    symbol: "VUAA", name: "Vanguard S&P 500 UCITS ETF", sector: "Diversified ETF", country: "Ireland",
    assetType: "ETF", weight: 18, currentPrice: 120.00, previousClose: 119.52, dayChangePercent: 0.40, dividendYield: 1.3,
    marketCap: null, pe: null, forwardPe: null, eps: null, revenueGrowth: null, profitMargin: null,
    week52Low: 105.20, week52High: 128.90, nextEarnings: null,
    description: "Vanguard S&P 500 UCITS ETF tracks the S&P 500 index of large-cap U.S. companies. It offers broad, low-cost exposure to the U.S. equity market in a single European-listed fund.",
  },
  {
    symbol: "MSFT", name: "Microsoft", sector: "Information Technology", country: "United States",
    assetType: "Stock", weight: 12, currentPrice: 480.00, previousClose: 474.31, dayChangePercent: 1.20, dividendYield: 0.7,
    marketCap: 3_560_000_000_000, pe: 34.2, forwardPe: 30.1, eps: 14.03, revenueGrowth: 14.2, profitMargin: 35.8,
    week52Low: 390.50, week52High: 495.20, nextEarnings: "2026-10-22",
    description: "Microsoft develops software, cloud services, and hardware, anchored by Azure, Windows, and Office. Its cloud and AI infrastructure businesses have been the primary growth driver in recent years.",
  },
  {
    symbol: "JPM", name: "JPMorgan Chase", sector: "Financials", country: "United States",
    assetType: "Stock", weight: 10, currentPrice: 220.00, previousClose: 220.65, dayChangePercent: -0.30, dividendYield: 2.1,
    marketCap: 620_000_000_000, pe: 12.4, forwardPe: 11.8, eps: 17.74, revenueGrowth: 8.1, profitMargin: 34.5,
    week52Low: 180.30, week52High: 235.60, nextEarnings: "2026-10-14",
    description: "JPMorgan Chase is the largest U.S. bank by assets, spanning consumer banking, investment banking, and asset management. Its scale and diversified revenue base have supported steady profitability.",
  },
  {
    symbol: "JNJ", name: "Johnson & Johnson", sector: "Health Care", country: "United States",
    assetType: "Stock", weight: 10, currentPrice: 165.00, previousClose: 164.72, dayChangePercent: 0.10, dividendYield: 2.9,
    marketCap: 400_000_000_000, pe: 15.8, forwardPe: 14.9, eps: 10.44, revenueGrowth: 5.3, profitMargin: 20.1,
    week52Low: 145.10, week52High: 172.40, nextEarnings: "2026-10-15",
    description: "Johnson & Johnson is a diversified healthcare company focused on pharmaceuticals and medical devices following its consumer-health spinoff. It has a long history of steady dividend growth.",
  },
  {
    symbol: "XOM", name: "Exxon Mobil", sector: "Energy", country: "United States",
    assetType: "Stock", weight: 9, currentPrice: 115.00, previousClose: 116.02, dayChangePercent: -0.80, dividendYield: 3.3,
    marketCap: 460_000_000_000, pe: 13.6, forwardPe: 12.9, eps: 8.46, revenueGrowth: -2.1, profitMargin: 10.2,
    week52Low: 98.40, week52High: 126.70, nextEarnings: "2026-10-31",
    description: "ExxonMobil is an integrated oil and gas major spanning upstream production, refining, and chemicals. Its earnings are closely tied to global energy prices.",
  },
  {
    symbol: "PG", name: "Procter & Gamble", sector: "Consumer Staples", country: "United States",
    assetType: "Stock", weight: 9, currentPrice: 170.00, previousClose: 169.55, dayChangePercent: 0.20, dividendYield: 2.4,
    marketCap: 400_000_000_000, pe: 24.3, forwardPe: 22.7, eps: 7.00, revenueGrowth: 3.2, profitMargin: 18.4,
    week52Low: 155.60, week52High: 180.20, nextEarnings: "2026-10-18",
    description: "Procter & Gamble makes household and personal-care staples sold under brands like Tide, Pampers, and Gillette. Its portfolio of everyday consumer products supports resilient demand.",
  },
  {
    symbol: "AMZN", name: "Amazon", sector: "Consumer Discretionary", country: "United States",
    assetType: "Stock", weight: 9, currentPrice: 210.00, previousClose: 207.88, dayChangePercent: 1.50, dividendYield: 0,
    marketCap: 2_200_000_000_000, pe: 41.5, forwardPe: 33.2, eps: 5.06, revenueGrowth: 11.4, profitMargin: 8.9,
    week52Low: 160.90, week52High: 225.30, nextEarnings: "2026-10-29",
    description: "Amazon operates the largest U.S. e-commerce marketplace alongside its AWS cloud computing division. AWS contributes a disproportionate share of operating profit relative to revenue.",
  },
  {
    symbol: "CAT", name: "Caterpillar", sector: "Industrials", country: "United States",
    assetType: "Stock", weight: 8, currentPrice: 370.00, previousClose: 372.90, dayChangePercent: -0.50, dividendYield: 1.8,
    marketCap: 190_000_000_000, pe: 17.9, forwardPe: 16.4, eps: 20.67, revenueGrowth: 4.6, profitMargin: 15.3,
    week52Low: 295.40, week52High: 395.80, nextEarnings: "2026-10-21",
    description: "Caterpillar manufactures construction, mining, and industrial equipment sold worldwide. Its results track global infrastructure spending and commodity-extraction activity.",
  },
  {
    symbol: "NEE", name: "NextEra Energy", sector: "Utilities", country: "United States",
    assetType: "Stock", weight: 8, currentPrice: 78.00, previousClose: 77.65, dayChangePercent: 0.60, dividendYield: 2.6,
    marketCap: 160_000_000_000, pe: 21.6, forwardPe: 19.8, eps: 3.61, revenueGrowth: 6.7, profitMargin: 22.9,
    week52Low: 62.30, week52High: 84.50, nextEarnings: "2026-10-23",
    description: "NextEra Energy is a Florida-based utility and one of the largest generators of wind and solar power in the world. Its regulated utility and renewables businesses both contribute to earnings.",
  },
  {
    symbol: "PLD", name: "Prologis", sector: "Real Estate", country: "United States",
    assetType: "Stock", weight: 7, currentPrice: 130.00, previousClose: 129.40, dayChangePercent: -0.20, dividendYield: 3.1,
    marketCap: 120_000_000_000, pe: 33.4, forwardPe: 29.6, eps: 3.89, revenueGrowth: 7.8, profitMargin: 38.6,
    week52Low: 105.70, week52High: 142.10, nextEarnings: "2026-10-20",
    description: "Prologis is a REIT that owns and leases logistics and warehouse facilities globally. Its properties support e-commerce fulfillment and supply-chain operations for major tenants.",
  },
];

function buildHoldingsAndTransactions() {
  const holdings = [];
  const transactions = [];
  let txId = 1;

  HOLDING_SEEDS.forEach((seed, index) => {
    const marketValue = seed.weight * 1000;
    const quantity = round6(marketValue / seed.currentPrice);
    const averageCost = round2(seed.currentPrice * 0.9);
    // Exact for every weight here: marketValue is a whole number of dollars
    // and 0.9 * (multiple of 1000) always lands on a whole cent, so no
    // rounding drift enters the two-lot split below.
    const costBasis = round2(marketValue * 0.9);
    const dayChange = round2(seed.currentPrice * (seed.dayChangePercent / 100));

    holdings.push({
      symbol: seed.symbol, name: seed.name, sector: seed.sector, country: seed.country,
      currency: CURRENCY, assetType: seed.assetType, weight: seed.weight, quantity, currentPrice: seed.currentPrice,
      marketValue, averageCost, dayChange, dayChangePercent: seed.dayChangePercent, dividendYield: seed.dividendYield,
      fundamentals: {
        price: seed.currentPrice, previousClose: seed.previousClose, marketCap: seed.marketCap,
        pe: seed.pe, forwardPe: seed.forwardPe, eps: seed.eps, revenueGrowth: seed.revenueGrowth,
        profitMargin: seed.profitMargin, dividendYield: seed.dividendYield, week52Low: seed.week52Low,
        week52High: seed.week52High, nextEarnings: seed.nextEarnings, description: seed.description,
      },
    });

    // Two staggered BUY lots. qty2 is derived by subtraction so the pair
    // always sums to exactly `quantity`; amount2 is derived the same way
    // against the exact per-symbol costBasis so the pair always sums to
    // exactly `costBasis` (no independent-rounding drift across 20 lots).
    const qty1 = round6(quantity * 0.55);
    const qty2 = round6(quantity - qty1);
    const amount1 = round2(qty1 * averageCost);
    const amount2 = round2(costBasis - amount1);
    const date1 = addDays("2024-10-05", index * 3);
    const date2 = addDays("2025-07-05", index * 3);

    transactions.push(
      { id: txId++, date: date1, symbol: seed.symbol, type: "BUY", quantity: qty1, price: averageCost, amount: amount1 },
      { id: txId++, date: date2, symbol: seed.symbol, type: "BUY", quantity: qty2, price: averageCost, amount: amount2 }
    );
  });

  return { holdings, transactions };
}

function buildPerformanceAndBenchmark() {
  const POINTS = 105;
  const raw = [];
  for (let index = 0; index < POINTS; index++) {
    const cycle = Math.sin(index / 7) * 900 + Math.cos(index / 13) * 450;
    const value = 72000 + index * 310 + cycle;
    const invested = round2(70000 + Math.floor(index / 13) * 2500);
    raw.push({ value, invested });
  }
  // Offset every value by the same constant so the final point lands on
  // exactly 105,000 -- not a special case for the last index alone.
  const offset = 105000 - raw[POINTS - 1].value;

  const performance = [];
  const sp500 = [];
  let previousValue = null;
  for (let index = 0; index < POINTS; index++) {
    const date = addDays(AS_OF, -7 * (POINTS - 1 - index));
    const value = round2(raw[index].value + offset);
    const invested = raw[index].invested;
    const totalPnl = round2(value - invested);
    const totalPnlPct = round2((totalPnl / invested) * 100);
    const pnl = previousValue == null ? 0 : round2(value - previousValue);
    const pnlPct = previousValue == null || previousValue === 0 ? 0 : round2((pnl / previousValue) * 100);
    performance.push({ date, value, invested, pnl, pnl_pct: pnlPct, total_pnl: totalPnl, total_pnl_pct: totalPnlPct });
    previousValue = value;

    sp500.push({ date, pct: round2(index * 0.21 + Math.sin(index / 9) * 1.8) });
  }

  return { performance, sp500 };
}

const DIVIDEND_PAYERS = [
  { symbol: "MSFT", amount: 70 },
  { symbol: "JPM", amount: 55 },
  { symbol: "JNJ", amount: 45 },
  { symbol: "XOM", amount: 60 },
  { symbol: "PG", amount: 50 },
  { symbol: "NEE", amount: 35 },
  { symbol: "PLD", amount: 40 },
];
const DIVIDEND_QUARTERS = 8;

function buildDividends() {
  const dividends = [];
  let id = 1;
  for (let q = 0; q < DIVIDEND_QUARTERS; q++) {
    const date = addMonths("2024-12-15", q * 3);
    for (const payer of DIVIDEND_PAYERS) {
      dividends.push({ id: id++, date, symbol: payer.symbol, amount: payer.amount, currency: CURRENCY });
    }
  }
  const dividendTotal = round2(dividends.reduce((sum, d) => sum + d.amount, 0));
  return { dividends, dividendTotal };
}

function buildDemoPortfolio() {
  const { holdings, transactions } = buildHoldingsAndTransactions();
  const { performance, sp500 } = buildPerformanceAndBenchmark();
  const { dividends, dividendTotal } = buildDividends();

  return {
    version: 1,
    asOf: AS_OF,
    currency: CURRENCY,
    cash: CASH,
    holdings,
    transactions,
    dividends,
    dividendTotal,
    performance,
    benchmarks: { sp500 },
    benchmarkMeta: [{ key: "sp500", label: "S&P 500", color: "var(--chart-5)" }],
  };
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}

const built = assertDemoPortfolio(buildDemoPortfolio());

// Frozen recursively in dev/test so demo components (which must be
// read-only) cannot mutate the shared fixture. import.meta.env.PROD skips
// the (cheap but non-zero) recursive freeze in production builds.
export const demoPortfolio = import.meta.env.PROD ? built : deepFreeze(built);
