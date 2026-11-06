import { Menu } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";

/**
 * The phone bottom bar itself, shared by the real bar (MobileBottomNav) and the
 * live preview in Settings > Preferences.
 *
 * Two kinds of motion, both in the SegmentedControl's "liquid" style
 * (DESIGN.md section 7):
 *  - the highlighted pill is one shared element that slides to the active item,
 *    its leading edge moving faster than the trailing edge;
 *  - when the user adds or removes a page, its slot grows from / shrinks to
 *    nothing while the neighbours flow over to make room, and the pill keeps up.
 * Nothing animates on first render. `prefers-reduced-motion` is handled
 * globally in index.css (transition-duration ~0).
 */
export const MORE_KEY = "more";

const LEADING = "0.28s cubic-bezier(0.34, 1.1, 0.64, 1)";
const TRAILING = "0.45s cubic-bezier(0.34, 1.1, 0.64, 1) 0.05s";
const SLOT_TRANSITION = "flex-grow 0.38s cubic-bezier(0.34, 1.1, 0.64, 1), opacity 0.24s ease";
const ITEM_TRANSITION = "transform 0.38s cubic-bezier(0.34, 1.1, 0.64, 1), color 0.15s ease";
// A little longer than SLOT_TRANSITION so a leaving slot is only unmounted once
// it has fully collapsed.
const EXIT_MS = 420;

/** Keeps leaving pages mounted (collapsing) until their exit animation is done.
 *  phase: "enter" = mounted collapsed, about to grow; "idle" = shown;
 *  "leave" = collapsing, about to be unmounted. */
function mergeSlots(prev, items) {
  const nextKeys = new Set(items.map((item) => item.to));
  const prevByKey = new Map(prev.map((slot) => [slot.key, slot]));
  const merged = items.map((item) => {
    const old = prevByKey.get(item.to);
    return old ? { ...old, item, phase: "idle" } : { key: item.to, item, phase: "enter" };
  });
  prev.forEach((slot, index) => {
    if (nextKeys.has(slot.key)) return;
    // Slot stays where it was: right after the nearest earlier slot still shown.
    let at = 0;
    for (let i = index - 1; i >= 0; i -= 1) {
      const found = merged.findIndex((candidate) => candidate.key === prev[i].key);
      if (found !== -1) {
        at = found + 1;
        break;
      }
    }
    merged.splice(at, 0, { ...slot, phase: "leave" });
  });
  return merged;
}

function useAnimatedSlots(items) {
  const [slots, setSlots] = useState(() =>
    items.map((item) => ({ key: item.to, item, phase: "idle" })),
  );
  const exitTimers = useRef(new Map());
  const signature = items.map((item) => item.to).join("|");

  useLayoutEffect(() => {
    setSlots((prev) => mergeSlots(prev, items));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `signature` is the content of `items`
  }, [signature]);

  // Mounted collapsed -> grow on the next frame (two rAFs so the collapsed
  // style is painted first and the transition has something to start from).
  const entering = slots.some((slot) => slot.phase === "enter");
  useEffect(() => {
    if (!entering) return undefined;
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => {
        setSlots((prev) => prev.map((slot) => (slot.phase === "enter" ? { ...slot, phase: "idle" } : slot)));
      });
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, [entering]);

  // Unmount leaving slots once collapsed; cancel if the page comes back.
  useEffect(() => {
    const timers = exitTimers.current;
    const leaving = new Set(slots.filter((slot) => slot.phase === "leave").map((slot) => slot.key));
    for (const key of leaving) {
      if (timers.has(key)) continue;
      timers.set(
        key,
        setTimeout(() => {
          timers.delete(key);
          setSlots((prev) => prev.filter((slot) => !(slot.key === key && slot.phase === "leave")));
        }, EXIT_MS),
      );
    }
    for (const [key, timer] of timers) {
      if (!leaving.has(key)) {
        clearTimeout(timer);
        timers.delete(key);
      }
    }
  }, [slots]);

  useEffect(() => {
    const timers = exitTimers.current;
    return () => timers.forEach((timer) => clearTimeout(timer));
  }, []);

  return slots;
}

function itemClass(active) {
  return `relative z-10 flex min-h-14 w-full flex-col items-center justify-center gap-0.5 rounded-2xl px-1 text-xs font-semibold ${
    active ? "text-brand" : "text-muted hover:text-ink"
  }`;
}

export default function BottomNavBar({
  items,
  activeKey,
  preview = false,
  onSelect,
  moreOpen = false,
  onOpenMenu,
}) {
  const slots = useAnimatedSlots(items);
  const rowRef = useRef(null);
  const elementRefs = useRef({});
  const previousKey = useRef(null);
  const [pill, setPill] = useState(null);

  const order = [...slots.map((slot) => slot.key), MORE_KEY];
  const orderSignature = order.join("|");
  const activeIndex = order.indexOf(activeKey);

  useLayoutEffect(() => {
    const row = rowRef.current;
    const element = elementRefs.current[activeKey];
    if (!row || !element) {
      setPill(null);
      return undefined;
    }
    const keyChanged = previousKey.current !== null && previousKey.current !== activeKey;
    const movedRight = previousKey.current === null || order.indexOf(previousKey.current) <= activeIndex;

    const measure = (animate) => {
      const next = {
        left: element.offsetLeft,
        right: row.clientWidth - element.offsetLeft - element.offsetWidth,
        top: element.offsetTop,
        height: element.offsetHeight,
        direction: movedRight ? 1 : -1,
        animate,
      };
      setPill((prev) =>
        prev && prev.left === next.left && prev.right === next.right && prev.top === next.top && prev.height === next.height
          ? prev
          : next,
      );
    };

    measure(keyChanged);
    previousKey.current = activeKey;

    // Slots change width while they grow or shrink: follow them frame by frame
    // (no transition on the pill for these, it is simply glued to its item).
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => measure(false));
    observer.observe(row);
    Object.values(elementRefs.current).forEach((node) => node && observer.observe(node));
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- order is covered by `orderSignature`
  }, [activeKey, orderSignature]);

  const pillStyle = pill && {
    left: pill.left,
    right: pill.right,
    top: pill.top,
    height: pill.height,
    transition: pill.animate
      ? `left ${pill.direction === 1 ? TRAILING : LEADING}, right ${pill.direction === 1 ? LEADING : TRAILING}, top 0.2s ease, height 0.2s ease`
      : "none",
  };

  const register = (key) => (node) => {
    if (node) elementRefs.current[key] = node;
    else delete elementRefs.current[key];
  };

  return (
    <div ref={rowRef} className="relative mx-auto flex max-w-xl items-stretch px-2 pt-1.5 pb-1.5">
      {pill && (
        <span
          aria-hidden="true"
          data-testid="bottomnav-pill"
          className="bottomnav-pill pointer-events-none absolute z-0 rounded-2xl bg-[var(--sidebar-active)]"
          style={pillStyle}
        />
      )}
      {slots.map(({ key, item, phase }) => {
        const { to, label, icon: Icon } = item;
        const shown = phase === "idle";
        const leaving = phase === "leave";
        const active = activeKey === to && !leaving;
        const content = (
          <>
            <Icon size={20} aria-hidden="true" />
            <span className="max-w-full truncate">{label}</span>
          </>
        );
        return (
          <div
            key={key}
            data-slot={key}
            data-phase={phase}
            className="min-w-0 px-0.5"
            style={{
              flexBasis: 0,
              flexGrow: shown ? 1 : 0,
              opacity: shown ? 1 : 0,
              transition: SLOT_TRANSITION,
              pointerEvents: leaving ? "none" : undefined,
            }}
            aria-hidden={leaving ? "true" : undefined}
            inert={leaving ? "" : undefined}
          >
            {preview ? (
              <div
                ref={register(key)}
                role="presentation"
                onClick={() => onSelect?.(to)}
                className={`${itemClass(active)} cursor-pointer`}
                style={{ transform: shown ? "scale(1)" : "scale(0.6)", transition: ITEM_TRANSITION }}
              >
                {content}
              </div>
            ) : (
              <NavLink
                ref={register(key)}
                to={to}
                end={to === "/"}
                tabIndex={leaving ? -1 : undefined}
                className={itemClass(active)}
                style={{ transform: shown ? "scale(1)" : "scale(0.6)", transition: ITEM_TRANSITION }}
              >
                {content}
              </NavLink>
            )}
          </div>
        );
      })}
      <div className="min-w-0 px-0.5" style={{ flex: "1 1 0%" }}>
        {preview ? (
          <div
            ref={register(MORE_KEY)}
            role="presentation"
            onClick={() => onSelect?.(MORE_KEY)}
            className={`${itemClass(activeKey === MORE_KEY)} cursor-pointer`}
            style={{ transition: ITEM_TRANSITION }}
          >
            <Menu size={20} aria-hidden="true" />
            <span>More</span>
          </div>
        ) : (
          <button
            ref={register(MORE_KEY)}
            type="button"
            onClick={onOpenMenu}
            aria-label="More, open navigation menu"
            aria-expanded={moreOpen}
            aria-controls="mobile-nav-drawer"
            aria-haspopup="dialog"
            className={itemClass(activeKey === MORE_KEY)}
            style={{ transition: ITEM_TRANSITION }}
          >
            <Menu size={20} aria-hidden="true" />
            <span>More</span>
          </button>
        )}
      </div>
    </div>
  );
}
