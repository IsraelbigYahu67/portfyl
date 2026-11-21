import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchBillingStatus } from "../../api";
import { noticeKey } from "../../lib/trial";
import TrialBanner from "./TrialBanner";

vi.mock("../../api", () => ({ fetchBillingStatus: vi.fn() }));
vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({ currentWorkspace: { id: "ws-1" } }),
}));

const DAY = 86_400_000;
const inDays = (days) => new Date(Date.now() + days * DAY - 60_000).toISOString();

function renderBanner(path = "/dashboard") {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <TrialBanner />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => localStorage.clear());

describe("TrialBanner", () => {
  it("shows the countdown with a link to the plans", async () => {
    fetchBillingStatus.mockResolvedValue({ plan: "pro", source: "trial", effective_until: inDays(6) });
    renderBanner();

    expect(await screen.findByRole("status")).toHaveTextContent("Pro trial: 6 days left");
    expect(screen.getByRole("link", { name: "Compare plans" })).toHaveAttribute("href", "/pricing");
  });

  it("says the trial ends today under 24 hours", async () => {
    fetchBillingStatus.mockResolvedValue({ plan: "pro", source: "trial", effective_until: new Date(Date.now() + 3_600_000).toISOString() });
    renderBanner();

    expect(await screen.findByText("Your Pro trial ends today")).toBeInTheDocument();
  });

  it.each([
    ["expired", /Your Pro trial has ended/],
    ["broker_account_reused", /this broker account already had a free trial/],
    ["history_reused", /the same transaction history already had a free trial/],
  ])("explains an ended trial (%s) and can be dismissed", async (reason, text) => {
    fetchBillingStatus.mockResolvedValue({ plan: "free", source: "free", trial_ended_reason: reason });
    renderBanner();

    expect(await screen.findByText(text)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss trial notice" }));

    expect(localStorage.getItem(noticeKey("ws-1"))).toBe(`ended:${reason}`);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("stays hidden after a dismissal at 5 days, and returns for the last 3 days", async () => {
    localStorage.setItem(noticeKey("ws-1"), "active");
    fetchBillingStatus.mockResolvedValue({ plan: "pro", source: "trial", effective_until: inDays(5) });
    const first = renderBanner();
    await waitFor(() => expect(fetchBillingStatus).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    first.unmount();

    fetchBillingStatus.mockResolvedValue({ plan: "pro", source: "trial", effective_until: inDays(3) });
    renderBanner();
    expect(await screen.findByRole("status")).toHaveTextContent("Pro trial: 3 days left");
  });

  it("tells a withheld trial", async () => {
    fetchBillingStatus.mockResolvedValue({ plan: "free", source: "free", trial_ended_reason: "not_eligible" });
    renderBanner();

    expect(await screen.findByText(/a free trial was already used for this e-mail address or network/)).toBeInTheDocument();
  });

  it("renders nothing on the pricing page", async () => {
    fetchBillingStatus.mockResolvedValue({ plan: "pro", source: "trial", effective_until: inDays(6) });
    renderBanner("/pricing");

    await waitFor(() => expect(fetchBillingStatus).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders nothing for a subscription or when trials are off", async () => {
    fetchBillingStatus.mockResolvedValue({ plan: "investor", source: "subscription", trial_ended_reason: null });
    const first = renderBanner();
    await waitFor(() => expect(fetchBillingStatus).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    first.unmount();

    fetchBillingStatus.mockResolvedValue({ plan: "free", source: "free", trial_ended_reason: null });
    renderBanner();
    await waitFor(() => expect(fetchBillingStatus).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders nothing and throws nothing when the status cannot be loaded", async () => {
    fetchBillingStatus.mockRejectedValue(new Error("network"));
    const { container } = renderBanner();

    await waitFor(() => expect(fetchBillingStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
