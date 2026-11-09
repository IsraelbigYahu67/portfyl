// Human-readable quote freshness for the price fields the backend attaches to
// /portfolio/summary (prices_as_of, price_delay_minutes, price_source) and to
// each /portfolio/holdings row (price_status, price_as_of, price_source).
// `locale`/`timeZone` exist for deterministic tests; the app uses the browser's.
// `t` is the i18n translate function (English when omitted); the strings are
// marked with msg() so i18n/messages.test.js finds them.

const msg = (text) => text;
const english = (text, vars) => text.replace(/\{(\w+)\}/g, (m, key) => (vars && key in vars ? String(vars[key]) : m));

const STATUS_TEXT = {
  live: msg("real-time"),
  delayed: msg("delayed"),
  closed: msg("market closed"),
  stale: msg("price is out of date"),
  unknown: msg("quote time unavailable"),
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

export function priceFreshnessLine(summary, opts = {}) {
  if (!summary || !summary.holdings_count || !("prices_as_of" in summary)) return null;
  const t = opts.t ?? english;
  const source = summary.price_source || t("market data provider");
  const quoteTime = summary.prices_as_of ? formatQuoteTime(summary.prices_as_of, opts) : null;
  if (!quoteTime) return t("Prices from {source} · quote time unavailable", { source });
  if (summary.price_delay_minutes > 0) {
    return t("Prices from {source} · delayed up to {minutes} min · last quote {time}", {
      source,
      minutes: summary.price_delay_minutes,
      time: quoteTime,
    });
  }
  return t("Prices from {source} · last quote {time}", { source, time: quoteTime });
}

export function priceFreshnessTitle(holding, opts = {}) {
  if (!holding?.price_status) return null;
  const t = opts.t ?? english;
  const source = holding.price_source || t("market data provider");
  if (holding.price_status === "missing") {
    return t("{source} · no current price; this holding is valued at 0", { source });
  }
  const status = STATUS_TEXT[holding.price_status];
  const parts = [source, status ? t(status) : holding.price_status];
  const quoteTime = holding.price_as_of ? formatQuoteTime(holding.price_as_of, opts) : null;
  if (quoteTime) parts.push(t("last quote {time}", { time: quoteTime }));
  return [...new Set(parts)].join(" · ");
}

export const hasPriceProblem = (holding) =>
  holding?.price_status === "missing" || holding?.price_status === "stale";
