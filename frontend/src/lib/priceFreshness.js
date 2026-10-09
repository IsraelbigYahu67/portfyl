// Human-readable quote freshness for the price fields the backend attaches to
// /portfolio/summary (prices_as_of, price_delay_minutes, price_source) and to
// each /portfolio/holdings row (price_status, price_as_of, price_source).
// `locale`/`timeZone` exist for deterministic tests; the app uses the browser's.

const STATUS_TEXT = {
  live: "real-time",
  delayed: "delayed",
  closed: "market closed",
  stale: "price is out of date",
  unknown: "quote time unavailable",
};

function formatQuoteTime(iso, { locale, timeZone } = {}) {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return null;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(new Date(ms));
}

export function priceFreshnessLine(summary, opts) {
  if (!summary || !summary.holdings_count || !("prices_as_of" in summary)) return null;
  const source = summary.price_source || "market data provider";
  const quoteTime = summary.prices_as_of ? formatQuoteTime(summary.prices_as_of, opts) : null;
  if (!quoteTime) return `Prices from ${source} · quote time unavailable`;
  const delay = summary.price_delay_minutes > 0 ? ` · delayed up to ${summary.price_delay_minutes} min` : "";
  return `Prices from ${source}${delay} · last quote ${quoteTime}`;
}

export function priceFreshnessTitle(holding, opts) {
  if (!holding?.price_status) return null;
  const source = holding.price_source || "market data provider";
  if (holding.price_status === "missing") {
    return `${source} · no current price; this holding is valued at 0`;
  }
  const parts = [source, STATUS_TEXT[holding.price_status] || holding.price_status];
  const quoteTime = holding.price_as_of ? formatQuoteTime(holding.price_as_of, opts) : null;
  if (quoteTime) parts.push(`last quote ${quoteTime}`);
  return [...new Set(parts)].join(" · ");
}

export const hasPriceProblem = (holding) =>
  holding?.price_status === "missing" || holding?.price_status === "stale";
