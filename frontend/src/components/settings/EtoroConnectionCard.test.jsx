import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import EtoroConnectionCard, { describeEtoroSync } from "./EtoroConnectionCard";

const mocks = vi.hoisted(() => ({
  fetchEtoroStatus: vi.fn(),
  connectEtoro: vi.fn(),
  disconnectEtoro: vi.fn(),
  syncEtoro: vi.fn(),
  setEtoroAutoSync: vi.fn(),
}));

vi.mock("../../api", () => mocks);
vi.mock("../../hooks/useBrokerPortfolio", () => ({ useBrokerPortfolio: () => ({ open: async () => null, discard: async () => {} }) }));

const CONNECTED = {
  connected: true,
  configured: true,
  auto_sync: false,
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
        <EtoroConnectionCard portfolioId="portfolio-1" portfolioName="Main" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

it("says when the server has no eToro integration configured", async () => {
  mocks.fetchEtoroStatus.mockResolvedValue({ connected: false, configured: false });
  mount();

  expect(await screen.findByText(/not available on this server yet/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/eToro API key/i)).not.toBeInTheDocument();
});

it("connects with a personal key and explains how to create one", async () => {
  mocks.fetchEtoroStatus.mockResolvedValue({ connected: false, configured: true });
  mocks.connectEtoro.mockResolvedValue({ connected: true });
  mount();

  const input = await screen.findByLabelText(/eToro API key/i);
  expect(screen.getByRole("button", { name: /^connect$/i })).toBeDisabled();
  expect(screen.getByText("Settings → Trading → API Key Management")).toBeInTheDocument();
  fireEvent.change(input, { target: { value: "  user-key  " } });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));

  await waitFor(() => expect(mocks.connectEtoro).toHaveBeenCalledWith("user-key"));
  expect(await screen.findByText(/Connected to eToro/i)).toBeInTheDocument();
});

it("shows a rejected key from the API", async () => {
  mocks.fetchEtoroStatus.mockResolvedValue({ connected: false, configured: true });
  mocks.connectEtoro.mockRejectedValue({ response: { data: { detail: "eToro rejected the key." } } });
  mount();

  fireEvent.change(await screen.findByLabelText(/eToro API key/i), { target: { value: "bad" } });
  fireEvent.click(screen.getByRole("button", { name: /^connect$/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent("eToro rejected the key.");
});

it("reports what a sync imported and skipped", async () => {
  mocks.fetchEtoroStatus.mockResolvedValue(CONNECTED);
  mocks.syncEtoro.mockResolvedValue({
    status: "imported", imported: 3, already_present: 1, errors: [],
    skipped_reasons: { "CFD / leveraged position": 2 },
  });
  mount();

  fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));
  const result = await screen.findByRole("status", { name: "eToro sync result" });
  expect(result).toHaveTextContent("3 new transactions, 1 already present.");
  expect(result).toHaveTextContent("CFD / leveraged position × 2");
});

it("shows review problems and the needs-attention flag", async () => {
  mocks.fetchEtoroStatus.mockResolvedValue({ ...CONNECTED, needs_attention: true, last_error: "eToro instrument 9 has no market ticker" });
  mount();

  expect(await screen.findByText("Connection needs attention")).toBeInTheDocument();
  expect(screen.getByText("eToro instrument 9 has no market ticker")).toBeInTheDocument();
});

it("toggles auto-sync and disconnects", async () => {
  mocks.fetchEtoroStatus.mockResolvedValue(CONNECTED);
  mocks.setEtoroAutoSync.mockResolvedValue({ ok: true, auto_sync: true });
  mocks.disconnectEtoro.mockResolvedValue({ ok: true });
  mount();

  fireEvent.click(await screen.findByRole("switch", { name: "eToro auto-sync" }));
  await waitFor(() => expect(mocks.setEtoroAutoSync).toHaveBeenCalled());
  expect(mocks.setEtoroAutoSync.mock.calls[0][0]).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: /disconnect/i }));
  await waitFor(() => expect(mocks.disconnectEtoro).toHaveBeenCalled());
});

it("describes a review result without claiming an import", () => {
  expect(describeEtoroSync({ status: "needs_review", errors: ["Position 5 is partially closed"] })).toEqual({
    tone: "error",
    title: "eToro positions need review — nothing was imported",
    detail: "Position 5 is partially closed",
  });
});
