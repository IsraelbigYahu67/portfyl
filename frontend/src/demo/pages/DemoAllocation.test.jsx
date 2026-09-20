import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import DemoAllocation from "./DemoAllocation";
import { DemoDataProvider } from "../DemoDataContext";

vi.mock("../../api", () => new Proxy({}, {
  get() {
    throw new Error("The public demo must not import the API client");
  },
}));

function renderAllocation() {
  return render(
    <MemoryRouter>
      <DemoDataProvider><DemoAllocation /></DemoDataProvider>
    </MemoryRouter>
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("DemoAllocation", () => {
  it("renders every synthetic asset and an equivalent allocation table without network access", () => {
    const fetch = vi.fn(() => {
      throw new Error("The public demo must not fetch data");
    });
    vi.stubGlobal("fetch", fetch);

    renderAllocation();

    expect(screen.getByText("100.00%")).toBeInTheDocument();
    for (const symbol of ["VUAA", "MSFT", "JPM", "JNJ", "XOM", "PG", "AMZN", "CAT", "NEE", "PLD"]) {
      expect(screen.getAllByText(symbol).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("10 sectors")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Allocation details" })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
