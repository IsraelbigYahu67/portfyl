import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Heatmap, { squarify, tileLabels } from "./Heatmap";
import { fetchHeatmap } from "../api";
import { legacyColorClassesIn } from "../test/legacyClasses";

vi.mock("../api", () => ({ fetchHeatmap: vi.fn() }));
vi.mock("../hooks/useStockDetail", () => ({ useStockDetail: () => ({ openStock: vi.fn() }) }));

describe("Heatmap period change", () => {
  it("shows the loading label over the old treemap while the next period loads, so the card does not resize", async () => {
    fetchHeatmap.mockResolvedValueOnce([{ ticker: "AAPL", weight: 60, change_pct: 1 }]);
    fetchHeatmap.mockReturnValueOnce(new Promise(() => {})); // 1W never resolves
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Heatmap />
      </QueryClientProvider>,
    );
    await vi.waitFor(() => expect(screen.queryByText("Loading heatmap…")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "1W" }));

    // Loading is shown, but as an overlay: the old tiles stay mounted, so the
    // treemap box (and the card around it) keeps its size.
    expect(screen.getByText("Loading heatmap…")).toBeInTheDocument();
    expect(screen.getByTitle(/AAPL/)).toBeInTheDocument();
  });
});

describe("tileLabels", () => {
  it("tileLabels hides labels that cannot fit at 12px", () => {
    expect(tileLabels(30, 18)).toEqual({ ticker: false, change: false, weight: false });
    expect(tileLabels(40, 24)).toEqual({ ticker: true, change: false, weight: false });
    expect(tileLabels(60, 40)).toEqual({ ticker: true, change: true, weight: false });
    expect(tileLabels(80, 56)).toEqual({ ticker: true, change: true, weight: true });
  });
});

describe("squarify", () => {
  it("squarify keeps every tile inside the box", () => {
    const weights = [8, 8, 7, 6, 6, 5, 5, 4, 4, 4, 4, 4, 4, 3, 3, 3, 3, 3, 2, 2, 2, 1.9];
    const items = weights.map((weight, i) => ({ ticker: `T${i}`, weight, change_pct: 0 }));
    const tiles = squarify(items, 600, 400);
    expect(tiles).toHaveLength(items.length);
    for (const t of tiles) {
      expect(t.x).toBeGreaterThanOrEqual(0);
      expect(t.y).toBeGreaterThanOrEqual(0);
      expect(t.x + t.w).toBeLessThanOrEqual(600.5);
      expect(t.y + t.h).toBeLessThanOrEqual(400.5);
    }
  });
});

it("uses no legacy color classes", async () => {
  expect(await legacyColorClassesIn(new URL("./Heatmap.jsx", import.meta.url))).toEqual([]);
});
