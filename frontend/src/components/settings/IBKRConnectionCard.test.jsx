import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import IBKRConnectionCard, { describeLedger } from "./IBKRConnectionCard";
import { legacyColorClassesIn } from "../../test/legacyClasses";

const mocks = vi.hoisted(() => ({
  fetchIBKRStatus: vi.fn(),
  connectIBKR: vi.fn(),
  disconnectIBKR: vi.fn(),
  syncIBKR: vi.fn(),
  setIBKRAutoSync: vi.fn(),
}));

vi.mock("../../api", () => mocks);
vi.mock("../../hooks/useBrokerPortfolio", () => ({ useBrokerPortfolio: () => ({ open: async () => null, discard: async () => {} }) }));

const CONNECTED = {
  connected: true,
  auto_sync: false,
  token_preview: "1234...abcd",
  last_synced_at: null,
  connected_at: "2026-10-01T10:00:00",
  needs_attention: false,
  last_error: null,
};

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <IBKRConnectionCard portfolioId="portfolio-1" portfolioName="Main" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function syncWith(ledger) {
  mocks.fetchIBKRStatus.mockResolvedValue(CONNECTED);
  mocks.syncIBKR.mockResolvedValue({ imported: 1, updated: 2, errors: [], balance_found: true, ledger });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));
  return screen.findByRole("status", { name: "IBKR sync result" });
}

beforeEach(() => {
  vi.clearAllMocks();
});

it("explains what the sync imports and lists the Flex Query setup", async () => {
  mocks.fetchIBKRStatus.mockResolvedValue({ connected: false });
  mount();

  expect(await screen.findByText("Not connected")).toBeInTheDocument();
  expect(screen.getByText(/imports stocks, ETFs, dividends and cash/i)).toBeInTheDocument();
  const guide = screen.getByText("How to set up the IBKR Flex Query").closest("details");
  for (const section of ["Trades", "Cash Transactions", "Corporate Actions", "Transfers", "Open Positions", "Account Information"]) {
    expect(within(guide).getByText(section)).toBeInTheDocument();
  }
  expect(guide).toHaveTextContent("Trades — Execution level");
  expect(guide).toHaveTextContent("Cash Transactions — Detail level");
  expect(within(guide).getByText("XML")).toBeInTheDocument();
  expect(within(guide).getByText("yyyyMMdd")).toBeInTheDocument();
  expect(within(guide).getByText("HHmmss")).toBeInTheDocument();
  expect(within(guide).getByText(";")).toBeInTheDocument();
  expect(guide).toHaveTextContent(/once per year/i);
  expect(within(guide).getByRole("link", { name: "Import page" })).toHaveAttribute("href", "/import");
});

it("connects with the Flex token and query ID", async () => {
  mocks.fetchIBKRStatus.mockResolvedValueOnce({ connected: false }).mockResolvedValue(CONNECTED);
  mocks.connectIBKR.mockResolvedValue({ connected: true });
  mount();

  const connect = await screen.findByRole("button", { name: /^connect$/i });
  expect(connect).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Flex Web Service token"), { target: { value: " tok-123 " } });
  fireEvent.change(screen.getByLabelText("Flex Query ID"), { target: { value: "987654" } });
  fireEvent.click(connect);

  await waitFor(() => expect(mocks.connectIBKR).toHaveBeenCalledWith("tok-123", "987654"));
  expect(await screen.findByText("1234...abcd")).toBeInTheDocument();
});

it("reports newly imported and already present ledger rows", async () => {
  const result = await syncWith({ status: "imported", imported: 12, already_present: 3, errors: [] });
  expect(result).toHaveTextContent("Stocks, ETFs, dividends and cash imported");
  expect(result).toHaveTextContent("12 new transactions, 3 already present.");
  expect(result).toHaveTextContent("Options: 1 new trade, 2 updated.");
});

it("shows the first review error when the statement needs review", async () => {
  const result = await syncWith({ status: "needs_review", imported: 0, already_present: 0, errors: ["AAPL dividend tax without gross", "second"] });
  expect(result).toHaveTextContent("need review");
  expect(result).toHaveTextContent("AAPL dividend tax without gross");
  expect(result).not.toHaveTextContent("second");
});

it("tells the user a deferred import will be retried", async () => {
  const result = await syncWith({ status: "deferred", imported: 0, already_present: 0, errors: ["OpenFIGI down"] });
  expect(result).toHaveTextContent("Instrument lookup unavailable");
  expect(result).toHaveTextContent(/retried automatically on the next sync/i);
});

it("points at the setup guide when Flex sections are missing", async () => {
  const result = await syncWith({ status: "sections_missing", imported: 0, already_present: 0, errors: [] });
  expect(result).toHaveTextContent(/no Trades or Cash Transactions section/i);
});

it("shows the review message the connection status carries", async () => {
  mocks.fetchIBKRStatus.mockResolvedValue({ ...CONNECTED, needs_attention: true, last_error: "Unknown currency in cash row" });
  mount();
  expect(await screen.findByText("Connection needs attention")).toBeInTheDocument();
  expect(screen.getByText("Unknown currency in cash row")).toBeInTheDocument();
});

it("surfaces a failed sync", async () => {
  mocks.fetchIBKRStatus.mockResolvedValue(CONNECTED);
  mocks.syncIBKR.mockRejectedValue({ response: { data: { detail: "Failed to send Flex request: timeout" } } });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Failed to send Flex request: timeout");
});

it("toggles auto-sync", async () => {
  mocks.fetchIBKRStatus.mockResolvedValue(CONNECTED);
  mocks.setIBKRAutoSync.mockResolvedValue({ ok: true, auto_sync: true });
  mount();
  fireEvent.click(await screen.findByRole("switch", { name: "IBKR auto-sync" }));
  await waitFor(() => expect(mocks.setIBKRAutoSync).toHaveBeenCalled());
  expect(mocks.setIBKRAutoSync.mock.calls[0][0]).toBe(true);
});

it("ignores a missing or unknown ledger", () => {
  expect(describeLedger(undefined)).toBeNull();
  expect(describeLedger({ status: "something_new" })).toBeNull();
});

it("shows the connection state as a badge with pill buttons", async () => {
  mocks.fetchIBKRStatus.mockResolvedValue(CONNECTED);
  mount();

  expect(await screen.findByText("Connected")).toHaveAttribute("data-tone", "gain");
  expect(screen.getByRole("button", { name: /sync now/i })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: /disconnect/i })).toHaveClass("btn-ghost", "text-loss");
});

it("styles the credential fields with the shared input class", async () => {
  mocks.fetchIBKRStatus.mockResolvedValue({ connected: false });
  mount();

  expect(await screen.findByLabelText("Flex Web Service token")).toHaveClass("input");
  expect(screen.getByLabelText("Flex Query ID")).toHaveClass("input");
  expect(screen.getByText("Not connected")).toHaveAttribute("data-tone", "neutral");
});

it("uses no legacy color classes", async () => {
  expect(await legacyColorClassesIn(new URL("./IBKRConnectionCard.jsx", import.meta.url))).toEqual([]);
});
