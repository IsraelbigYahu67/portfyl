import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";

import { useT212Sync } from "./useT212Sync";
import { fetchT212HistoryStatus, fetchT212Positions, fetchT212Status, retryT212History, syncT212 } from "../api";

vi.mock("../api", () => ({
  fetchT212Status: vi.fn(),
  fetchT212HistoryStatus: vi.fn(),
  fetchT212Positions: vi.fn(),
  syncT212: vi.fn(),
  retryT212History: vi.fn(),
}));

function wrapperFor(client) {
  return function Wrapper({ children }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useT212Sync", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.clearAllMocks();
    fetchT212Status.mockResolvedValue({ connected: true });
    fetchT212Positions.mockResolvedValue({ connected: true, status: "fresh", currency: "USD", positions: [] });
    syncT212.mockResolvedValue({
      snapshot: { status: "ready", cash_updated: true, positions_updated: true, positions: 0 },
      history: { run_id: "run-1", status: "fetching", complete: false },
    });
    fetchT212HistoryStatus.mockResolvedValue({
      connected: true,
      run: {
        id: "run-1",
        mode: "incremental",
        state: "waiting_rate_limit",
        complete: false,
        orders_loaded: 10,
        orders_complete: false,
        dividends_loaded: 2,
        dividends_complete: false,
        started_at: "2026-09-21T10:00:00Z",
        last_progress_at: "2026-09-21T10:01:00Z",
        completed_at: null,
        last_error: null,
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("polls a rate-limited run more slowly than an actively fetching run", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => useT212Sync({ portfolioId: "portfolio-1", currency: "USD" }),
      { wrapper: wrapperFor(client) },
    );

    await waitFor(() => expect(fetchT212HistoryStatus).toHaveBeenCalledTimes(1));
    expect(result.current.phase).toBe("waiting_rate_limit");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchT212HistoryStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchT212HistoryStatus).toHaveBeenCalledTimes(2);
  });

  it("refreshes the current position snapshot after a manual sync", async () => {
    fetchT212HistoryStatus.mockResolvedValue({ connected: true, run: null });
    fetchT212Positions
      .mockResolvedValueOnce({ connected: true, status: "fresh", currency: "USD", positions: [{ ticker: "AAPL", market_value: 100 }] })
      .mockResolvedValueOnce({ connected: true, status: "fresh", currency: "USD", positions: [{ ticker: "AAPL", market_value: 125 }] });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => useT212Sync({ portfolioId: "portfolio-1", currency: "USD" }),
      { wrapper: wrapperFor(client) },
    );

    await waitFor(() => expect(result.current.positionsQuery.data?.positions[0]?.market_value).toBe(100));

    await act(async () => {
      await result.current.syncAsync?.();
    });

    await waitFor(() => expect(result.current.positionsQuery.data?.positions[0]?.market_value).toBe(125));
  });

  it("refreshes snapshot consumers without pretending history was finalized", async () => {
    fetchT212HistoryStatus.mockResolvedValue({ connected: true, run: null });
    const cashQuery = vi.fn()
      .mockResolvedValueOnce({ broker_amount: 100 })
      .mockResolvedValueOnce({ broker_amount: 125 });
    const transactionsQuery = vi.fn()
      .mockResolvedValueOnce([{ id: "old" }])
      .mockResolvedValueOnce([{ id: "new" }]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => {
      const t212 = useT212Sync({ portfolioId: "portfolio-1", currency: "USD" });
      const cash = useQuery({ queryKey: ["cash-reconciliation", "USD"], queryFn: cashQuery, staleTime: Infinity });
      const transactions = useQuery({ queryKey: ["transactions"], queryFn: transactionsQuery, staleTime: Infinity });
      return { t212, cash, transactions };
    }, { wrapper: wrapperFor(client) });

    await waitFor(() => expect(result.current.cash.data?.broker_amount).toBe(100));
    await waitFor(() => expect(result.current.transactions.data?.[0]?.id).toBe("old"));

    await act(async () => {
      await result.current.t212.syncAsync();
    });

    await waitFor(() => expect(result.current.cash.data?.broker_amount).toBe(125));
    expect(result.current.transactions.data?.[0]?.id).toBe("old");
    expect(transactionsQuery).toHaveBeenCalledTimes(1);
  });

  it("refreshes ledger consumers exactly once when finalization completes", async () => {
    fetchT212HistoryStatus
      .mockResolvedValueOnce({
        connected: true,
        run: {
          id: "run-2", mode: "incremental", state: "fetching", complete: false,
          orders_loaded: 10, orders_complete: false, dividends_loaded: 2, dividends_complete: false,
          started_at: "2026-09-21T10:00:00Z", last_progress_at: "2026-09-21T10:01:00Z",
          completed_at: null, last_error: null,
        },
      })
      .mockResolvedValueOnce({
        connected: true,
        run: {
          id: "run-2", mode: "incremental", state: "completed", complete: true,
          orders_loaded: 40, orders_complete: true, dividends_loaded: 10, dividends_complete: true,
          started_at: "2026-09-21T10:00:00Z", last_progress_at: "2026-09-21T10:05:00Z",
          completed_at: "2026-09-21T10:06:00Z", last_error: null,
        },
      });
    const transactionsQuery = vi.fn()
      .mockResolvedValueOnce([{ id: "before-backfill" }])
      .mockResolvedValueOnce([{ id: "after-finalization" }]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => {
      const t212 = useT212Sync({ portfolioId: "portfolio-1", currency: "USD" });
      const transactions = useQuery({ queryKey: ["transactions"], queryFn: transactionsQuery, staleTime: Infinity });
      return { t212, transactions };
    }, { wrapper: wrapperFor(client) });

    await waitFor(() => expect(result.current.t212.historyRun?.state).toBe("fetching"));
    await waitFor(() => expect(result.current.transactions.data?.[0]?.id).toBe("before-backfill"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    await waitFor(() => expect(result.current.t212.historyRun?.state).toBe("completed"));
    await waitFor(() => expect(result.current.transactions.data?.[0]?.id).toBe("after-finalization"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(transactionsQuery).toHaveBeenCalledTimes(2);
  });
  it("retryHistory posts the retry and refetches the history status", async () => {
    retryT212History.mockResolvedValue({ run_id: "run-2", status: "pending", complete: false, blocked: false });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(
      () => useT212Sync({ portfolioId: "portfolio-1", currency: "USD" }),
      { wrapper: wrapperFor(client) },
    );

    await waitFor(() => expect(fetchT212HistoryStatus).toHaveBeenCalledTimes(1));
    expect(result.current.retryPending).toBe(false);

    await act(async () => {
      result.current.retryHistory();
    });

    expect(retryT212History).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(fetchT212HistoryStatus.mock.calls.length).toBeGreaterThan(1));
    await waitFor(() => expect(result.current.retryPending).toBe(false));
  });
});
