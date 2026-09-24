import { fireEvent, render, screen } from "@testing-library/react";

import BrokerPositionSnapshot from "./BrokerPositionSnapshot";

const snapshot = (positions, status = "fresh") => ({
  data: { connected: true, status, as_of: "2026-09-21T10:05:00Z", currency: "USD", positions },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
});

it("shows current broker quantities without fabricating a total when currency is unknown", () => {
  render(<BrokerPositionSnapshot query={snapshot([
    { ticker: "AAPL", quantity: 10, market_value: null, currency: null },
    { ticker: "MSFT", quantity: 2, market_value: 50, currency: "USD" },
  ])} />);

  expect(screen.getByText("2 positions")).toBeInTheDocument();
  expect(screen.getByText("AAPL")).toBeInTheDocument();
  expect(screen.getByText("10 shares")).toBeInTheDocument();
  expect(screen.getByText(/total value unavailable/i)).toBeInTheDocument();
  expect(screen.getByText("$50.00")).toBeInTheDocument();
});

it("labels a stale snapshot and displays a complete converted total", () => {
  render(<BrokerPositionSnapshot query={snapshot([
    { ticker: "AAPL", quantity: 1, market_value: 100, currency: "USD" },
    { ticker: "MSFT", quantity: 2, market_value: 50, currency: "USD" },
  ], "stale")} />);

  expect(screen.getByText("$150.00")).toBeInTheDocument();
  expect(screen.getByText("Snapshot stale")).toBeInTheDocument();
});

it("distinguishes an empty successful snapshot from an unavailable snapshot", () => {
  const { rerender } = render(<BrokerPositionSnapshot query={snapshot([])} />);
  expect(screen.getByText(/No open positions in the latest snapshot/i)).toBeInTheDocument();

  rerender(<BrokerPositionSnapshot query={snapshot([], "unavailable")} />);
  expect(screen.getByText(/No position snapshot yet/i)).toBeInTheDocument();
});

it("offers retry when the snapshot request fails", () => {
  const refetch = vi.fn();
  render(<BrokerPositionSnapshot query={{ isLoading: false, isError: true, refetch }} />);
  fireEvent.click(screen.getByRole("button", { name: "Retry positions" }));
  expect(refetch).toHaveBeenCalledOnce();
});
