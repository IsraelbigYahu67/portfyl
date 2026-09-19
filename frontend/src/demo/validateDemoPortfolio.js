const EXPECTED_SYMBOLS = ["VUAA", "MSFT", "JPM", "JNJ", "XOM", "PG", "AMZN", "CAT", "NEE", "PLD"];
const CENT = 0.01;
const QUANTITY_TOLERANCE = 0.00001;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function fail(message) {
  throw new Error(`assertDemoPortfolio: ${message}`);
}

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function isValidDate(value) {
  if (typeof value !== "string" || !DATE_RE.test(value)) return false;
  const d = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value;
}

function checkNumericFields(obj, fields, where) {
  for (const field of fields) {
    if (!isFiniteNumber(obj[field])) {
      fail(`${where} has a non-finite ${field} (${obj[field]})`);
    }
  }
}

/**
 * Validates a demo portfolio fixture and returns it unchanged when every
 * invariant holds. Every failure names the broken invariant so it's
 * diagnosable from the thrown message alone.
 */
export function assertDemoPortfolio(data) {
  if (!data || typeof data !== "object") fail("fixture is missing or not an object");
  if (!isValidDate(data.asOf)) fail(`asOf is missing or not a valid YYYY-MM-DD date (${data.asOf})`);
  if (data.currency !== "USD") fail(`currency must be USD (got ${data.currency})`);
  if (!isFiniteNumber(data.cash) || data.cash <= 0) fail(`cash must be a positive number (got ${data.cash})`);

  const holdings = data.holdings;
  if (!Array.isArray(holdings) || holdings.length !== 10) {
    fail(`holdings must contain exactly 10 entries (got ${holdings?.length})`);
  }

  const symbols = holdings.map((h) => h.symbol);
  if (JSON.stringify(symbols) !== JSON.stringify(EXPECTED_SYMBOLS)) {
    fail(`holdings symbols/order must exactly match ${EXPECTED_SYMBOLS.join(",")} (got ${symbols.join(",")})`);
  }
  if (new Set(symbols).size !== symbols.length) fail("holdings contain a duplicate symbol");

  const sectors = holdings.map((h) => h.sector);
  if (sectors.some((s) => !s || typeof s !== "string")) fail("every holding must have a non-empty sector");
  if (new Set(sectors).size !== sectors.length) fail("every holding must have a unique sector/role");

  let weightTotal = 0;
  let marketValueTotal = 0;
  for (const holding of holdings) {
    checkNumericFields(
      holding,
      ["weight", "quantity", "currentPrice", "marketValue", "averageCost", "dayChange", "dayChangePercent", "dividendYield"],
      `holding ${holding.symbol}`
    );
    weightTotal += holding.weight;
    marketValueTotal += holding.marketValue;
  }
  if (Math.abs(weightTotal - 100) > CENT) {
    fail(`holding weights must sum to 100 within 0.01 (got ${weightTotal})`);
  }
  if (Math.abs(marketValueTotal - 100000) > CENT) {
    fail(`holding market values must sum to USD 100,000 within one cent (got ${marketValueTotal})`);
  }

  if (!Array.isArray(data.transactions) || data.transactions.length === 0) {
    fail("transactions must be a non-empty array");
  }
  for (const holding of holdings) {
    const lots = data.transactions.filter((t) => t.symbol === holding.symbol && t.type === "BUY");
    if (lots.length === 0) fail(`${holding.symbol} has no BUY transactions`);
    const lotQty = lots.reduce((sum, t) => sum + t.quantity, 0);
    if (Math.abs(lotQty - holding.quantity) > QUANTITY_TOLERANCE) {
      fail(`${holding.symbol}'s BUY transaction quantities (${lotQty}) do not reconcile with its holding quantity (${holding.quantity})`);
    }
  }

  if (!Array.isArray(data.performance) || data.performance.length === 0) {
    fail("performance history is missing or empty");
  }
  for (const point of data.performance) {
    if (!isValidDate(point.date)) fail(`performance point has an invalid date (${point.date})`);
    checkNumericFields(point, ["value", "invested"], `performance point ${point.date}`);
  }
  const lastPoint = data.performance[data.performance.length - 1];
  if (lastPoint.date !== data.asOf) {
    fail(`performance history must end on asOf (${data.asOf}), got ${lastPoint.date}`);
  }

  if (!Array.isArray(data.dividends)) fail("dividends must be an array");
  for (const row of data.dividends) {
    if (!isValidDate(row.date)) fail(`dividend row has an invalid date (${row.date})`);
    if (!isFiniteNumber(row.amount)) fail(`dividend row for ${row.symbol} has a non-finite amount`);
  }
  const dividendSum = Math.round(data.dividends.reduce((sum, d) => sum + d.amount, 0) * 100) / 100;
  if (!isFiniteNumber(data.dividendTotal) || Math.abs(dividendSum - data.dividendTotal) > CENT) {
    fail(`dividendTotal (${data.dividendTotal}) does not reconcile with the sum of dividend rows (${dividendSum})`);
  }

  return data;
}
