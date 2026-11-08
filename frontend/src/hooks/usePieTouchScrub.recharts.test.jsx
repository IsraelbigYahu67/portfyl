import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { PieChart, Pie, Cell, Tooltip } from "recharts";
import { PieTouchScrub } from "./usePieTouchScrub";

// The real Recharts donut: a finger over a slice must open Recharts' own
// tooltip for that slice, and dragging to another slice must switch it.
function Donut() {
  const data = [
    { name: "Tech", value: 60 },
    { name: "Energy", value: 40 },
  ];
  return (
    <PieTouchScrub>
      {(tooltipProps) => (
        <PieChart width={200} height={200}>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={40} outerRadius={80} isAnimationActive={false}>
            {data.map((d) => <Cell key={d.name} fill="red" />)}
          </Pie>
          <Tooltip {...tooltipProps} content={({ active, payload }) => (active && payload?.length ? <b data-testid="tip">{payload[0].payload.name}</b> : null)} />
        </PieChart>
      )}
    </PieTouchScrub>
  );
}

// Without a <Tooltip> (the dashboard draws its own label) the finger must still
// reach Pie's onMouseEnter, with the slice index.
function BareDonut({ onEnter }) {
  const data = [{ name: "Tech", value: 60 }, { name: "Energy", value: 40 }];
  return (
    <PieTouchScrub>
      {() => (
        <PieChart width={200} height={200}>
          <Pie data={data} dataKey="value" innerRadius={40} outerRadius={80} isAnimationActive={false} onMouseEnter={(_, i) => onEnter(i)}>
            {data.map((d) => <Cell key={d.name} fill="red" />)}
          </Pie>
        </PieChart>
      )}
    </PieTouchScrub>
  );
}

describe("PieTouchScrub with a real Recharts donut", () => {
  let hit;
  beforeEach(() => {
    hit = null;
    document.elementFromPoint = vi.fn(() => hit);
  });
  afterEach(() => {
    delete document.elementFromPoint;
  });

  it("shows the tooltip of the slice under the finger", () => {
    const { container, queryByTestId } = render(<Donut />);
    const sectors = container.querySelectorAll(".recharts-pie-sector");
    expect(sectors.length).toBe(2);

    hit = sectors[0].querySelector("path");
    fireEvent.touchStart(hit, { touches: [{ clientX: 1, clientY: 1 }] });
    expect(queryByTestId("tip")?.textContent).toBe("Tech");

    hit = sectors[1].querySelector("path");
    fireEvent.touchMove(hit, { touches: [{ clientX: 2, clientY: 2 }] });
    expect(queryByTestId("tip")?.textContent).toBe("Energy");
  });

  it("reports the slice index to Pie's onMouseEnter without a Tooltip", () => {
    const seen = [];
    const { container } = render(<BareDonut onEnter={(i) => seen.push(i)} />);
    const sectors = container.querySelectorAll(".recharts-pie-sector");

    hit = sectors[0].querySelector("path");
    fireEvent.touchStart(hit, { touches: [{ clientX: 1, clientY: 1 }] });
    hit = sectors[1].querySelector("path");
    fireEvent.touchMove(hit, { touches: [{ clientX: 2, clientY: 2 }] });
    expect(seen).toEqual([0, 1]);
  });
});
