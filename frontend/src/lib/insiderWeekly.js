// Weekly bucketing + insider-transaction-to-week snapping for the stock
// detail page's insider dot chart. Kept as pure functions so the bucket/
// snap math is unit-testable without rendering Recharts.

const DAY_MS = 24 * 60 * 60 * 1000;
const WEEK_MS = 7 * DAY_MS;

// Buckets a daily {date, close} price series (as returned by
// fetchHistory().data) into `weeks` trailing 7-day windows ending at the
// last date present in the series. Each bucket's close is the last daily
// close inside its window; weeks with no data get close: null so the line
// can gap rather than snapping to a stale value.
export function buildWeeklyBuckets(dailySeries, weeks = 52) {
  const points = (dailySeries || [])
    .map((p) => ({ ts: new Date(p.date).getTime(), close: p.close }))
    .filter((p) => Number.isFinite(p.ts) && p.close != null)
    .sort((a, b) => a.ts - b.ts);

  if (!points.length) return [];

  const endTs = points[points.length - 1].ts;
  const startTs = endTs - (weeks - 1) * WEEK_MS;

  const buckets = Array.from({ length: weeks }, (_, i) => {
    const weekTs = startTs + i * WEEK_MS;
    return { weekKey: new Date(weekTs).toISOString().slice(0, 10), weekTs, close: null };
  });

  for (const p of points) {
    if (p.ts < startTs) continue;
    const idx = Math.min(weeks - 1, Math.floor((p.ts - startTs) / WEEK_MS));
    buckets[idx].close = p.close;
  }

  return buckets;
}

// Snaps each buy/sell insider transaction to the weekly bucket containing
// its date, producing one dot descriptor per transaction. Transactions with
// side "other", an unparseable date, a date outside the bucket range, or
// whose bucket has no price (close: null) are dropped — they stay visible
// in the separate transactions list, just not plotted on this chart.
export function assignTransactionsToWeeks(transactions, buckets) {
  if (!buckets?.length) return [];
  const startTs = buckets[0].weekTs;
  const weeks = buckets.length;
  const dots = [];

  for (const t of transactions || []) {
    if (t.side !== "buy" && t.side !== "sell") continue;
    const ts = new Date(t.date).getTime();
    if (!Number.isFinite(ts) || ts < startTs) continue;
    const idx = Math.floor((ts - startTs) / WEEK_MS);
    if (idx < 0 || idx >= weeks) continue;
    const bucket = buckets[idx];
    if (bucket.close == null) continue;
    dots.push({
      key: `${bucket.weekKey}-${t.side}-${dots.length}`,
      side: t.side,
      weekKey: bucket.weekKey,
      weekTs: bucket.weekTs,
      close: bucket.close,
      insider: t.insider ?? null,
      date: t.date,
      shares: t.shares != null ? Math.abs(t.shares) : null,
      value: t.value != null ? Math.abs(t.value) : null,
    });
  }

  return dots;
}

// Pixel offset for spreading dots that land in the same week+side group so
// they don't fully overlap: 0, +6, -6, +12, -12, ... Applied to the
// rendered dot's cy, never to the underlying data value.
export function jitterOffsetPx(index) {
  if (!index) return 0;
  const magnitude = Math.ceil(index / 2) * 6;
  return index % 2 === 1 ? magnitude : -magnitude;
}
