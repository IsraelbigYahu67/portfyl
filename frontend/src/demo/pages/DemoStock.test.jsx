import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import DemoStock from "./DemoStock";
import { DemoDataProvider } from "../DemoDataContext";

function renderAt(path) {
  return render(<MemoryRouter initialEntries={[path]}><DemoDataProvider><Routes><Route path="/demo/stock/:ticker" element={<DemoStock />} /></Routes></DemoDataProvider></MemoryRouter>);
}

afterEach(() => vi.unstubAllGlobals());

describe("DemoStock", () => {
  it.each([
    ["VUAA", "Vanguard S&P 500 UCITS ETF"], ["MSFT", "Microsoft"], ["JPM", "JPMorgan Chase"], ["JNJ", "Johnson & Johnson"], ["XOM", "Exxon Mobil"],
    ["PG", "Procter & Gamble"], ["AMZN", "Amazon"], ["CAT", "Caterpillar"], ["NEE", "NextEra Energy"], ["PLD", "Prologis"],
  ])("renders %s from the synthetic fixture without a network request", (symbol, name) => {
    const fetch = vi.fn(() => { throw new Error("Demo must not fetch data"); });
    vi.stubGlobal("fetch", fetch);
    renderAt(`/demo/stock/${symbol}`);
    expect(screen.getByRole("heading", { name: symbol })).toBeInTheDocument();
    expect(screen.getByText(name)).toBeInTheDocument();
    expect(screen.getByText(/Synthetic demo data/)).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("normalizes lowercase symbols and rejects unapproved or malformed symbols", () => {
    renderAt("/demo/stock/msft");
    expect(screen.getByRole("heading", { name: "MSFT" })).toBeInTheDocument();
    cleanup();
    renderAt("/demo/stock/not-a-symbol");
    expect(screen.getByText("Demo stock not found")).toBeInTheDocument();
  });
});
