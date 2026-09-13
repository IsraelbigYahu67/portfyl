import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ChartSummary from "./ChartSummary";

describe("ChartSummary", () => {
  it("renders a named disclosure with supplied non-visual data", () => {
    render(
      <ChartSummary title="Performance chart data">
        <table>
          <tbody>
            <tr><td>Portfolio</td><td>12%</td></tr>
          </tbody>
        </table>
      </ChartSummary>
    );
    expect(screen.getByRole("group", { name: "Performance chart data" })).toHaveTextContent("Portfolio12%");
  });
});
