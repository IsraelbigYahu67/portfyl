// Y axis for the stock financials bar charts: round steps (1, 2, 2.5 or 5 ×
// 10ⁿ), zero always on the axis, and labels that each pick their own unit
// ("500M", "1B", "1.5B") so a 1B axis does not read as 0.5B / 1B.

const UNITS = [
  [1e12, "T"],
  [1e9, "B"],
  [1e6, "M"],
  [1e3, "K"],
];

function niceStep(raw) {
  if (!(raw > 0)) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  for (const multiple of [1, 2, 2.5, 5, 10]) {
    if (magnitude * multiple >= raw - 1e-9 * magnitude) return magnitude * multiple;
  }
  return magnitude * 10;
}

// Strip floating noise (0.1 + 0.2) without losing real precision.
const clean = (n) => Number(n.toPrecision(12));

export function buildFinancialAxis(values, { maxTicks = 5 } = {}) {
  const finite = (values || []).filter((v) => Number.isFinite(v));
  const lo = Math.min(0, ...finite);
  const hi = Math.max(0, ...finite);
  if (lo === hi) return { domain: [0, 1], ticks: [0, 1] };

  let step = niceStep((hi - lo) / (maxTicks - 1));
  let first;
  let last;
  for (;;) {
    first = Math.floor(lo / step + 1e-9);
    last = Math.ceil(hi / step - 1e-9);
    if (last - first + 1 <= maxTicks + 1) break;
    step = niceStep(step * 1.01);
  }
  const ticks = [];
  for (let i = first; i <= last; i += 1) ticks.push(clean(i * step));
  return { domain: [ticks[0], ticks[ticks.length - 1]], ticks };
}

function trimNumber(n) {
  return String(clean(Number(n.toFixed(2))));
}

export function formatFinancialTick(value, { perShare = false } = {}) {
  if (!Number.isFinite(value)) return "";
  if (value === 0) return "0";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (perShare) return `${sign}${trimNumber(abs)}`;
  for (const [size, suffix] of UNITS) {
    if (abs >= size) return `${sign}${trimNumber(abs / size)}${suffix}`;
  }
  return `${sign}${trimNumber(abs)}`;
}

// Width for the widest label at 12px (~7.5px per character) plus breathing
// room, so "-500M" or "200K" never get clipped at the card edge.
export function financialAxisWidth(labels) {
  const longest = Math.max(0, ...(labels || []).map((label) => String(label).length));
  return Math.min(72, Math.max(52, Math.ceil(longest * 7.5) + 12));
}
