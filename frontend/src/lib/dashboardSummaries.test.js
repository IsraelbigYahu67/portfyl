import { summarizePassiveIncome, splitDividendForecast, buildCompositionRows, snapshotNetWorth } from "./dashboardSummaries";

describe("summarizePassiveIncome", () => {
  const holdings = [
    // 10 shares at 400 USD native, worth 92 000 CZK -> 23 CZK per USD
    { ticker: "MSFT", shares: 10, current_price: 400, market_value: 92000 },
    // UK listing quoted in pence: 100 shares at 500 GBp, worth 14 500 CZK
    { ticker: "ULVR.L", shares: 100, current_price: 500, market_value: 14500 },
    { ticker: "NVDA", shares: 5, current_price: 130, market_value: 15000 },
  ];

  it("converts each estimated annual income into the display currency via the holding's own price ratio", () => {
    const result = summarizePassiveIncome({
      holdings,
      dividends: [
        { ticker: "MSFT", annual_income: 33.2, income_status: "estimated", ex_date: "2026-11-19" },
        { ticker: "ULVR.L", annual_income: 15000, income_status: "estimated", ex_date: "2026-10-30" },
      ],
      totalValue: 121500,
      today: "2026-10-11",
    });

    // 33.2 USD * 23 = 763.6 ; 15000 GBp * (14500 / 50000) = 4350
    expect(result.annualIncome).toBeCloseTo(763.6 + 4350, 6);
    expect(result.yieldPct).toBeCloseTo(((763.6 + 4350) / 121500) * 100, 6);
    expect(result.payers).toBe(2);
  });

  it("skips rows flagged for review or without an estimate", () => {
    const result = summarizePassiveIncome({
      holdings,
      dividends: [
        { ticker: "MSFT", annual_income: 33.2, income_status: "review" },
        { ticker: "NVDA", annual_income: null, income_status: "unavailable" },
      ],
      totalValue: 121500,
      today: "2026-10-11",
    });
    expect(result.annualIncome).toBe(0);
    expect(result.payers).toBe(0);
    expect(result.yieldPct).toBe(0);
  });

  it("picks the earliest upcoming ex-dividend date and ignores past ones", () => {
    const result = summarizePassiveIncome({
      holdings,
      dividends: [
        { ticker: "MSFT", annual_income: 33.2, income_status: "estimated", ex_date: "2026-11-19" },
        { ticker: "ULVR.L", annual_income: 15000, income_status: "estimated", ex_date: "2026-10-30" },
        { ticker: "NVDA", annual_income: 0.2, income_status: "estimated", ex_date: "2026-09-01" },
      ],
      totalValue: 121500,
      today: "2026-10-11",
    });
    expect(result.next).toEqual({ ticker: "ULVR.L", date: "2026-10-30" });
  });

  it("returns a null yield when the portfolio value is unknown", () => {
    const result = summarizePassiveIncome({ holdings, dividends: [], totalValue: null, today: "2026-10-11" });
    expect(result.yieldPct).toBeNull();
    expect(result.next).toBeNull();
  });
});

describe("splitDividendForecast", () => {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].map((month, i) => ({
    month,
    paid: i < 9 ? 10 * (i + 1) : 0,
    estimated: i >= 9 ? 100 : 0,
    entries: [],
  }));
  const forecast = { year: 2026, currency: "USD", months, total_paid: 450, total_estimated: 300 };

  it("splits the calendar year at the current month and converts USD to the display rate", () => {
    const { received, upcoming } = splitDividendForecast(forecast, { monthIndex: 9, usdRate: 23 });

    expect(received.months.map((m) => m.month)).toEqual(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]);
    expect(received.total).toBeCloseTo(450 * 23, 6);
    expect(upcoming.months.map((m) => m.month)).toEqual(["Oct", "Nov", "Dec"]);
    expect(upcoming.total).toBeCloseTo(300 * 23, 6);
    expect(upcoming.monthlyAverage).toBeCloseTo(100 * 23, 6);
    expect(upcoming.dailyAverage).toBeCloseTo((100 * 23 * 12) / 365, 6);
    // Older responses carry no all-time total.
    expect(received.allTime).toBeNull();
  });

  it("converts the all-time paid total to the display rate", () => {
    const { received } = splitDividendForecast({ ...forecast, total_paid_all_time: 900 }, { monthIndex: 9, usdRate: 23 });
    expect(received.allTime).toBeCloseTo(900 * 23, 6);
  });

  it("keeps USD amounts untouched when no rate is given", () => {
    const { upcoming } = splitDividendForecast(forecast, { monthIndex: 9, usdRate: 1 });
    expect(upcoming.months[0].amount).toBe(100);
  });

  it("uses the rolling 12-month outlook for upcoming and keeps the confirmed / forecasted split per company", () => {
    const outlook = {
      months: [
        {
          month: "Oct", year: 2026, confirmed: 10, forecasted: 5,
          entries: [
            { ticker: "AAA", name: "Aaa Corp", amount: 10, status: "confirmed" },
            { ticker: "BBB", name: "Bbb Corp", amount: 5, status: "forecasted" },
          ],
        },
        { month: "Jan", year: 2027, confirmed: 0, forecasted: 20, entries: [{ ticker: "AAA", name: "Aaa Corp", amount: 20, status: "forecasted" }] },
      ],
    };
    const { received, upcoming } = splitDividendForecast({ ...forecast, outlook }, { monthIndex: 9, usdRate: 2 });

    expect(upcoming.months.map((m) => `${m.month} ${m.year}`)).toEqual(["Oct 2026", "Jan 2027"]);
    expect(upcoming.months[0]).toMatchObject({ confirmed: 20, forecasted: 10, amount: 30 });
    expect(upcoming.months[0].entries).toEqual([
      { ticker: "AAA", name: "Aaa Corp", amount: 20, status: "confirmed" },
      { ticker: "BBB", name: "Bbb Corp", amount: 10, status: "forecasted" },
    ]);
    expect(upcoming.total).toBe(30 + 40);
    // Received still comes from the calendar year, not the outlook.
    expect(received.months).toHaveLength(10);
  });

  it("lists only paid entries under received", () => {
    const withEntries = {
      ...forecast,
      months: forecast.months.map((m, i) => (i === 0
        ? { ...m, entries: [{ ticker: "AAA", name: "Aaa Corp", amount: 10, status: "paid" }, { ticker: "BBB", name: "Bbb Corp", amount: 3, status: "estimated" }] }
        : m)),
    };
    const { received } = splitDividendForecast(withEntries, { monthIndex: 9, usdRate: 1 });
    expect(received.months[0].entries).toEqual([{ ticker: "AAA", name: "Aaa Corp", amount: 10, status: "paid" }]);
  });

  it("returns empty halves for a missing forecast", () => {
    const { received, upcoming } = splitDividendForecast(null, { monthIndex: 3, usdRate: 1 });
    expect(received).toEqual({ months: [], total: 0, monthlyAverage: 0 });
    expect(upcoming).toEqual({ months: [], total: 0, monthlyAverage: 0 });
  });
});

describe("buildCompositionRows", () => {
  const breakdown = [
    { name: "Stocks", value: 1168560, weight: 47.0 },
    { name: "ETFs", value: 994520, weight: 40.0 },
    { name: "Cash", value: 185190, weight: 7.4 },
  ];

  it("attaches target and drift from allocation-target groups with the same name", () => {
    const rows = buildCompositionRows(breakdown, [
      { group: "stocks", target_pct: 45, current_pct: 47.2, drift_pct: 2.2 },
      { group: "ETFs", target_pct: 45, current_pct: 39.8, drift_pct: -5.2 },
    ]);

    expect(rows).toEqual([
      { name: "Stocks", value: 1168560, weight: 47.0, targetPct: 45, driftPct: 2 },
      { name: "ETFs", value: 994520, weight: 40.0, targetPct: 45, driftPct: -5 },
      { name: "Cash", value: 185190, weight: 7.4, targetPct: null, driftPct: null },
    ]);
  });

  it("works without any targets", () => {
    expect(buildCompositionRows(breakdown, undefined).every((r) => r.targetPct === null)).toBe(true);
  });
});

describe("snapshotNetWorth", () => {
  const positions = {
    status: "fresh",
    as_of: "2026-10-11T14:00:00Z",
    currency: "CZK",
    positions: [{ market_value: 50000 }, { market_value: 18609 }],
  };
  const fetching = { state: "fetching" };

  it("sums the broker snapshot while T212 history is still loading", () => {
    expect(snapshotNetWorth({ positions, historyRun: fetching, currency: "CZK" })).toEqual({
      positionsValue: 68609,
      asOf: "2026-10-11T14:00:00Z",
    });
  });

  it("is null once history has completed, so the ledger value is used", () => {
    expect(snapshotNetWorth({ positions, historyRun: { state: "completed" }, currency: "CZK" })).toBeNull();
  });

  it("is null without a history run (e.g. a CSV-only portfolio)", () => {
    expect(snapshotNetWorth({ positions, historyRun: null, currency: "CZK" })).toBeNull();
  });

  it("is null when any position has no market value or the currency differs", () => {
    const partial = { ...positions, positions: [{ market_value: 50000 }, { market_value: null }] };
    expect(snapshotNetWorth({ positions: partial, historyRun: fetching, currency: "CZK" })).toBeNull();
    expect(snapshotNetWorth({ positions, historyRun: fetching, currency: "USD" })).toBeNull();
  });

  it("is null without snapshot positions", () => {
    const empty = { ...positions, positions: [] };
    expect(snapshotNetWorth({ positions: empty, historyRun: fetching, currency: "CZK" })).toBeNull();
    expect(snapshotNetWorth({ positions: undefined, historyRun: fetching, currency: "CZK" })).toBeNull();
  });
});
