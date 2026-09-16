import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { UrlTabs } from "./UrlTabs";

const items = [
  { value: "overview", label: "Overview", panelId: "overview-panel" },
  { value: "financials", label: "Financials", panelId: "financials-panel" },
  { value: "filings", label: "Filings", panelId: "filings-panel", disabled: true },
];

describe("UrlTabs", () => {
  it("renders an accessible tablist with one selected tab stop", () => {
    render(
      <UrlTabs
        ariaLabel="Stock sections"
        idPrefix="stock"
        items={items}
        value="overview"
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("tablist", { name: "Stock sections" })).toBeInTheDocument();
    const overview = screen.getByRole("tab", { name: "Overview" });
    const financials = screen.getByRole("tab", { name: "Financials" });
    const filings = screen.getByRole("tab", { name: "Filings" });
    expect(overview).toHaveAttribute("id", "stock-overview-tab");
    expect(overview).toHaveAttribute("aria-controls", "overview-panel");
    expect(overview).toHaveAttribute("aria-selected", "true");
    expect(overview).toHaveAttribute("tabindex", "0");
    expect(financials).toHaveAttribute("aria-selected", "false");
    expect(financials).toHaveAttribute("tabindex", "-1");
    expect(filings).toBeDisabled();
  });

  it("selects on click and moves focus with wrapping arrow, Home, and End keys", () => {
    const onChange = vi.fn();
    render(
      <UrlTabs
        ariaLabel="Stock sections"
        idPrefix="stock"
        items={items}
        value="overview"
        onChange={onChange}
      />,
    );

    const overview = screen.getByRole("tab", { name: "Overview" });
    const financials = screen.getByRole("tab", { name: "Financials" });
    const filings = screen.getByRole("tab", { name: "Filings" });

    fireEvent.click(financials);
    expect(onChange).toHaveBeenLastCalledWith("financials");

    overview.focus();
    fireEvent.keyDown(overview, { key: "ArrowRight" });
    expect(financials).toHaveFocus();
    expect(onChange).toHaveBeenLastCalledWith("financials");

    fireEvent.keyDown(financials, { key: "ArrowRight" });
    expect(overview).toHaveFocus();
    expect(onChange).toHaveBeenLastCalledWith("overview");

    fireEvent.keyDown(overview, { key: "ArrowLeft" });
    expect(financials).toHaveFocus();

    fireEvent.keyDown(financials, { key: "Home" });
    expect(overview).toHaveFocus();

    fireEvent.keyDown(overview, { key: "End" });
    expect(financials).toHaveFocus();

    fireEvent.click(filings);
    expect(onChange).not.toHaveBeenCalledWith("filings");
  });
});
