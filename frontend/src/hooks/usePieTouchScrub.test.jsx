import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, act } from "@testing-library/react";
import { PieTouchScrub } from "./usePieTouchScrub";

// Stand-ins for Recharts slices: same class, and React enter/leave handlers
// like the ones Recharts attaches to drive its tooltip.
function Harness({ log }) {
  return (
    <PieTouchScrub className="wrap">
      {(tooltipProps) => (
        <>
          <span data-testid="props">{JSON.stringify(tooltipProps)}</span>
          {["a", "b"].map((id) => (
            <svg key={id}>
              <g
                className="recharts-pie-sector"
                data-testid={id}
                onMouseEnter={() => log.push(`enter ${id}`)}
                onMouseLeave={() => log.push(`leave ${id}`)}
              >
                <path data-testid={`${id}-path`} />
              </g>
            </svg>
          ))}
        </>
      )}
    </PieTouchScrub>
  );
}

const point = { clientX: 5, clientY: 5 };

describe("PieTouchScrub", () => {
  let hit;
  beforeEach(() => {
    hit = null;
    document.elementFromPoint = vi.fn(() => hit);
  });
  afterEach(() => {
    delete document.elementFromPoint;
  });

  it("opens the slice under the finger and follows it to the next one", () => {
    const log = [];
    const { getByTestId } = render(<Harness log={log} />);

    hit = getByTestId("a-path");
    fireEvent.touchStart(getByTestId("a-path"), { touches: [point] });
    expect(log).toEqual(["enter a"]);

    hit = getByTestId("b-path");
    fireEvent.touchMove(getByTestId("a-path"), { touches: [point] });
    expect(log).toEqual(["enter a", "leave a", "enter b"]);
  });

  it("keeps the last slice while the finger is over a gap", () => {
    const log = [];
    const { getByTestId } = render(<Harness log={log} />);

    hit = getByTestId("a-path");
    fireEvent.touchStart(getByTestId("a-path"), { touches: [point] });
    hit = null;
    fireEvent.touchMove(getByTestId("a-path"), { touches: [point] });
    expect(log).toEqual(["enter a"]);
  });

  it("lifts the tooltip only while the finger is down", () => {
    const log = [];
    const { getByTestId } = render(<Harness log={log} />);
    const style = () => JSON.parse(getByTestId("props").textContent).wrapperStyle;
    // Always above overlays on the donut, never lifted until a finger is down.
    expect(style().zIndex).toBeGreaterThan(0);
    expect(style().marginTop).toBeUndefined();

    hit = getByTestId("a-path");
    fireEvent.touchStart(getByTestId("a-path"), { touches: [point] });
    expect(style().marginTop).toBeLessThan(0);
    expect(style().zIndex).toBeGreaterThan(0);

    fireEvent.touchEnd(getByTestId("a-path"));
    expect(style().marginTop).toBeUndefined();
    // Lifting the finger leaves the tooltip open.
    expect(log).toEqual(["enter a"]);
  });

  it("blocks page scroll during a drag that started on a slice", () => {
    const { getByTestId } = render(<Harness log={[]} />);
    hit = getByTestId("a-path");
    fireEvent.touchStart(getByTestId("a-path"), { touches: [point] });
    const notPrevented = fireEvent.touchMove(getByTestId("a-path"), { touches: [point] });
    expect(notPrevented).toBe(false);
  });

  it("leaves page scroll alone for a drag that started off the donut", () => {
    const { getByTestId } = render(<Harness log={[]} />);
    hit = null;
    fireEvent.touchStart(getByTestId("a-path"), { touches: [point] });
    const notPrevented = fireEvent.touchMove(getByTestId("a-path"), { touches: [point] });
    expect(notPrevented).toBe(true);
  });

  it("closes the tooltip when a later touch lands off the donut", () => {
    const log = [];
    const { getByTestId } = render(<Harness log={log} />);

    hit = getByTestId("a-path");
    fireEvent.touchStart(getByTestId("a-path"), { touches: [point] });
    fireEvent.touchEnd(getByTestId("a-path"));

    hit = document.body;
    act(() => {
      fireEvent.touchStart(document.body, { touches: [point] });
    });
    expect(log).toEqual(["enter a", "leave a"]);
  });
});
