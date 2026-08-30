const DASH = "—";

// Prefix/suffix per currency. Note GBp/GBX (London pence) is distinct from GBP
// (pounds) and must be checked on the raw code before upper-casing collapses them.
export function currencyParts(currency) {
  if (currency === "GBp" || currency === "GBX") return { suffix: " p" };
  switch ((currency || "USD").toUpperCase()) {
    case "CZK": return { suffix: " Kč" };
    case "EUR": return { prefix: "€" };
    case "GBP": return { prefix: "£" };
    case "GBX": return { suffix: " p" };
    default: return { prefix: "$" }; // USD and anything unmapped
  }
}

export function formatMoney(n, currency = "USD") {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const str = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const { prefix = "", suffix = "" } = currencyParts(currency);
  return `${sign}${prefix}${str}${suffix}`;
}

export function formatPercent(n, { sign = true, digits = 2 } = {}) {
  if (n == null || Number.isNaN(n)) return DASH;
  const prefix = n >= 0 ? (sign ? "+" : "") : "-";
  return `${prefix}${Math.abs(n).toFixed(digits)}%`;
}

export function formatCompact(n, currency = "USD") {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const str = Math.abs(n).toLocaleString("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  });
  const { prefix = "", suffix = "" } = currencyParts(currency);
  return `${sign}${prefix}${str}${suffix}`;
}

export function formatNumber(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return DASH;
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

// Date-only ISO strings ("2024-01-01") must not go through `new Date(iso)`:
// the spec parses them as UTC midnight, so they render as the *previous* day
// in any timezone west of UTC. Build the Date from local components instead.
export function formatShortDate(iso, options = { month: "short", day: "numeric" }) {
  if (!iso) return DASH;
  const [y, m, d] = String(iso).split("-").map(Number);
  if (!y || !m || !d) return DASH;
  return new Date(y, m - 1, d).toLocaleDateString("en-US", options);
}

export function formatNumberSpaced(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const [intPart, fracPart] = Math.abs(n).toFixed(digits).split(".");
  const spacedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return fracPart != null ? `${sign}${spacedInt},${fracPart}` : `${sign}${spacedInt}`;
}

export function formatMoneySpaced(n, currency = "USD") {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const { prefix = "", suffix = "" } = currencyParts(currency);
  return `${sign}${prefix}${formatNumberSpaced(Math.abs(n), 2)}${suffix}`;
}
