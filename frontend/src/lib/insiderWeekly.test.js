import { buildWeeklyBuckets, assignTransactionsToWeeks, jitterOffsetPx } from "./insiderWeekly";

const DAY = 24 * 60 * 60 * 1000;
const WEEK = 7 * DAY;

describe("buildWeeklyBuckets", () => {
  it("returns an empty array for empty/missing input", () => {
    expect(buildWeeklyBuckets([])).toEqual([]);
    expect(buildWeeklyBuckets(null)).toEqual([]);
  });

  it("buckets daily closes into 7-day windows, keeping the last close per window", () => {
    const series = [
      { date: "2026-01-01", close: 100 },
      { date: "2026-01-03", close: 105 },
      { date: "2026-01-08", close: 110 },
    ];
    const buckets = buildWeeklyBuckets(series, 2);
    expect(buckets).toHaveLength(2);
    expect(buckets[0]).toEqual({ weekKey: "2026-01-01", weekTs: Date.UTC(2026, 0, 1), close: 105 });
    expect(buckets[1]).toEqual({ weekKey: "2026-01-08", weekTs: Date.UTC(2026, 0, 8), close: 110 });
  });

  it("leaves close: null for weeks with no daily data", () => {
    const series = [
      { date: "2026-01-01", close: 100 },
      { date: "2026-01-15", close: 120 },
    ];
    const buckets = buildWeeklyBuckets(series, 3);
    expect(buckets.map((b) => b.close)).toEqual([100, null, 120]);
  });

  it("spaces bucket timestamps exactly one week apart", () => {
    const series = [{ date: "2026-01-01", close: 100 }];
    const buckets = buildWeeklyBuckets(series, 4);
    expect(buckets.map((b) => b.weekTs)).toEqual([
      Date.UTC(2026, 0, 1) - 3 * WEEK,
      Date.UTC(2026, 0, 1) - 2 * WEEK,
      Date.UTC(2026, 0, 1) - 1 * WEEK,
      Date.UTC(2026, 0, 1),
    ]);
  });

  it("defaults to 52 weeks when not specified", () => {
    const buckets = buildWeeklyBuckets([{ date: "2026-01-01", close: 100 }]);
    expect(buckets).toHaveLength(52);
  });
});

describe("assignTransactionsToWeeks", () => {
  const series = [
    { date: "2026-01-01", close: 100 },
    { date: "2026-01-15", close: 120 },
  ];
  const buckets = buildWeeklyBuckets(series, 3); // weeks: Jan01 (100), Jan08 (null), Jan15 (120)

  it("returns an empty array when there are no buckets", () => {
    expect(assignTransactionsToWeeks([{ date: "2026-01-01", side: "buy" }], [])).toEqual([]);
  });

  it("snaps a transaction to the week bucket containing its date", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Alice", date: "2026-01-02", side: "buy", shares: -100, value: 5000 }],
      buckets,
    );
    expect(out).toEqual([
      {
        key: expect.any(String),
        side: "buy",
        weekKey: "2026-01-01",
        weekTs: Date.UTC(2026, 0, 1),
        close: 100,
        insider: "Alice",
        date: "2026-01-02",
        shares: 100,
        value: 5000,
      },
    ]);
  });

  it("drops transactions landing in an empty (null close) bucket", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Bob", date: "2026-01-10", side: "sell", shares: 50, value: 2500 }],
      buckets,
    );
    expect(out).toEqual([]);
  });

  it("drops transactions before the bucket range", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Carol", date: "2025-12-01", side: "buy", shares: 10, value: 100 }],
      buckets,
    );
    expect(out).toEqual([]);
  });

  it("drops transactions after the bucket range", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Frank", date: "2026-02-01", side: "buy", shares: 10, value: 100 }],
      buckets,
    );
    expect(out).toEqual([]);
  });

  it("drops transactions with an unparseable date", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Grace", date: "not-a-date", side: "buy", shares: 10, value: 100 }],
      buckets,
    );
    expect(out).toEqual([]);
  });

  it("returns an empty array for missing transactions", () => {
    expect(assignTransactionsToWeeks(null, buckets)).toEqual([]);
  });

  it("drops non buy/sell sides", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Dave", date: "2026-01-16", side: "other", shares: 5, value: 50 }],
      buckets,
    );
    expect(out).toEqual([]);
  });

  it("keeps one entry per transaction with unique keys when several share a week+side", () => {
    const out = assignTransactionsToWeeks(
      [
        { insider: "Alice", date: "2026-01-02", side: "buy", shares: 100, value: 5000 },
        { insider: "Eve", date: "2026-01-05", side: "buy", shares: 200, value: 9000 },
      ],
      buckets,
    );
    expect(out).toHaveLength(2);
    expect(out[0].key).not.toEqual(out[1].key);
    expect(out.every((d) => d.weekKey === "2026-01-01")).toBe(true);
  });
});

describe("jitterOffsetPx", () => {
  it("alternates outward from the true point", () => {
    expect([0, 1, 2, 3, 4].map(jitterOffsetPx)).toEqual([0, 6, -6, 12, -12]);
  });
});
