// Editor model for per-portfolio target weights. Mirrors the rules in
// backend/allocation_targets.py so problems show before saving; the server
// re-validates everything. Targets stay text while editing and are sent as
// strings, so no float rounding happens on the way to the Decimal column.

export const TARGET_SUM_TOLERANCE = 0.01;
const MAX_GROUP_LENGTH = 40;
const PCT_RE = /^\d{1,3}(\.\d{1,2})?$/;

export function parseTarget(text) {
  const value = String(text ?? "").trim().replace(",", ".");
  if (value === "") return null;
  if (!PCT_RE.test(value)) return NaN;
  const n = Number(value);
  return n > 100 ? NaN : n;
}

const toCents = (n) => Math.round(n * 100);

export function draftFromDrift(drift) {
  return (drift?.rows || []).map((r) => ({
    key: r.ticker,
    ticker: r.ticker,
    name: r.name ?? null,
    group: r.group ?? "",
    target: r.target_pct == null ? "" : String(r.target_pct),
    currentPct: r.current_pct ?? 0,
    isNew: false,
  }));
}

export function newDraftRow(index) {
  return { key: `new-${index}`, ticker: "", name: null, group: "", target: "", currentPct: 0, isNew: true };
}

export function draftTotal(rows) {
  const cents = rows.reduce((sum, r) => {
    const v = parseTarget(r.target);
    return Number.isFinite(v) ? sum + toCents(v) : sum;
  }, 0);
  return cents / 100;
}

export function draftErrors(rows) {
  const errors = [];
  const seen = new Set();
  for (const r of rows) {
    if (String(r.target).trim() === "") continue;
    const ticker = r.ticker.trim().toUpperCase();
    if (!ticker) {
      errors.push("Every target needs a ticker.");
      continue;
    }
    if (seen.has(ticker)) errors.push(`${ticker} has more than one target.`);
    seen.add(ticker);
    if (Number.isNaN(parseTarget(r.target))) {
      errors.push(`The target for ${ticker} must be a number from 0 to 100 with at most two decimals.`);
    }
    if (r.group.trim().length > MAX_GROUP_LENGTH) {
      errors.push(`The group for ${ticker} can be at most ${MAX_GROUP_LENGTH} characters.`);
    }
  }
  const total = draftTotal(rows);
  if (total > 100 + TARGET_SUM_TOLERANCE) {
    errors.push(`Targets add up to ${total.toFixed(2)}%, more than 100%.`);
  }
  return [...new Set(errors)];
}

export function toPayload(rows) {
  return rows
    .filter((r) => String(r.target).trim() !== "" && r.ticker.trim() !== "")
    .map((r) => ({
      ticker: r.ticker.trim().toUpperCase(),
      target_pct: String(r.target).trim().replace(",", "."),
      group: r.group.trim() || null,
    }));
}

// Pre-fill targets with today's weights so the user edits from the status quo.
// Rounded weights rarely sum to exactly 100.00, so the residual goes to the
// largest row; rows not currently held are cleared.
export function fillFromCurrentWeights(rows) {
  const held = rows.filter((r) => r.currentPct > 0);
  if (!held.length) return rows;
  const residual = 10000 - held.reduce((sum, r) => sum + toCents(r.currentPct), 0);
  const largest = held.reduce((a, b) => (b.currentPct > a.currentPct ? b : a));
  return rows.map((r) => {
    if (r.currentPct <= 0) return { ...r, target: "" };
    const cents = toCents(r.currentPct) + (r === largest ? residual : 0);
    return { ...r, target: (cents / 100).toFixed(2) };
  });
}
