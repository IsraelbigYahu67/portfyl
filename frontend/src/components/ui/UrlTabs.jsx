import { useEffect, useLayoutEffect, useRef, useState } from "react";

function toIdPart(value) {
  return String(value).trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
}

// Same liquid-pour timing as SegmentedControl (DESIGN.md, motion rules).
const LEADING = "0.28s cubic-bezier(0.34, 1.1, 0.64, 1)";
const TRAILING = "0.45s cubic-bezier(0.34, 1.1, 0.64, 1) 0.05s";

const SCROLL_FADE = "linear-gradient(to right, black 88%, transparent)";

export function UrlTabs({ ariaLabel, idPrefix = "url-tabs", items, value, onChange, className = "" }) {
  const rootRef = useRef(null);
  const refs = useRef(new Map());
  const previousIndex = useRef(-1);
  const [thumb, setThumb] = useState(null);
  // True while more tabs sit past the right edge of the scrolling row.
  const [moreRight, setMoreRight] = useState(false);
  const enabledItems = items.filter((item) => !item.disabled);
  const activeIndex = items.findIndex((item) => item.value === value);

  useLayoutEffect(() => {
    const root = rootRef.current;
    const button = refs.current.get(value);
    if (!root || !button) {
      setThumb(null);
      return undefined;
    }

    const measure = (animate) => {
      const next = {
        left: button.offsetLeft,
        right: root.scrollWidth - button.offsetLeft - button.offsetWidth,
        top: button.offsetTop,
        height: button.offsetHeight,
        direction: previousIndex.current <= activeIndex ? 1 : -1,
        animate,
      };
      setThumb((prev) =>
        prev && prev.left === next.left && prev.right === next.right && prev.top === next.top && prev.height === next.height
          ? prev
          : next
      );
      // Keep the selected tab visible when the row scrolls horizontally. The
      // row itself scrolls, never the page (also on first render, for deep links).
      const edge = button.offsetLeft + button.offsetWidth;
      if (button.offsetLeft < root.scrollLeft) root.scrollLeft = Math.max(0, button.offsetLeft - 8);
      else if (edge > root.scrollLeft + root.clientWidth) root.scrollLeft = edge - root.clientWidth + 8;
    };

    measure(previousIndex.current !== -1);
    previousIndex.current = activeIndex;

    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => measure(false));
    observer.observe(root);
    return () => observer.disconnect();
  }, [value, activeIndex, items]);

  // A fade on the right edge tells the user the last tab ("Ownership") is not
  // cut off, just further along the row.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    const update = () => setMoreRight(root.scrollWidth > root.clientWidth + 1 && root.scrollLeft + root.clientWidth < root.scrollWidth - 1);
    update();
    root.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      root.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [items]);

  const selectAndFocus = (item) => {
    if (!item || item.disabled) return;
    onChange(item.value);
    refs.current.get(item.value)?.focus();
  };

  const handleKeyDown = (event, currentValue) => {
    const currentIndex = enabledItems.findIndex((item) => item.value === currentValue);
    if (currentIndex < 0 || enabledItems.length === 0) return;

    let nextItem;
    if (event.key === "ArrowRight") {
      nextItem = enabledItems[(currentIndex + 1) % enabledItems.length];
    } else if (event.key === "ArrowLeft") {
      nextItem = enabledItems[(currentIndex - 1 + enabledItems.length) % enabledItems.length];
    } else if (event.key === "Home") {
      nextItem = enabledItems[0];
    } else if (event.key === "End") {
      nextItem = enabledItems[enabledItems.length - 1];
    } else {
      return;
    }

    event.preventDefault();
    selectAndFocus(nextItem);
  };

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
      aria-label={ariaLabel}
      className={`segmented relative flex max-w-full min-w-0 gap-0.5 overflow-x-auto rounded-[var(--radius-card)] bg-surface-hover p-0.5 sm:inline-flex ${className}`.trim()}
      role="tablist"
      data-more-right={moreRight ? "true" : "false"}
      style={moreRight ? { maskImage: SCROLL_FADE, WebkitMaskImage: SCROLL_FADE } : undefined}
    >
      {thumb && (
        <span
          aria-hidden="true"
          className="segmented-thumb pointer-events-none absolute rounded-[var(--radius-card)] bg-surface-card-elevated"
          style={thumbStyle}
        />
      )}
      {items.map((item) => {
        const selected = item.value === value;
        const idPart = toIdPart(item.value);
        return (
          <button
            key={item.value}
            ref={(node) => {
              if (node) refs.current.set(item.value, node);
              else refs.current.delete(item.value);
            }}
            id={`${idPrefix}-${idPart}-tab`}
            type="button"
            role="tab"
            aria-controls={item.panelId}
            aria-selected={selected}
            disabled={item.disabled}
            tabIndex={selected && !item.disabled ? 0 : -1}
            onClick={() => selectAndFocus(item)}
            onKeyDown={(event) => handleKeyDown(event, item.value)}
            className={`relative z-10 shrink-0 whitespace-nowrap rounded-[var(--radius-card)] px-3 py-1.5 max-sm:min-h-10 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ${
              selected
                ? `font-semibold text-brand${thumb ? "" : " bg-surface-card-elevated"}`
                : "text-muted hover:text-ink"
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
