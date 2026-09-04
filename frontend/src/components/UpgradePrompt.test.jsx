import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import UpgradePrompt from "./UpgradePrompt";


describe("UpgradePrompt", () => {
  it("turns a stable backend denial into a pricing link", () => {
    render(<MemoryRouter><UpgradePrompt /></MemoryRouter>);
    act(() => {
      window.dispatchEvent(new CustomEvent("portfyl:entitlement-denied", {
        detail: { code: "resource_read_only", resource: "portfolios", limit: 1 },
      }));
    });
    expect(screen.getByText(/read-only on your plan/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Compare plans/i })).toHaveAttribute("href", "/pricing");
    fireEvent.click(screen.getByLabelText(/Dismiss upgrade prompt/i));
    expect(screen.queryByText(/read-only on your plan/i)).not.toBeInTheDocument();
  });
});
