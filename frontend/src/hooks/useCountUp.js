import { useEffect, useRef, useState } from "react";

function prefersReducedMotion() {
  return typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useCountUp(target, { duration = 900, enabled = true } = {}) {
  const isNumber = typeof target === "number" && Number.isFinite(target);
  const [value, setValue] = useState(isNumber ? (enabled ? 0 : target) : target);
  const frame = useRef(null);

  useEffect(() => {
    if (!isNumber || !enabled || prefersReducedMotion()) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const from = 0;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setValue(from + (target - from) * eased);
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => frame.current && cancelAnimationFrame(frame.current);
  }, [target, duration, enabled, isNumber]);

  return value;
}
