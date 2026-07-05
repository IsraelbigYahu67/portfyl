const DASH = "—";

export function formatMoney(n, currency = "USD") {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const str = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency === "CZK" ? `${sign}${str} Kč` : `${sign}$${str}`;
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
  return currency === "CZK" ? `${sign}${str} Kč` : `${sign}$${str}`;
}

export function formatNumber(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return DASH;
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
