import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import DemoDividends from "./DemoDividends";
import { DemoDataProvider } from "../DemoDataContext";

vi.mock("../../api", () => new Proxy({}, {
  get() {
    throw new Error("The public demo must not import the API client");
  },
}));

afterEach(() => vi.unstubAllGlobals());

describe("DemoDividends", () => {
  it("reconciles the synthetic dividend income in quarterly, payer, and year-over-year views locally", () => {
    const fetch = vi.fn(() => {
      throw new Error("The public demo must not fetch data");
    });
    vi.stubGlobal("fetch", fetch);

    render(<MemoryRouter><DemoDataProvider><DemoDividends /></DemoDataProvider></MemoryRouter>);

    expect(screen.getByText("$2,840.00")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Synthetic dividend payments" })).toBeInTheDocument();
    expect(screen.getAllByText("2025 Q1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MSFT").length).toBeGreaterThan(0);
    expect(screen.getAllByText("PLD").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/↑|↓/).length).toBeGreaterThan(0);
    expect(fetch).not.toHaveBeenCalled();
  });
});
