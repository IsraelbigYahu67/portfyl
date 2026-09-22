import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import T212SnapshotPositions from "./T212SnapshotPositions";

const api = vi.hoisted(() => ({
  fetchT212Status: vi.fn(),
  fetchT212HistoryStatus: vi.fn(),
  fetchT212Positions: vi.fn(),
  connectT212: vi.fn(),
  disconnectT212: vi.fn(),
  syncT212: vi.fn(),
  setT212AutoSync: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../App", () => ({
  usePortfolio: () => ({ current: { id: "portfolio-1" } }),
}));

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><T212SnapshotPositions currency="USD" /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchT212Status.mockResolvedValue({ connected: true });
  api.fetchT212HistoryStatus.mockResolvedValue({ connected: true, run: { state: "fetching", complete: false } });
});

it("shows current broker positions separately while history is still being fetched", async () => {
  api.fetchT212Positions.mockResolvedValue({
    connected: true, status: "fresh", as_of: "2026-09-21T12:00:00Z", currency: "USD",
    positions: [
      { ticker: "AAPL", quantity: 2.5, currency: "USD", market_value: 500 },
      { ticker: "VUSA", quantity: 3, currency: null, market_value: 300 },
      { ticker: "MSFT", quantity: 1, currency: "USD", market_value: null },
    ],
  });
  mount();

  expect(await screen.findByRole("heading", { name: "Trading 212 positions" })).toBeInTheDocument();
  expect(await screen.findByText("AAPL")).toBeInTheDocument();
  expect(screen.getByText("VUSA")).toBeInTheDocument();
  expect(screen.getByText("$500.00")).toBeInTheDocument();
  expect(screen.getByText("Currency unknown")).toBeInTheDocument();
  expect(screen.getByText("Price unavailable")).toBeInTheDocument();
  expect(screen.getByText(/history is still being fetched/i)).toBeInTheDocument();
  expect(screen.queryByText("$300.00")).not.toBeInTheDocument();
});

it("marks an old snapshot as stale", async () => {
  api.fetchT212Positions.mockResolvedValue({
    connected: true, status: "stale", as_of: "2026-09-19T12:00:00Z", currency: "USD",
    positions: [{ ticker: "AAPL", quantity: 1, currency: "USD", market_value: 200 }],
  });
  mount();

  expect(await screen.findByText(/snapshot is out of date/i)).toBeInTheDocument();
});

it("shows a retry when connection status cannot be loaded", async () => {
  api.fetchT212Status.mockRejectedValue(new Error("network error"));
  mount();

  expect(await screen.findByText(/Could not check the Trading 212 connection/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});
