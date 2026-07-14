import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SyncScheduleSettings from "./SyncScheduleSettings";

// vi.mock factories are hoisted above top-level consts — a plain `const spy`
// referenced inside the factory would hit a TDZ error. vi.hoisted() runs first.
const mocks = vi.hoisted(() => ({
  fetchSyncSchedule: vi.fn(() =>
    Promise.resolve({
      mode: "daily",
      daily_time: "02:00",
      interval_hours: 6,
      timezone: "Europe/Prague",
      last_run: null,
      next_run: null,
    })
  ),
  updateSyncSchedule: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../api", () => ({
  fetchSyncSchedule: mocks.fetchSyncSchedule,
  updateSyncSchedule: mocks.updateSyncSchedule,
}));

function mount() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <SyncScheduleSettings />
    </QueryClientProvider>
  );
}

describe("SyncScheduleSettings", () => {
  it("seeds the form from the API and shows the timezone", async () => {
    mount();
    expect(await screen.findByText(/Auto-sync schedule/i)).toBeInTheDocument();
    expect(await screen.findByDisplayValue("02:00")).toBeInTheDocument();
    expect(screen.getByText(/Europe\/Prague/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /daily at/i })).toBeChecked();
  });

  it("saves the edited schedule", async () => {
    mount();
    await screen.findByDisplayValue("02:00");
    fireEvent.click(screen.getByRole("radio", { name: /every/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(mocks.updateSyncSchedule).toHaveBeenCalledWith({
        mode: "interval",
        daily_time: "02:00",
        interval_hours: 6,
      })
    );
  });

  it("displays error banner when initial fetch fails", async () => {
    mocks.fetchSyncSchedule.mockRejectedValueOnce(new Error("Network error"));
    mount();
    expect(await screen.findByText(/Failed to load sync schedule/i)).toBeInTheDocument();
  });
});
