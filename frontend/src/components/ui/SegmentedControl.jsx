import { useEffect, useLayoutEffect, useRef, useState } from "react";

// The landing page is prerendered on the server, where useLayoutEffect only
// warns; the thumb is measured after hydration either way.
const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

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
 * An option with an `href` renders as a link (`aria-current="page"` when
 * active) so crawlers and middle-clicks can follow it; `onChange` still runs
 * on click, before the browser navigates.
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

  useIsomorphicLayoutEffect(() => {
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

    // On a phone the row scrolls sideways instead of wrapping; keep the chosen
    // option in view (scroll the row itself, never the page).
    if (root.scrollWidth > root.clientWidth) {
      const edge = button.offsetLeft + button.offsetWidth;
      if (button.offsetLeft < root.scrollLeft) root.scrollLeft = button.offsetLeft - 4;
      else if (edge > root.scrollLeft + root.clientWidth) root.scrollLeft = edge - root.clientWidth + 4;
    }

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
      className={`segmented relative ${block ? "flex w-full" : "inline-flex"} max-w-full max-sm:overflow-x-auto max-sm:[scrollbar-width:none] max-sm:[&::-webkit-scrollbar]:hidden gap-0.5 rounded-[var(--radius-card)] bg-surface-hover p-0.5 ${className}`}
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
        const Element = opt.href ? "a" : "button";
        const elementProps = opt.href
          ? { href: opt.href, hrefLang: opt.hrefLang, "aria-current": active ? "page" : undefined }
          : { type: "button", "aria-pressed": active, disabled: opt.disabled };
        return (
          <Element
            key={opt.value}
            ref={(node) => {
              if (node) buttonRefs.current[opt.value] = node;
              else delete buttonRefs.current[opt.value];
            }}
            {...elementProps}
            aria-label={opt.title}
            title={opt.title}
            onClick={() => onChange?.(opt.value)}
            className={`relative z-10 shrink-0 whitespace-nowrap max-sm:inline-flex max-sm:min-h-10 max-sm:items-center max-sm:justify-center rounded-[var(--radius-card)] font-medium transition-colors ${block ? "flex-1 flex items-center justify-center" : ""} ${SIZES[size]} ${
              active
                ? `font-semibold text-brand${thumb ? "" : " bg-surface-card-elevated"}`
                : "text-muted hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-muted"
            }`}
          >
            {opt.label}
          </Element>
        );
      })}
    </div>
  );
}
