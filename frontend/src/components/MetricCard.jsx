import { useCallback, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import SpotlightCard from "./reactbits/SpotlightCard";
import { useCountUp } from "../hooks/useCountUp";

const TOOLTIP_GAP = 8;
const VIEWPORT_PADDING = 12;

function tooltipPosition(trigger, tooltip) {
  const maxLeft = Math.max(VIEWPORT_PADDING, window.innerWidth - VIEWPORT_PADDING - tooltip.width);
  const left = Math.min(
    Math.max(trigger.left + trigger.width / 2 - tooltip.width / 2, VIEWPORT_PADDING),
    maxLeft
  );

  const below = trigger.bottom + TOOLTIP_GAP;
  const above = trigger.top - TOOLTIP_GAP - tooltip.height;
  const maxTop = Math.max(VIEWPORT_PADDING, window.innerHeight - VIEWPORT_PADDING - tooltip.height);
  const preferredTop = below + tooltip.height <= window.innerHeight - VIEWPORT_PADDING
    ? below
    : above >= VIEWPORT_PADDING
      ? above
      : below;

  return {
    left,
    top: Math.min(Math.max(preferredTop, VIEWPORT_PADDING), maxTop),
  };
}

function InfoIcon({ info }) {
  const triggerRef = useRef(null);
  const tooltipRef = useRef(null);
  const tooltipId = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [position, setPosition] = useState(null);
  const visible = hovered || focused;

  const updatePosition = useCallback(() => {
    if (!triggerRef.current || !tooltipRef.current) return;
    setPosition(tooltipPosition(
      triggerRef.current.getBoundingClientRect(),
      tooltipRef.current.getBoundingClientRect()
    ));
  }, []);

  useLayoutEffect(() => {
    if (!visible) return;
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [visible, updatePosition]);

  if (!info) return null;
  return (
    <span
      className="relative inline-flex items-center"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-label={`What is ${info.title}?`}
        aria-describedby={visible ? tooltipId : undefined}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        className="relative inline-flex text-muted hover:text-ink cursor-help transition-colors before:absolute before:-inset-4 before:content-[''] sm:before:-inset-2"
      >
        <Info size={12} />
      </button>
      {visible && createPortal(
        <span
          ref={tooltipRef}
          id={tooltipId}
          role="tooltip"
          className="pointer-events-none w-72 max-w-[calc(100vw-1.5rem)] max-h-[calc(100vh-1.5rem)] overflow-y-auto
                     bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 shadow-[var(--shadow-ambient)]
                     text-xs leading-relaxed text-muted normal-case tracking-normal font-normal"
          style={{
            position: "fixed",
            zIndex: 2147483647,
            left: position?.left ?? 0,
            top: position?.top ?? 0,
            visibility: position ? "visible" : "hidden",
          }}
        >
          <span className="block font-semibold text-ink mb-1">{info.title}</span>
          <span className="block text-muted">{info.what}</span>
          {info.formula && (
            <span className="block mt-1.5 pt-1.5 border-t border-hairline font-mono text-xs text-brand">
              {info.formula}
            </span>
          )}
          {info.note && (
            <span className="block mt-1 text-xs text-muted italic">{info.note}</span>
          )}
        </span>,
        document.body
      )}
    </span>
  );
}

// `value` is normally a pre-formatted string (every current caller already
// formats via lib/format.js before passing it in). Passing a raw number
// AND countUp opts into a count-up animation -- additive, backward compatible.
function MetricValue({ value, countUp }) {
  const isNumber = countUp && typeof value === "number" && Number.isFinite(value);
  const animated = useCountUp(isNumber ? value : 0, { enabled: isNumber });
  return isNumber ? animated.toLocaleString("en-US", { maximumFractionDigits: 0 }) : value;
}

export default function MetricCard({ icon: Icon, label, value, sub, positive, negative, loading, info, countUp = false }) {
  const subColor = positive ? "text-gain" : negative ? "text-loss" : "text-muted";

  return (
    <SpotlightCard className="card pop-tile !bg-surface-card-elevated relative flex flex-col gap-1.5 min-w-0">
      {Icon && (
        <span className="absolute top-4 right-4 grid place-items-center w-7 h-7 rounded-lg bg-brand/10 text-brand">
          <Icon size={14} />
        </span>
      )}
      <span className="eyebrow flex items-center gap-1.5">
        {label}
        <InfoIcon info={info} />
      </span>
      {loading ? (
        <div className="h-8 w-28 bg-surface-hover rounded animate-pulse mt-1" />
      ) : (
        <span className="financial-headline text-2xl font-display font-bold tabular-nums tracking-tight [overflow-wrap:anywhere]">
          <MetricValue value={value} countUp={countUp} />
        </span>
      )}
      {sub && !loading && <span className={`text-[13px] font-semibold tabular-nums ${subColor}`}>{sub}</span>}
    </SpotlightCard>
  );
}

export { InfoIcon };
