import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import Pricing from "./Pricing";


describe("Pricing", () => {
  it("shows the static plan catalogue and discloses that payments are coming soon", () => {
    render(<Pricing />);

    expect(screen.getByRole("heading", { name: "Plans" })).toBeInTheDocument();
    expect(screen.getByText(/Paid plans are coming soon/i)).toBeInTheDocument();
    expect(
      screen.getByText(/All cloud workspaces currently use the Free plan\./i),
    ).toBeInTheDocument();
    expect(screen.getByText("€4.99 / month")).toBeInTheDocument();
    expect(screen.getByText("or €49.00 annually")).toBeInTheDocument();
    expect(screen.getByText("€7.99 / month")).toBeInTheDocument();
    expect(screen.getByText("or €79.00 annually")).toBeInTheDocument();
    expect(screen.queryByText(/Manage billing|trial|Stripe/i)).not.toBeInTheDocument();
  });

  it("opens and closes an informational dialog instead of starting checkout", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<Pricing />);

    fireEvent.click(screen.getByRole("button", { name: /Investor monthly.*coming soon/i }));

    const dialog = screen.getByRole("dialog", { name: "Payments are coming soon" });
    expect(dialog).toHaveTextContent("Payments are not available yet");
    expect(dialog).toHaveTextContent("Investor");
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    expect(fetchSpy).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fetchSpy.mockRestore();
  });

  it("provides an explicit close control for the dialog", () => {
    render(<Pricing />);

    fireEvent.click(screen.getByRole("button", { name: /Pro annual.*coming soon/i }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("contains focus and restores it to the invoking CTA after closing", () => {
    render(<Pricing />);

    const invoker = screen.getByRole("button", { name: /Investor monthly.*coming soon/i });
    fireEvent.click(invoker);

    const closeButton = screen.getByRole("button", { name: "Close" });
    const confirmationButton = screen.getByRole("button", { name: "Got it" });
    confirmationButton.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    expect(confirmationButton).toHaveFocus();

    fireEvent.click(closeButton);
    expect(invoker).toHaveFocus();
  });
});
