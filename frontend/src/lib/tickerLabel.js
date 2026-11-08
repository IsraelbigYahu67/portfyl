// Short ticker labels for tight spaces (phone legends).
//
// Yahoo-style tickers carry the exchange as a dot suffix (VWCE.DE, CEZ.PR,
// NOVO-B.CO). On a phone the suffix only eats room, so it is dropped — but only
// for *known exchange* suffixes: BRK.B / BF.B are share classes, not exchanges,
// and must stay whole. If the shortened label would be ambiguous (the same
// ticker listed on several exchanges, or next to a plain one), the full ticker
// is kept for every colliding entry.

const EXCHANGE_SUFFIXES = new Set([
  // Europe
  "L", "IL", "DE", "F", "BE", "DU", "HM", "HA", "MU", "SG", "PA", "MI", "AS", "BR", "LS", "MC",
  "SW", "VI", "HE", "ST", "CO", "OL", "IC", "IR", "WA", "PR", "BU", "AT", "IS", "RG", "TL", "VS",
  // Americas
  "TO", "V", "NE", "CN", "MX", "SA", "BA", "SN",
  // Asia-Pacific, Middle East, Africa
  "HK", "SS", "SZ", "T", "KS", "KQ", "TW", "TWO", "SI", "AX", "NZ", "NS", "BO", "JK", "KL", "BK",
  "TA", "JO",
]);

// { base, suffix } when `name` ends in a known exchange suffix, else null.
export function splitTicker(name) {
  const text = String(name ?? "");
  const dot = text.lastIndexOf(".");
  if (dot <= 0 || dot === text.length - 1) return null;
  const suffix = text.slice(dot + 1).toUpperCase();
  return EXCHANGE_SUFFIXES.has(suffix) ? { base: text.slice(0, dot), suffix } : null;
}

// Map of every name -> the label to show for it.
export function shortTickerLabels(names) {
  const list = (names || []).map((n) => String(n));
  const bases = list.map((n) => splitTicker(n)?.base ?? n);
  const counts = new Map();
  bases.forEach((b) => counts.set(b.toUpperCase(), (counts.get(b.toUpperCase()) || 0) + 1));
  return new Map(
    list.map((n, i) => [n, splitTicker(n) && counts.get(bases[i].toUpperCase()) === 1 ? bases[i] : n])
  );
}
