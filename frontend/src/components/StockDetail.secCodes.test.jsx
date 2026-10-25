import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { attachSecCodes, InsiderTransactionsSection } from "./StockDetail";

const yf = (over) => ({ insider: "A", side: "other", shares: 1000, value: 0, date: "2026-07-27", ...over });

describe("attachSecCodes", () => {
  it("matches by date and share count and lets the SEC code decide the side", () => {
    const out = attachSecCodes(
      [yf({ side: "other" }), yf({ date: "2026-06-01", shares: 50, side: "sell" })],
      [{ tx_date: "2026-07-27", shares: 1000, tx_code: "P" }],
    );
    expect(out[0]).toMatchObject({ code: "P", side: "buy" });
    expect(out[1].code).toBeUndefined();
    expect(out[1].side).toBe("sell");
  });

  it("maps non-market codes to other", () => {
    const [row] = attachSecCodes([yf({ side: "sell" })], [{ tx_date: "2026-07-27", shares: 1000, tx_code: "F" }]);
    expect(row).toMatchObject({ code: "F", side: "other" });
  });

  it("returns the input unchanged when there is no SEC data", () => {
    const rows = [yf()];
    expect(attachSecCodes(rows, undefined)).toBe(rows);
  });
});

describe("InsiderTransactionsSection SEC extras", () => {
  it("shows the cluster-buy banner and the SEC code badge", () => {
    render(
      <InsiderTransactionsSection
        transactions={[yf({ code: "P", side: "buy" })]}
        currencyCode="USD"
        currentPrice={100}
        clusters={[{ start: "2026-07-01", end: "2026-07-20", buyers: ["Ann", "Bob", "Cy"] }]}
      />,
    );
    expect(screen.getByText("Cluster buy detected")).toBeInTheDocument();
    expect(screen.getByText("P")).toBeInTheDocument();
  });
});
