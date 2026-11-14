const DASH = "—";

const LOCALE_BY_CURRENCY = { CZK: "cs-CZ", PLN: "pl-PL", USD: "en-US" };
const SUPPORTED_CURRENCY_CODES = new Set(["CZK", "EUR", "GBP", "PLN", "USD"]);
// Locales that write a decimal comma.
const COMMA_LOCALES = new Set(["cs-CZ", "pl-PL"]);

// Prefix/suffix per currency. Note GBp/GBX (London pence) is distinct from GBP
// (pounds) and must be checked on the raw code before upper-casing collapses them.
export function currencyParts(currency) {
  if (currency === "GBp" || currency === "GBX") return { suffix: " p" };
  switch ((currency || "USD").toUpperCase()) {
    case "CZK": return { suffix: " Kč" };
    case "PLN": return { suffix: " zł" };
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
    const { prefix = "", suffix = "" } = currencyParts(code);
    const cent = COMMA_LOCALES.has(LOCALE_BY_CURRENCY[code]) ? "0,01" : "0.01";
    return n > 0 ? `<${prefix}${cent}${suffix}` : `>-${prefix}${cent}${suffix}`;
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

// Number separators follow the display currency: CZK reads cs-CZ, PLN pl-PL,
// the rest en-US.
export function displayLocale(currency) {
  return LOCALE_BY_CURRENCY[String(currency || "USD").toUpperCase()] || "en-US";
}

export function formatQuantity(value, currency = "USD") {
  if (value == null || !Number.isFinite(Number(value))) return DASH;
  return new Intl.NumberFormat(displayLocale(currency), {
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
  let str = Math.abs(n).toLocaleString("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  });
  // Keep the K/M/B suffixes but use the decimal comma for CZK and PLN.
  if (COMMA_LOCALES.has(displayLocale(currency))) str = str.replace(".", ",");
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

// Table cells: "Oct 15" within the current year, "Oct 15, 2025" otherwise.
export function formatTableDate(iso, now = new Date()) {
  if (!iso) return DASH;
  const [y, m, d] = String(iso).split("-").map(Number);
  if (!y || !m || !d) return DASH;
  const options = { month: "short", day: "numeric" };
  if (y !== now.getFullYear()) options.year = "numeric";
  return new Date(y, m - 1, d).toLocaleDateString("en-US", options);
}

// "INTEREST_ON_FREE_CASH" -> "Interest on free cash"
export function humanizeCode(code) {
  if (code == null || String(code).trim() === "") return DASH;
  const text = String(code).trim().replace(/_+/g, " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function pluralize(n, one, many) {
  return n === 1 ? one : many;
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
