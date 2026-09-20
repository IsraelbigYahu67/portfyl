import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import OptionsCalendar from "./OptionsCalendar";

describe("OptionsCalendar", () => {
  it("renders a day's P&L with the financial-data semantic class and no sub-12px text", () => {
    const today = new Date();
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
    const { container } = render(
      <OptionsCalendar data={[{ date: dateStr, pnl: 250, trades_count: 2 }]} />
    );

    expect(screen.getByText("+$250")).toHaveClass("financial-data");
    expect(container.querySelectorAll('[class*="text-[8px]"], [class*="text-[9px]"], [class*="text-[10px]"], [class*="text-[11px]"]').length).toBe(0);
  });
});
