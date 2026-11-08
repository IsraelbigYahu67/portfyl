// A percentage whose decimal points line up when stacked in a right-aligned
// column. Each value is padded with real trailing zeros up to `decimals`, so
// "40", "12.3" and "5.25" read "40.00%", "12.30%" and "5.25%" and nothing sits
// between the last digit and the "%". tabular-nums keeps every digit and the
// dot the same width in all rows.

const text = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  const s = String(n);
  return /e/i.test(s) ? n.toFixed(2) : s;
};

export function decimalsOf(value) {
  const frac = text(value).split(".")[1];
  return frac ? frac.length : 0;
}

export function maxDecimalsOf(values) {
  return Math.max(0, ...(values || []).map(decimalsOf));
}

export default function AlignedPercent({ value, decimals = 0 }) {
  const n = Number(value);
  const shown = Number.isFinite(n) ? n.toFixed(Math.max(decimals, decimalsOf(value))) : String(value);
  return <span className="tabular-nums">{shown}%</span>;
}
