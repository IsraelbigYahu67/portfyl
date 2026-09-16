import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ConfirmProvider } from "../ui/ConfirmDialog";
import { ToastProvider } from "../ui/Toast";
import { WatchlistEmptyState } from "./WatchlistEmptyState";

const api = vi.hoisted(() => ({
  searchTickers: vi.fn(),
  createWatchlist: vi.fn(),
  addWatchlistItem: vi.fn(),
}));
vi.mock("../../api", () => api);

function renderState() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><ToastProvider><ConfirmProvider><WatchlistEmptyState /></ConfirmProvider></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.searchTickers.mockResolvedValue({ results: [{ symbol: "AAPL", name: "Apple" }] });
  api.createWatchlist.mockResolvedValue({ id: "wl-1", name: "My watchlist", items: [], count: 0 });
  api.addWatchlistItem.mockResolvedValue({ id: "item-1" });
});

it("autofocuses ticker search and quick-starts My watchlist", async () => {
  renderState();
  const input = screen.getByRole("combobox", { name: /ticker to track/i });
  expect(input).toHaveFocus();
  fireEvent.change(input, { target: { value: "AAP" } });
  fireEvent.click(await screen.findByRole("option", { name: /AAPL Apple/i }));
  await waitFor(() => expect(api.createWatchlist).toHaveBeenCalledWith({ name: "My watchlist" }));
  expect(api.addWatchlistItem).toHaveBeenCalledWith("wl-1", "AAPL");
});

it("keeps the created list and reports an actionable partial failure", async () => {
  api.addWatchlistItem.mockRejectedValue(new Error("provider unavailable"));
  renderState();
  const input = screen.getByRole("combobox", { name: /ticker to track/i });
  fireEvent.change(input, { target: { value: "AAPL" } });
  fireEvent.click(await screen.findByRole("option", { name: /AAPL Apple/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/watchlist was created/i);
});
