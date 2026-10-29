import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render as rtlRender, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  changePlan,
  confirmCheckout,
  fetchBillingStatus,
  fetchTestPlan,
  openBillingPortal,
  startCheckout,
  updateTestPlan,
} from "../api";
import Pricing from "./Pricing";


vi.mock("../api", () => ({
  changePlan: vi.fn(),
  confirmCheckout: vi.fn(),
  fetchBillingStatus: vi.fn(),
  fetchTestPlan: vi.fn(),
  openBillingPortal: vi.fn(),
  startCheckout: vi.fn(),
  updateTestPlan: vi.fn(),
}));

let queryClient;

function render(ui) {
  queryClient = new QueryClient();
  return rtlRender(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function billingStatus(overrides = {}) {
  return {
    plan: "free",
    source: "free",
    billing_enabled: true,
    can_manage_billing: true,
    has_billing_account: false,
    prices: { currency: "eur", monthly_cents: { investor: 599, pro: 999 } },
    subscription: null,
    ...overrides,
  };
}

const originalLocation = window.location;

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...originalLocation, assign: vi.fn(), search: "", pathname: "/pricing" },
  });
});

afterEach(() => {
  Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
});


describe("Pricing read-only (local edition)", () => {
  it("renders the catalogue without any billing or test-plan API call", () => {
    render(<Pricing planSwitching={false} />);

    expect(screen.getByText(/Local edition: every feature is included/i)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Investor" })).getByText("€5.99")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Pro" })).getByText("€9.99")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(fetchBillingStatus).not.toHaveBeenCalled();
    expect(fetchTestPlan).not.toHaveBeenCalled();
  });
});


describe("Pricing in the no-payment test mode", () => {
  beforeEach(() => {
    fetchBillingStatus.mockResolvedValue(billingStatus({ billing_enabled: false }));
    fetchTestPlan.mockResolvedValue({ plan: "free", switching_enabled: true, payments_enabled: false });
  });

  it("shows the catalogue and makes the no-payment test boundary explicit", async () => {
    render(<Pricing />);

    expect(screen.getByRole("heading", { name: "Plans" })).toBeInTheDocument();
    expect(await screen.findByText(/Free plan switching during private testing/i)).toBeInTheDocument();
    expect(screen.getByText(/No payment method, checkout, charge, or subscription/i)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Free" })).getByText("€0")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Investor" })).getByText("€5.99")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Pro" })).getByText("€9.99")).toBeInTheDocument();
    expect(screen.queryByText(/annually/i)).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Active for testing" })).toBeDisabled();
    expect(screen.queryByText(/Manage subscription|Link/)).not.toBeInTheDocument();
  });

  it("switches the workspace plan without starting checkout", async () => {
    updateTestPlan.mockResolvedValue({ plan: "investor" });
    render(<Pricing />);
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    fireEvent.click(await screen.findByRole("button", { name: "Use Investor for testing" }));

    await waitFor(() => expect(updateTestPlan).toHaveBeenCalledWith("investor"));
    expect(await screen.findByText("Current test plan")).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["plan-capabilities"] });
    expect(startCheckout).not.toHaveBeenCalled();
  });

  it("keeps the current plan and reports a failed change", async () => {
    updateTestPlan.mockRejectedValue(new Error("network"));
    render(<Pricing />);

    fireEvent.click(await screen.findByRole("button", { name: "Use Pro for testing" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The plan could not be changed");
    expect(screen.getByRole("button", { name: "Active for testing" })).toBeDisabled();
  });
});


describe("Pricing with Stripe payments", () => {
  it("requires the immediate-start consent before checkout", async () => {
    fetchBillingStatus.mockResolvedValue(billingStatus());
    startCheckout.mockResolvedValue({ url: "https://checkout.stripe.test/cs_1" });
    render(<Pricing />);

    const upgrade = await screen.findByRole("button", { name: "Upgrade to Pro" });
    expect(upgrade).toBeDisabled();
    expect(screen.getByText(/Secure payments through Link/)).toBeInTheDocument();
    expect(fetchTestPlan).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("checkbox", { name: /lose my 14-day right of withdrawal/i }));
    fireEvent.click(upgrade);

    await waitFor(() => expect(startCheckout).toHaveBeenCalledWith("pro"));
    await waitFor(() => expect(window.location.assign).toHaveBeenCalledWith("https://checkout.stripe.test/cs_1"));
  });

  it("books a plan switch for the next period instead of charging now", async () => {
    const subscription = {
      plan: "investor",
      status: "active",
      current_period_end: "2026-11-28T12:00:00+00:00",
      cancel_at_period_end: false,
      grace_ends_at: null,
      scheduled_plan: null,
      scheduled_change_at: null,
    };
    fetchBillingStatus.mockResolvedValue(billingStatus({
      plan: "investor", source: "subscription", has_billing_account: true, subscription,
    }));
    changePlan.mockResolvedValue(billingStatus({
      plan: "investor",
      source: "subscription",
      has_billing_account: true,
      subscription: { ...subscription, scheduled_plan: "pro", scheduled_change_at: "2026-11-28T12:00:00+00:00" },
    }));
    render(<Pricing />);

    expect(await screen.findByText(/Renews automatically on November 28, 2026/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Current plan" })).toBeDisabled();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Switch to Pro from November 28, 2026" }));

    await waitFor(() => expect(changePlan).toHaveBeenCalledWith("pro"));
    expect(await screen.findByText(/Pro starts on November 28, 2026\. Until then you keep Investor/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep Investor" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Starts next period" })).toBeDisabled();
    expect(window.location.assign).not.toHaveBeenCalled();
    expect(openBillingPortal).not.toHaveBeenCalled();
  });

  it("sends a cancelling subscriber to the portal to resume first", async () => {
    fetchBillingStatus.mockResolvedValue(billingStatus({
      plan: "pro",
      source: "subscription",
      has_billing_account: true,
      subscription: {
        plan: "pro",
        status: "active",
        current_period_end: "2026-11-28T12:00:00+00:00",
        cancel_at_period_end: true,
        scheduled_plan: null,
        scheduled_change_at: null,
      },
    }));
    openBillingPortal.mockResolvedValue({ url: "https://billing.stripe.test/p" });
    render(<Pricing />);

    expect(await screen.findByText(/Cancelled\. Your plan stays active until November 28, 2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Manage in billing portal" }));
    await waitFor(() => expect(window.location.assign).toHaveBeenCalledWith("https://billing.stripe.test/p"));
    expect(changePlan).not.toHaveBeenCalled();
  });

  it("confirms the checkout when Stripe redirects back", async () => {
    window.location.search = "?checkout=success&session_id=cs_42";
    const replaceState = vi.spyOn(window.history, "replaceState").mockImplementation(() => {});
    fetchBillingStatus.mockResolvedValue(billingStatus());
    confirmCheckout.mockResolvedValue(billingStatus({
      plan: "pro",
      checkout_status: "complete",
      subscription: { plan: "pro", status: "active", current_period_end: null, cancel_at_period_end: false },
    }));
    render(<Pricing />);

    expect(await screen.findByText("Thank you! Your subscription is active.")).toBeInTheDocument();
    expect(confirmCheckout).toHaveBeenCalledWith("cs_42");
    expect(replaceState).toHaveBeenCalledWith(null, "", "/pricing");
    replaceState.mockRestore();
  });

  it("tells non-owners that only the owner manages billing", async () => {
    fetchBillingStatus.mockResolvedValue(billingStatus({ can_manage_billing: false }));
    render(<Pricing />);

    expect(await screen.findByText(/Only the workspace owner/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upgrade to Investor" })).toBeDisabled();
  });
});
