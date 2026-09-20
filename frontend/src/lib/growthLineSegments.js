export function splitGrowthLineSegments(points, zeroY) {
  const segments = [];
  let previous = null;

  for (const point of points) {
    if (!Number.isFinite(point?.x) || !Number.isFinite(point?.y) || !Number.isFinite(point?.value)) {
      previous = null;
      continue;
    }

    if (previous) {
      if (previous.value === 0 || point.value === 0 || (previous.value > 0) === (point.value > 0)) {
        segments.push({
          x1: previous.x,
          y1: previous.y,
          x2: point.x,
          y2: point.y,
          isGain: (previous.value || point.value) >= 0,
        });
      } else {
        // Split at the exact zero crossing so neither color leaks to the other side.
        const ratio = Math.abs(previous.value) / (Math.abs(previous.value) + Math.abs(point.value));
        const crossingX = previous.x + (point.x - previous.x) * ratio;

        segments.push({ x1: previous.x, y1: previous.y, x2: crossingX, y2: zeroY, isGain: previous.value > 0 });
        segments.push({ x1: crossingX, y1: zeroY, x2: point.x, y2: point.y, isGain: point.value > 0 });
      }
    }

    previous = point;
  }

  return segments;
}
