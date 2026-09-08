import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchTestPlan, updateTestPlan } from "../api";
import Pricing from "./Pricing";


vi.mock("../api", () => ({
  fetchTestPlan: vi.fn(),
  updateTestPlan: vi.fn(),
}));


describe("Pricing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchTestPlan.mockResolvedValue({
      plan: "free",
      switching_enabled: true,
      payments_enabled: false,
    });
  });

  it("shows the catalogue and makes the no-payment test boundary explicit", async () => {
    render(<Pricing />);

    expect(screen.getByRole("heading", { name: "Plans" })).toBeInTheDocument();
    expect(screen.getByText(/Free plan switching during private testing/i)).toBeInTheDocument();
    expect(screen.getByText(/No payment method, checkout, charge, or subscription/i)).toBeInTheDocument();
    expect(screen.getByText("€4.99 / month")).toBeInTheDocument();
    expect(screen.getByText("Planned price: €49.00 annually")).toBeInTheDocument();
    expect(screen.getByText("€7.99 / month")).toBeInTheDocument();
    expect(screen.getByText("Planned price: €79.00 annually")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Active for testing" })).toBeDisabled();
    expect(screen.queryByText(/Manage billing|trial|Stripe/i)).not.toBeInTheDocument();
  });

  it("switches the workspace plan without starting checkout", async () => {
    updateTestPlan.mockResolvedValue({ plan: "investor" });
    render(<Pricing />);

    const button = await screen.findByRole("button", { name: "Use Investor for testing" });
    fireEvent.click(button);

    await waitFor(() => expect(updateTestPlan).toHaveBeenCalledWith("investor"));
    expect(await screen.findByText("Current test plan")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Active for testing" })).toBeDisabled();
  });

  it("keeps the current plan and reports a failed change", async () => {
    updateTestPlan.mockRejectedValue(new Error("network"));
    render(<Pricing />);

    fireEvent.click(await screen.findByRole("button", { name: "Use Pro for testing" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The plan could not be changed");
    expect(screen.getByRole("button", { name: "Active for testing" })).toBeDisabled();
  });
});
