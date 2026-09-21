import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import Settings from "./Settings";

const mocks = vi.hoisted(() => ({
  fetchT212Status: vi.fn(),
  fetchT212HistoryStatus: vi.fn(),
  syncT212: vi.fn(),
  discordMount: vi.fn(),
  dataMount: vi.fn(),
  recordPortfolioDataImported: vi.fn(() => true),
}));

vi.mock("../api", () => ({
  fetchT212Status: mocks.fetchT212Status,
  fetchT212HistoryStatus: mocks.fetchT212HistoryStatus,
  connectT212: vi.fn(),
  disconnectT212: vi.fn(),
  syncT212: mocks.syncT212,
  setT212AutoSync: vi.fn(),
}));

vi.mock("../analytics/useRegisteredActivation", () => ({
  useRegisteredActivation: () => ({
    recordPortfolioDataImported: mocks.recordPortfolioDataImported,
  }),
}));
vi.mock("../App", () => ({
  usePortfolio: () => ({ current: { id: "portfolio-1", name: "Imported portfolio" } }),
  useCurrency: () => ({ currency: "USD", setCurrency: vi.fn(), rate: 22, rateLoading: false }),
  usePalette: () => ({ palette: "blue", setPalette: vi.fn(), theme: "light", setTheme: vi.fn(), themeStyle: "glass", setThemeStyle: vi.fn() }),
}));
vi.mock("../components/SyncScheduleSettings", () => ({ default: () => <div>Sync schedule</div> }));
vi.mock("../components/DiscordSettings", () => ({ default: () => { mocks.discordMount(); return <div>Discord destination</div>; } }));
vi.mock("../components/DataPrivacySettings", () => ({ default: () => { mocks.dataMount(); return <div>Privacy controls</div>; } }));

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}{location.search}</output>;
}

function mount(path) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Settings dataManagement={<div>Portfolio management</div>} />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.fetchT212Status.mockResolvedValue({ connected: false });
  mocks.fetchT212HistoryStatus.mockResolvedValue({ connected: false, run: null });
});

it.each([
  ["connections", "Connections"],
  ["preferences", "Preferences"],
  ["notifications", "Notifications"],
  ["data", "Data & Privacy"],
])("restores the %s section from its direct URL", async (section, heading) => {
  mount(`/settings?section=${section}`);
  expect(await screen.findByRole("heading", { level: 2, name: heading })).toBeInTheDocument();
});

it("replaces an invalid section with Connections and preserves unrelated parameters", async () => {
  mount("/settings?source=alert&section=unknown");
  expect(await screen.findByRole("heading", { level: 2, name: "Connections" })).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("location")).toHaveTextContent("/settings?source=alert&section=connections"));
});

it("mounts only the selected section and trusts the broker status for connection state", async () => {
  mount("/settings?section=connections");
  expect(await screen.findByText("Not connected")).toBeInTheDocument();
  expect(screen.getAllByText("Imported portfolio").length).toBeGreaterThan(0);
  expect(mocks.fetchT212Status).toHaveBeenCalledTimes(1);
  expect(mocks.discordMount).not.toHaveBeenCalled();
  expect(mocks.dataMount).not.toHaveBeenCalled();
});

it("opens Preferences without firing section network queries", async () => {
  mount("/settings?section=preferences");
  expect(await screen.findByRole("heading", { level: 2, name: "Preferences" })).toBeInTheDocument();
  expect(mocks.fetchT212Status).not.toHaveBeenCalled();
  expect(mocks.discordMount).not.toHaveBeenCalled();
  expect(mocks.dataMount).not.toHaveBeenCalled();
});

it("navigates with real links, preserves parameters, and focuses the new heading", async () => {
  mount("/settings?section=connections&source=alert");
  fireEvent.click(screen.getByRole("link", { name: "Notifications" }));
  const heading = await screen.findByRole("heading", { level: 2, name: "Notifications" });
  await waitFor(() => expect(heading).toHaveFocus());
  expect(screen.getByLabelText("location")).toHaveTextContent("/settings?section=notifications&source=alert");
  expect(mocks.discordMount).toHaveBeenCalled();
});

describe("Trading 212 sync activation measurement", () => {
  beforeEach(() => {
    mocks.fetchT212Status.mockResolvedValue({ connected: true, auto_sync: false, api_key_preview: "••••1234" });
  });

  it("emits a broker import when a sync actually imports transactions", async () => {
    mocks.syncT212.mockResolvedValueOnce({ total_imported: 5, imported_orders: 3, imported_dividends: 2 });
    mount("/settings?section=connections");

    fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));

    await waitFor(() => expect(mocks.recordPortfolioDataImported).toHaveBeenCalledWith("broker"));
    expect(mocks.recordPortfolioDataImported).toHaveBeenCalledTimes(1);
  });

  it("does not emit a broker import when a sync finds nothing new", async () => {
    mocks.syncT212.mockResolvedValueOnce({ total_imported: 0, imported_orders: 0, imported_dividends: 0 });
    mount("/settings?section=connections");

    fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));

    await waitFor(() => expect(screen.getByText(/Synced 0 transactions/i)).toBeInTheDocument());
    expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
  });

  it("does not emit a broker import when a sync fails", async () => {
    mocks.syncT212.mockRejectedValueOnce({ response: { data: { detail: "Sync failed" } } });
    mount("/settings?section=connections");

    fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Sync failed");
    expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
  });
});

describe("Trading 212 history backfill progress", () => {
  beforeEach(() => {
    mocks.fetchT212Status.mockResolvedValue({ connected: true, auto_sync: false, api_key_preview: "••••1234" });
  });

  it("shows nothing when no run has ever been created", async () => {
    mocks.fetchT212HistoryStatus.mockResolvedValue({ connected: true, run: null });
    mount("/settings?section=connections");

    await screen.findByText("Connected");
    expect(screen.queryByText(/Importing history/i)).not.toBeInTheDocument();
  });

  it("shows in-progress state and the loaded counts", async () => {
    mocks.fetchT212HistoryStatus.mockResolvedValue({
      connected: true,
      run: {
        id: "run-1", mode: "incremental", state: "fetching", complete: false,
        orders_loaded: 12, orders_complete: false, dividends_loaded: 4, dividends_complete: false,
        started_at: "2026-09-21T10:00:00Z", last_progress_at: "2026-09-21T10:05:00Z",
        completed_at: null, last_error: null,
      },
    });
    mount("/settings?section=connections");

    expect(await screen.findByText("Importing history…")).toBeInTheDocument();
    expect(screen.getByText(/12 orders and 4 dividends loaded so far/i)).toBeInTheDocument();
    expect(screen.getByText(/this page can be closed/i)).toBeInTheDocument();
  });

  it("shows the completed state without the background-continuing hint", async () => {
    mocks.fetchT212HistoryStatus.mockResolvedValue({
      connected: true,
      run: {
        id: "run-1", mode: "incremental", state: "completed", complete: true,
        orders_loaded: 40, orders_complete: true, dividends_loaded: 10, dividends_complete: true,
        started_at: "2026-09-21T10:00:00Z", last_progress_at: "2026-09-21T10:05:00Z",
        completed_at: "2026-09-21T10:06:00Z", last_error: null,
      },
    });
    mount("/settings?section=connections");

    expect(await screen.findByText("History imported")).toBeInTheDocument();
    expect(screen.queryByText(/this page can be closed/i)).not.toBeInTheDocument();
  });

  it("surfaces a persisted error even while still retrying", async () => {
    mocks.fetchT212HistoryStatus.mockResolvedValue({
      connected: true,
      run: {
        id: "run-1", mode: "incremental", state: "fetching", complete: false,
        orders_loaded: 5, orders_complete: false, dividends_loaded: 0, dividends_complete: false,
        started_at: "2026-09-21T10:00:00Z", last_progress_at: "2026-09-21T10:01:00Z",
        completed_at: null, last_error: "temporary upstream error",
      },
    });
    mount("/settings?section=connections");

    expect(await screen.findByText("temporary upstream error")).toBeInTheDocument();
  });
});
