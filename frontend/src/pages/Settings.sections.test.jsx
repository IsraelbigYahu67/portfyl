import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import Settings, { HistoryBackfillStatus } from "./Settings";
import { HAS_PUBLIC_HOME } from "../lib/routes";
import { legacyColorClassesIn } from "../test/legacyClasses";

const mocks = vi.hoisted(() => ({
  fetchT212Status: vi.fn(),
  fetchT212HistoryStatus: vi.fn(),
  fetchT212Positions: vi.fn(),
  syncT212: vi.fn(),
  retryT212History: vi.fn(),
  discordMount: vi.fn(),
  dataMount: vi.fn(),
}));

vi.mock("../api", () => ({
  fetchT212Status: mocks.fetchT212Status,
  fetchT212HistoryStatus: mocks.fetchT212HistoryStatus,
  fetchT212Positions: mocks.fetchT212Positions,
  connectT212: vi.fn(),
  disconnectT212: vi.fn(),
  syncT212: mocks.syncT212,
  retryT212History: mocks.retryT212History,
  setT212AutoSync: vi.fn(),
}));

vi.mock("../App", () => ({
  usePortfolio: () => ({ current: { id: "portfolio-1", name: "Imported portfolio" } }),
  useCurrency: () => ({ currency: "USD", setCurrency: vi.fn(), rate: 22, rateLoading: false }),
  usePalette: () => ({ palette: "blue", setPalette: vi.fn(), theme: "light", setTheme: vi.fn(), themeStyle: "glass", setThemeStyle: vi.fn() }),
}));
vi.mock("../components/SyncScheduleSettings", () => ({ default: () => <div>Sync schedule</div> }));
vi.mock("../components/DiscordSettings", () => ({ default: () => { mocks.discordMount(); return <div>Discord destination</div>; } }));
vi.mock("../components/DataPrivacySettings", () => ({ default: () => { mocks.dataMount(); return <div>Privacy controls</div>; } }));
vi.mock("../components/settings/IBKRConnectionCard", () => ({ default: ({ portfolioName }) => <div>IBKR card for {portfolioName}</div> }));
vi.mock("../components/settings/EtoroConnectionCard", () => ({ default: ({ portfolioName }) => <div>eToro card for {portfolioName}</div> }));

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
  mocks.fetchT212Positions.mockResolvedValue({ connected: false, status: "unavailable", as_of: null, currency: "USD", positions: [] });
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

it("links the public legal pages from Data & Privacy only in cloud", async () => {
  mount("/settings?section=data");
  await screen.findByRole("heading", { level: 2, name: "Data & Privacy" });
  const terms = screen.queryByRole("link", { name: "Terms of Service" });
  if (HAS_PUBLIC_HOME) {
    expect(terms).toHaveAttribute("href", "/terms?lang=en");
    expect(screen.getByRole("link", { name: "Zásady ochrany osobních údajů" })).toHaveAttribute("href", "/privacy?lang=cs");
  } else {
    expect(terms).not.toBeInTheDocument();
  }
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
  expect(screen.getByText("IBKR card for Imported portfolio")).toBeInTheDocument();
  expect(screen.getByText("eToro card for Imported portfolio")).toBeInTheDocument();
  expect(mocks.discordMount).not.toHaveBeenCalled();
  expect(mocks.dataMount).not.toHaveBeenCalled();
});

it("shows Trading 212 connection state as a badge", async () => {
  mount("/settings?section=connections");
  expect(await screen.findByText("Not connected")).toHaveAttribute("data-tone", "neutral");
  expect(screen.getByLabelText("API Key")).toHaveClass("input");
  expect(screen.getByRole("button", { name: /^connect$/i })).toHaveClass("btn-primary");
});

it("uses no legacy color classes", async () => {
  expect(await legacyColorClassesIn(new URL("./Settings.jsx", import.meta.url))).toEqual([]);
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

describe("Trading 212 snapshot-first manual sync", () => {
  beforeEach(() => {
    mocks.fetchT212Status.mockResolvedValue({ connected: true, auto_sync: false, api_key_preview: "••••1234" });
  });

  it("reports the snapshot and background history run without claiming transactions were imported", async () => {
    mocks.syncT212.mockResolvedValueOnce({
      snapshot: { status: "ready", cash_updated: true, positions_updated: true, positions: 3 },
      history: { run_id: "run-1", status: "pending", complete: false },
    });
    mount("/settings?section=connections");

    fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));

    expect(await screen.findByText(/Snapshot refreshed\. History continues in the background\./i)).toBeInTheDocument();
  });

  it("shows a safe error when the snapshot request fails", async () => {
    mocks.syncT212.mockRejectedValueOnce({ response: { data: { detail: "Sync failed" } } });
    mount("/settings?section=connections");

    fireEvent.click(await screen.findByRole("button", { name: /sync now/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Sync failed");
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
        cash_loaded: 1, cash_complete: false,
        started_at: "2026-09-21T10:00:00Z", last_progress_at: "2026-09-21T10:05:00Z",
        completed_at: null, last_error: null,
      },
    });
    mount("/settings?section=connections");

    expect(await screen.findByText("Downloading history…")).toBeInTheDocument();
    expect(screen.getByText(/12 orders, 4 dividends and 1 cash transaction loaded so far/i)).toBeInTheDocument();
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
    expect(screen.getByText(/historical analytics are up to date/i)).toBeInTheDocument();
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

  it("keeps finalization visible as active background work", async () => {
    mocks.fetchT212HistoryStatus.mockResolvedValue({
      connected: true,
      run: {
        id: "run-1", mode: "incremental", state: "finalizing", complete: false, download_complete: true,
        orders_loaded: 40, orders_complete: true, dividends_loaded: 10, dividends_complete: true,
        started_at: "2026-09-21T10:00:00Z", last_progress_at: "2026-09-21T10:05:00Z",
        completed_at: null, last_error: null,
      },
    });
    mount("/settings?section=connections");

    expect(await screen.findByText("Finalizing history…")).toBeInTheDocument();
    expect(screen.getByText(/this page can be closed/i)).toBeInTheDocument();
  });

  it("explains a needs-review run without implying a retry or an imported history", async () => {
    mocks.fetchT212HistoryStatus.mockResolvedValue({
      connected: true,
      run: {
        id: "run-1", mode: "incremental", state: "needs_review", complete: false, download_complete: true,
        orders_loaded: 40, orders_complete: true, dividends_loaded: 10, dividends_complete: true,
        started_at: "2026-09-21T10:00:00Z", last_progress_at: "2026-09-21T10:05:00Z",
        completed_at: null,
        last_error: "Trading 212 history contains corporate actions (such as splits) that Portfyl cannot import automatically yet. No history was imported.",
      },
    });
    mount("/settings?section=connections");

    expect(await screen.findByText("Needs review")).toBeInTheDocument();
    expect(screen.getByText(/corporate actions.*cannot import automatically yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/this page can be closed/i)).not.toBeInTheDocument();
    expect(screen.queryByText("History imported")).not.toBeInTheDocument();
  });
});

describe("Trading 212 needs-review panel", () => {
  const baseRun = {
    state: "needs_review", orders_loaded: 40, dividends_loaded: 10,
    last_error: "Trading 212 history contains corporate actions (such as splits) that Portfyl cannot import automatically yet. No history was imported.",
  };
  const review = (overrides = {}) => ({
    items: [{ fill_type: "STOCK_SPLIT", ticker: "NVDA", date: "2024-06-10" }],
    csv_needed_through: "2024-06-10", csv_covers_all: false, mapper_supports_all: false, ...overrides,
  });

  it("lists the blocking items, links to the CSV import and offers a retry", () => {
    const onRetry = vi.fn();
    render(
      <MemoryRouter>
        <HistoryBackfillStatus run={{ ...baseRun, review: review() }} onRetry={onRetry} retryPending={false} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Stock split · NVDA · 2024-06-10/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Trading 212 CSV export/i })).toHaveAttribute("href", "/import");
    expect(screen.getByText(/covers at least through 2024-06-10/i)).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: /Retry history import/i });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("falls back to the raw type and an unknown date for unlabelled items", () => {
    render(
      <MemoryRouter>
        <HistoryBackfillStatus
          run={{ ...baseRun, review: review({ items: [{ fill_type: "MERGER", ticker: null, date: null }], csv_needed_through: null }) }}
          onRetry={() => {}} retryPending={false}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/MERGER · unknown · unknown date/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Trading 212 CSV export/i })).not.toBeInTheDocument();
  });

  it("describes a cash transaction that could not be mapped", () => {
    render(
      <MemoryRouter>
        <HistoryBackfillStatus
          run={{
            ...baseRun,
            last_error: "Trading 212 reported a cash transaction that Portfyl cannot import automatically yet. No history was imported.",
            review: review({
              items: [{ fill_type: null, ticker: null, date: "2026-03-01", cash_type: "MYSTERY" }],
              csv_needed_through: "2026-03-01",
            }),
          }}
          onRetry={() => {}} retryPending={false}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Cash transaction \(MYSTERY\) · 2026-03-01/)).toBeInTheDocument();
    expect(screen.getByText(/cash transaction that Portfyl cannot import/i)).toBeInTheDocument();
  });

  it("tells the user a retry can succeed once the CSV already covers the actions", () => {
    render(
      <MemoryRouter>
        <HistoryBackfillStatus run={{ ...baseRun, review: review({ csv_covers_all: true }) }} onRetry={() => {}} retryPending={false} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/already covers this history/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Trading 212 CSV export/i })).not.toBeInTheDocument();
  });

  it("disables the retry while one is pending", () => {
    render(
      <MemoryRouter>
        <HistoryBackfillStatus run={{ ...baseRun, review: review() }} onRetry={() => {}} retryPending />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: /Retry history import/i })).toBeDisabled();
  });

  it("shows no panel for other states or when the run has no review data", () => {
    const { rerender } = render(
      <MemoryRouter>
        <HistoryBackfillStatus run={{ ...baseRun, review: null }} onRetry={() => {}} retryPending={false} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: /Retry history import/i })).not.toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <HistoryBackfillStatus run={{ ...baseRun, state: "completed", review: review() }} onRetry={() => {}} retryPending={false} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: /Retry history import/i })).not.toBeInTheDocument();
  });

  it("retries from Settings and refetches the run", async () => {
    mocks.fetchT212Status.mockResolvedValue({ connected: true, auto_sync: false, api_key_preview: "••••1234" });
    mocks.fetchT212HistoryStatus.mockResolvedValue({ connected: true, run: { id: "run-1", ...baseRun, review: review() } });
    mocks.retryT212History.mockResolvedValue({ run_id: "run-2", status: "pending", complete: false, blocked: false });
    mount("/settings?section=connections");

    fireEvent.click(await screen.findByRole("button", { name: /Retry history import/i }));

    await waitFor(() => expect(mocks.retryT212History).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mocks.fetchT212HistoryStatus.mock.calls.length).toBeGreaterThan(1));
  });

  it("surfaces a failed retry instead of failing silently", async () => {
    mocks.fetchT212Status.mockResolvedValue({ connected: true, auto_sync: false, api_key_preview: "••••1234" });
    mocks.fetchT212HistoryStatus.mockResolvedValue({ connected: true, run: { id: "run-1", ...baseRun, review: review() } });
    mocks.retryT212History.mockRejectedValue({ response: { status: 429, data: { detail: "Trading 212 rate limit reached" } } });
    mount("/settings?section=connections");

    fireEvent.click(await screen.findByRole("button", { name: /Retry history import/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/rate limit reached/i);
    expect(screen.getByRole("button", { name: /Retry history import/i })).toBeEnabled();
  });
});

describe("Trading 212 fast position snapshot", () => {
  it("shows the current position count, value, and freshness", async () => {
    mocks.fetchT212Status.mockResolvedValue({ connected: true, auto_sync: false, api_key_preview: "••••1234" });
    mocks.fetchT212Positions.mockResolvedValue({
      connected: true,
      status: "fresh",
      as_of: "2026-09-21T10:05:00Z",
      currency: "USD",
      positions: [
        { ticker: "AAPL", market_value: 100 },
        { ticker: "MSFT", market_value: 50 },
      ],
    });

    mount("/settings?section=connections");

    expect(await screen.findByText("2 positions")).toBeInTheDocument();
    expect(screen.getByText("$150.00")).toBeInTheDocument();
    expect(screen.getByText(/updated/)).toBeInTheDocument();
  });

  it("shows the snapshot as a compact summary instead of the full list", async () => {
    mocks.fetchT212Status.mockResolvedValue({ connected: true, auto_sync: false, api_key_preview: "1234" });
    mocks.fetchT212Positions.mockResolvedValue({
      connected: true,
      status: "fresh",
      as_of: "2026-09-21T10:05:00Z",
      currency: "USD",
      positions: [{ ticker: "AAPL", market_value: 100 }],
    });

    mount("/settings?section=connections");

    expect(await screen.findByRole("button", { name: "Show positions" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Current positions" })).not.toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });
});
