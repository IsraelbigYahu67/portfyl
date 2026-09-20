function nicePercentStep(requiredStep) {
  const magnitude = 10 ** Math.floor(Math.log10(requiredStep));
  const normalized = requiredStep / magnitude;

  if (normalized <= 1) return magnitude;
  if (normalized <= 2) return magnitude * 2;
  if (normalized <= 5) return magnitude * 5;
  return magnitude * 10;
}

export function buildPercentAxis(values) {
  const validValues = (values || []).filter(Number.isFinite);
  if (!validValues.length || validValues.every((value) => value === 0)) {
    return { domain: [-1, 1], ticks: [-1, 0, 1] };
  }

  const min = Math.min(0, ...validValues);
  const max = Math.max(0, ...validValues);
  const step = nicePercentStep(Math.max(1, (max - min) / 4));
  const lower = Math.floor(min / step) * step;
  const upper = Math.ceil(max / step) * step;
  const ticks = Array.from({ length: (upper - lower) / step + 1 }, (_, index) => lower + index * step);

  return { domain: [lower, upper], ticks };
}
