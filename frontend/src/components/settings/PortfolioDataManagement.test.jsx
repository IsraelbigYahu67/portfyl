import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import PortfolioDataManagement, { PORTFOLIO_DATA_QUERY_KEYS } from "./PortfolioDataManagement";

const mocks = vi.hoisted(() => ({
  clearAllTransactions: vi.fn(),
  confirm: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock("../../api", () => ({ clearAllTransactions: mocks.clearAllTransactions }));
vi.mock("../../App", () => ({ usePortfolio: () => ({ current: { id: "portfolio-1", name: "Long-term" } }) }));
vi.mock("../ui/ConfirmDialog", () => ({ useConfirm: () => mocks.confirm }));
vi.mock("../ui/Toast", () => ({ useToast: () => ({ success: mocks.success, error: mocks.error }) }));

function mount() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  vi.spyOn(client, "invalidateQueries");
  render(<QueryClientProvider client={client}><PortfolioDataManagement /></QueryClientProvider>);
  return client;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.confirm.mockResolvedValue(true);
  mocks.clearAllTransactions.mockResolvedValue({ deleted: 4 });
});

it("names the active portfolio and leaves it untouched when confirmation is cancelled", async () => {
  mocks.confirm.mockResolvedValueOnce(false);
  mount();
  expect(screen.getByText("Long-term")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Clear portfolio" }));
  await waitFor(() => expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({ danger: true, confirmLabel: "Clear portfolio" })));
  expect(mocks.clearAllTransactions).not.toHaveBeenCalled();
});

it("clears once and invalidates every portfolio-derived and recovery key", async () => {
  const client = mount();
  fireEvent.click(screen.getByRole("button", { name: "Clear portfolio" }));

  await waitFor(() => expect(mocks.clearAllTransactions).toHaveBeenCalledTimes(1));
  expect(await screen.findByRole("status")).toHaveTextContent("Long-term was cleared");
  for (const key of PORTFOLIO_DATA_QUERY_KEYS) {
    expect(client.invalidateQueries).toHaveBeenCalledWith({ queryKey: [key] });
  }
});

it("keeps a clear failure visible and actionable", async () => {
  mocks.clearAllTransactions.mockRejectedValueOnce({ response: { data: { detail: "Portfolio is locked" } } });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Clear portfolio" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Portfolio is locked");
  expect(screen.getByRole("button", { name: "Clear portfolio" })).toBeEnabled();
});
