import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useFocusTrap } from "../../hooks/useFocusTrap";

const DURATION = 320;
const EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)";

function prefersReducedMotion() {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

// The transform that shrinks the dialog panel back onto the element it came from.
function coverTransform(origin, panel) {
  const dx = origin.left - panel.left;
  const dy = origin.top - panel.top;
  return `translate(${dx}px, ${dy}px) scale(${origin.width / panel.width}, ${origin.height / panel.height})`;
}

// Modal that zooms out of (and back into) the element `getOrigin()` returns,
// so an expanded widget visibly grows from its dashboard card. Rendered in a
// portal: dashboard widgets sit inside transformed (animate-fade-up)
// ancestors, which would otherwise trap `position: fixed`.
export default function ZoomDialog({ open, onClose, getOrigin, labelledBy, className = "", children }) {
  const [mounted, setMounted] = useState(open);
  if (open && !mounted) setMounted(true);
  const panelRef = useFocusTrap({ active: open && mounted, onEscape: onClose });
  const backdropRef = useRef(null);

  useLayoutEffect(() => {
    const panel = panelRef.current;
    const backdrop = backdropRef.current;
    if (!mounted || !panel || !backdrop) return undefined;

    // Measure the panel at rest, even if a previous animation is mid-flight.
    panel.style.transition = "none";
    panel.style.transform = "";
    const target = panel.getBoundingClientRect();
    const origin = getOrigin?.()?.getBoundingClientRect();
    const animate = origin && origin.width > 0 && target.width > 0 && !prefersReducedMotion();

    if (open) {
      if (!animate) return undefined;
      panel.style.transformOrigin = "top left";
      panel.style.transform = coverTransform(origin, target);
      panel.style.opacity = "0.4";
      backdrop.style.transition = "none";
      backdrop.style.opacity = "0";
      // Forcing a reflow commits the start frame, so the styles below
      // transition from it instead of jumping straight to the end state.
      panel.getBoundingClientRect();
      panel.style.transition = `transform ${DURATION}ms ${EASE}, opacity ${DURATION}ms ease`;
      panel.style.transform = "";
      panel.style.opacity = "";
      backdrop.style.transition = `opacity ${DURATION}ms ease`;
      backdrop.style.opacity = "";
      return undefined;
    }

    if (!animate) {
      setMounted(false);
      return undefined;
    }
    panel.getBoundingClientRect();
    panel.style.transformOrigin = "top left";
    panel.style.transition = `transform ${DURATION}ms ${EASE}, opacity ${DURATION}ms ease`;
    panel.style.transform = coverTransform(origin, target);
    panel.style.opacity = "0";
    backdrop.style.transition = `opacity ${DURATION}ms ease`;
    backdrop.style.opacity = "0";
    const timer = setTimeout(() => setMounted(false), DURATION);
    return () => clearTimeout(timer);
    // getOrigin is read at animation time only; re-running on its identity
    // would restart the animation on every parent render.
  }, [open, mounted]);

  if (!mounted) return null;

  return createPortal(
    <div
      ref={backdropRef}
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4"
      style={{ backdropFilter: "blur(var(--blur-overlay))" }}
      onMouseDown={(event) => {
        if (open && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className={`card w-full max-h-[85dvh] flex flex-col ${className}`}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
