const DASH = "—";

const LOCALE_BY_CURRENCY = { CZK: "cs-CZ", USD: "en-US" };
const SUPPORTED_CURRENCY_CODES = new Set(["CZK", "EUR", "GBP", "USD"]);

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

export function formatMoney(value, currency = "USD") {
  if (value == null || !Number.isFinite(Number(value))) return DASH;
  const n = Number(value);
  const code = currency === "GBp" || currency === "GBX"
    ? currency
    : String(currency || "USD").toUpperCase();

  if (n !== 0 && Math.abs(n) < 0.01) {
    if (code === "CZK") return n > 0 ? "<0,01 Kč" : ">-0,01 Kč";
    const { prefix = "", suffix = "" } = currencyParts(code);
    return n > 0 ? `<${prefix}0.01${suffix}` : `>-${prefix}0.01${suffix}`;
  }

  if (code === "GBp" || code === "GBX") {
    return `${n.toLocaleString("en-GB", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} p`;
  }

  if (!SUPPORTED_CURRENCY_CODES.has(code)) {
    return `$${n.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  try {
    return new Intl.NumberFormat(LOCALE_BY_CURRENCY[code] || "en-US", {
      style: "currency",
      currency: code,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
  }
}

export function formatQuantity(value) {
  if (value == null || !Number.isFinite(Number(value))) return DASH;
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 8,
    useGrouping: true,
  }).format(Number(value));
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

export function formatLongDate(iso) {
  return formatShortDate(iso, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function formatDateTime(iso) {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return DASH;
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
  }).format(date);
}

export function formatNumberSpaced(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const [intPart, fracPart] = Math.abs(n).toFixed(digits).split(".");
  const spacedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
  return fracPart != null ? `${sign}${spacedInt},${fracPart}` : `${sign}${spacedInt}`;
}

export function formatMoneySpaced(n, currency = "USD") {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const { prefix = "", suffix = "" } = currencyParts(currency);
  return `${sign}${prefix}${formatNumberSpaced(Math.abs(n), 2)}${suffix}`;
}
