import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import Settings from "./Settings";

const mocks = vi.hoisted(() => ({
  fetchT212Status: vi.fn(),
  discordMount: vi.fn(),
  dataMount: vi.fn(),
}));

vi.mock("../api", () => ({
  fetchT212Status: mocks.fetchT212Status,
  connectT212: vi.fn(),
  disconnectT212: vi.fn(),
  syncT212: vi.fn(),
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
