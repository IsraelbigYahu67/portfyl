import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { legacyColorClassesIn } from "../test/legacyClasses";
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
    expect(screen.getByRole("button", { name: "Daily at" })).toHaveAttribute("aria-pressed", "true");
  });

  it("sync schedule mode is a segmented control", async () => {
    const { container } = mount();
    await screen.findByDisplayValue("02:00");
    const group = screen.getByRole("group", { name: "Sync mode" });
    expect(group).toHaveClass("segmented");
    expect(within(group).getByRole("button", { name: "Daily at" })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: "Every N hours" })).toBeInTheDocument();
    expect(container.querySelector('input[type="radio"]')).toBeNull();
  });

  it("shows the time field in daily mode and the hours field in interval mode", async () => {
    mount();
    await screen.findByDisplayValue("02:00");
    expect(screen.queryByLabelText("Hours between syncs")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Every N hours" }));
    expect(screen.getByLabelText("Hours between syncs")).toHaveValue(6);
    expect(screen.queryByLabelText("Sync time")).not.toBeInTheDocument();
  });

  it("saves the edited schedule", async () => {
    mount();
    await screen.findByDisplayValue("02:00");
    fireEvent.click(screen.getByRole("button", { name: "Every N hours" }));
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

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./SyncScheduleSettings.jsx", import.meta.url))).toEqual([]);
  });
});
