import { useCallback, useEffect, useState } from "react";

// Recharts only shows a donut tooltip for the slice the pointer ENTERS. A
// finger dragged across the chart never enters anything new (touch events keep
// firing on the element the touch started on), so on a phone the tooltip would
// show for the first slice only. This hook follows the finger instead: it looks
// up the slice under it (`elementFromPoint`) and replays mouse over/out events
// on that slice, which Recharts already turns into its own tooltip.
//
// Used through <PieTouchScrub>, which also lifts the tooltip above the finger
// while it is down (otherwise the finger sits right on top of it).

const SECTOR = ".recharts-pie-sector";
// How far the tooltip floats above where Recharts would put it, in px. Roughly
// a fingertip plus a one-line tooltip.
const TOOLTIP_LIFT = 72;
const TOOLTIP_Z = 50;

function fire(type, target, relatedTarget) {
  target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, relatedTarget }));
}

export default function usePieTouchScrub() {
  // A callback ref (state, not useRef) so the listeners attach even when the
  // chart wrapper mounts later than the component that owns the hook.
  const [node, setNode] = useState(null);
  const [scrubbing, setScrubbing] = useState(false);

  useEffect(() => {
    if (!node) return undefined;
    let active = null; // the slice whose tooltip is open
    let down = false; // a finger that started on a slice is still on the screen

    const sectorAt = (touch) => {
      const hit = document.elementFromPoint(touch.clientX, touch.clientY)?.closest?.(SECTOR);
      return hit && node.contains(hit) ? hit : null;
    };

    // React derives both "leave the old slice" and "enter the new one" from a
    // single mouseout whose relatedTarget is the new slice. A first slice has
    // nothing to leave, so it gets a plain mouseover.
    const activate = (next) => {
      if (next === active) return;
      if (active) fire("mouseout", active, next);
      else fire("mouseover", next, null);
      active = next;
    };

    // Listening on the document lets a touch anywhere else (including outside
    // this chart) close the tooltip that a lifted finger left open.
    const onStart = (event) => {
      const touch = event.touches[0];
      const hit = touch ? sectorAt(touch) : null;
      down = Boolean(hit);
      if (hit) activate(hit);
      else if (active) activate(null);
      setScrubbing(down);
    };
    const onMove = (event) => {
      if (!down || !event.touches[0]) return;
      // The drag belongs to the chart, not to page scroll.
      if (event.cancelable) event.preventDefault();
      // Between slices (the 3-degree gaps, the hole) keep the last one.
      const hit = sectorAt(event.touches[0]);
      if (hit) activate(hit);
    };
    const onEnd = () => {
      down = false;
      setScrubbing(false);
    };

    document.addEventListener("touchstart", onStart, { passive: true });
    node.addEventListener("touchmove", onMove, { passive: false });
    node.addEventListener("touchend", onEnd);
    node.addEventListener("touchcancel", onEnd);
    return () => {
      document.removeEventListener("touchstart", onStart);
      node.removeEventListener("touchmove", onMove);
      node.removeEventListener("touchend", onEnd);
      node.removeEventListener("touchcancel", onEnd);
    };
  }, [node]);

  // Spread onto the chart's <Tooltip>. The z-index keeps the bubble above any
  // overlay sitting on the donut (e.g. the "Total value" text in its hole).
  const tooltipProps = scrubbing
    ? { isAnimationActive: false, wrapperStyle: { marginTop: -TOOLTIP_LIFT, zIndex: TOOLTIP_Z } }
    : { wrapperStyle: { zIndex: TOOLTIP_Z } };

  const ref = useCallback((el) => setNode(el), []);
  return { ref, tooltipProps };
}

// Wraps a Recharts donut: `children` is called with the props to spread onto
// its <Tooltip>. Keeps the hook out of components with early returns.
export function PieTouchScrub({ className, children }) {
  const { ref, tooltipProps } = usePieTouchScrub();
  return (
    <div ref={ref} className={className}>
      {children(tooltipProps)}
    </div>
  );
}
