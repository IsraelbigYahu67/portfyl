import { useLayoutEffect, useRef, useState } from "react";

/**
 * Segmented toggle — the grey pill-row pattern repeated across the app.
 *
 *   <SegmentedControl
 *     aria-label="Chart mode"
 *     value={mode}
 *     onChange={setMode}
 *     options={[{ value: "value", label: "Value" }, { value: "growth", label: "Growth %" }]}
 *   />
 *
 * The highlighted pill is one shared element that slides between options.
 * Its leading edge moves faster than its trailing edge, so it stretches and
 * then settles into the clicked option like liquid pouring across.
 */
const SIZES = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-2.5 py-1 text-xs",
};

const LEADING = "0.28s cubic-bezier(0.34, 1.1, 0.64, 1)";
const TRAILING = "0.45s cubic-bezier(0.34, 1.1, 0.64, 1) 0.05s";

export default function SegmentedControl({
  options,
  value,
  onChange,
  size = "md",
  block = false,
  className = "",
  "aria-label": ariaLabel,
}) {
  const rootRef = useRef(null);
  const buttonRefs = useRef({});
  const previousIndex = useRef(-1);
  const [thumb, setThumb] = useState(null);

  const activeIndex = options.findIndex((opt) => opt.value === value);

  useLayoutEffect(() => {
    const root = rootRef.current;
    const button = buttonRefs.current[value];
    if (!root || !button) {
      setThumb(null);
      return undefined;
    }

    const measure = (animate) => {
      const next = {
        left: button.offsetLeft,
        right: root.clientWidth - button.offsetLeft - button.offsetWidth,
        top: button.offsetTop,
        height: button.offsetHeight,
        // 1 = moving right (right edge leads), -1 = moving left (left edge leads).
        direction: previousIndex.current <= activeIndex ? 1 : -1,
        animate,
      };
      setThumb((prev) =>
        prev && prev.left === next.left && prev.right === next.right && prev.top === next.top && prev.height === next.height
          ? prev
          : next
      );
    };

    measure(previousIndex.current !== -1);
    previousIndex.current = activeIndex;

    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => measure(false));
    observer.observe(root);
    return () => observer.disconnect();
  }, [value, activeIndex, options]);

  const thumbStyle = thumb && {
    left: thumb.left,
    right: thumb.right,
    top: thumb.top,
    height: thumb.height,
    transition: thumb.animate
      ? `left ${thumb.direction === 1 ? TRAILING : LEADING}, right ${thumb.direction === 1 ? LEADING : TRAILING}, top 0.2s ease, height 0.2s ease`
      : "none",
  };

  return (
    <div
      ref={rootRef}
      role="group"
      aria-label={ariaLabel}
      className={`segmented relative ${block ? "flex w-full" : "inline-flex"} gap-0.5 rounded-[var(--radius-card)] bg-surface-hover p-0.5 ${className}`}
    >
      {thumb && (
        <span
          aria-hidden="true"
          className="segmented-thumb pointer-events-none absolute rounded-[var(--radius-card)] bg-surface-card-elevated"
          style={thumbStyle}
        />
      )}
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            ref={(node) => {
              if (node) buttonRefs.current[opt.value] = node;
              else delete buttonRefs.current[opt.value];
            }}
            type="button"
            aria-pressed={active}
            aria-label={opt.title}
            disabled={opt.disabled}
            title={opt.title}
            onClick={() => onChange(opt.value)}
            className={`relative z-10 rounded-[var(--radius-card)] font-medium transition-colors ${block ? "flex-1 flex items-center justify-center" : ""} ${SIZES[size]} ${
              active
                ? `font-semibold text-brand${thumb ? "" : " bg-surface-card-elevated"}`
                : "text-muted hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-muted"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
