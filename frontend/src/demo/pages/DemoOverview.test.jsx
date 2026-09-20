import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import DemoOverview from "./DemoOverview";
import { DemoDataProvider } from "../DemoDataContext";

vi.mock("../../api", () => new Proxy({}, {
  get() {
    throw new Error("The public demo must not import the API client");
  },
}));

function renderOverview() {
  return render(
    <MemoryRouter>
      <DemoDataProvider><DemoOverview /></DemoDataProvider>
    </MemoryRouter>
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("DemoOverview", () => {
  it("renders the complete synthetic USD portfolio without network access", () => {
    const fetch = vi.fn(() => {
      throw new Error("The public demo must not fetch data");
    });
    vi.stubGlobal("fetch", fetch);

    renderOverview();

    expect(screen.getByText(/final value \$105,000\.00/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "VUAA" })).toHaveAttribute("href", "/demo/stock/VUAA");
    expect(screen.getByRole("link", { name: "MSFT" })).toHaveAttribute("href", "/demo/stock/MSFT");
    expect(screen.getAllByRole("row")).toHaveLength(11);
    expect(screen.getByRole("region", { name: "Portfolio performance summary" })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
