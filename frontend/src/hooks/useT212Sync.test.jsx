import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";

import { historyPollInterval, useT212Sync } from "./useT212Sync";

const api = vi.hoisted(() => ({
  fetchT212Status: vi.fn(),
  fetchT212HistoryStatus: vi.fn(),
  fetchT212Positions: vi.fn(),
  syncT212: vi.fn(),
  connectT212: vi.fn(),
  disconnectT212: vi.fn(),
  setT212AutoSync: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../App", () => ({
  usePortfolio: () => ({ current: { id: "portfolio-1" } }),
}));

function mount(options) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { client, ...renderHook(() => useT212Sync(options), { wrapper }) };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchT212Status.mockResolvedValue({ connected: true });
  api.fetchT212HistoryStatus.mockResolvedValue({ connected: true, run: { state: "fetching", complete: false } });
  api.fetchT212Positions.mockResolvedValue({ connected: true, status: "fresh", positions: [] });
});

it("polls active history, slows down at a provider reset, and stops on a terminal state", () => {
  expect(historyPollInterval({ state: { data: { run: { state: "fetching" } } } })).toBe(5000);
  expect(historyPollInterval({ state: { data: { run: { state: "waiting_rate_limit" } } } })).toBe(30000);
  expect(historyPollInterval({ state: { data: { run: { state: "completed" } } } })).toBe(false);
});

it("refreshes snapshot state after sync without claiming staged history changed the ledger", async () => {
  api.syncT212.mockResolvedValue({ positions_updated: true, cash_updated: true, total_imported: 0, history_status: "pending" });
  const { client, result } = mount({ currency: "USD", includePositions: true });
  client.setQueryData(["transactions"], []);
  client.setQueryData(["sector-breakdown", "USD"], { sectors: [] });

  await waitFor(() => expect(result.current.positions.data?.status).toBe("fresh"));
  await act(async () => result.current.sync.mutateAsync());

  await waitFor(() => expect(api.fetchT212Positions).toHaveBeenCalledTimes(2));
  expect(client.getQueryState(["transactions"]).isInvalidated).toBe(false);
  expect(client.getQueryState(["sector-breakdown", "USD"]).isInvalidated).toBe(true);
  expect(result.current.history.data?.run?.state).toBe("fetching");
});

it("clears cached broker positions and history on disconnect", async () => {
  api.disconnectT212.mockResolvedValue({ ok: true });
  const { client, result } = mount({ currency: "USD", includePositions: true });
  await waitFor(() => expect(result.current.positions.data?.status).toBe("fresh"));

  await act(async () => result.current.disconnect.mutateAsync());

  expect(client.getQueryData(["t212-positions", "portfolio-1", "USD"])).toBeUndefined();
  expect(client.getQueryData(["t212-history-status", "portfolio-1"])).toBeUndefined();
});

it("does not retain Trading 212 credentials in the mutation cache", async () => {
  api.connectT212.mockResolvedValue({ ok: true });
  const { client, result } = mount();

  await act(async () => result.current.connect.mutate({ apiKey: "key-private", apiSecret: "secret-private" }));

  const mutationState = JSON.stringify(client.getMutationCache().getAll().map((mutation) => mutation.state));
  expect(mutationState).not.toContain("key-private");
  expect(mutationState).not.toContain("secret-private");
});
