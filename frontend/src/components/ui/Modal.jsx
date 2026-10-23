import { createPortal } from "react-dom";
import { useFocusTrap } from "../../hooks/useFocusTrap";

// Accessible dialog: overlay + `.card` panel with role="dialog", focus trapped
// while open and restored to the opener on close (useFocusTrap). Escape or a
// click on the backdrop calls `onClose`. Rendered in a portal so transformed
// ancestors (animate-fade-up widgets) cannot trap `position: fixed`.
// Motion is opt-in via `motion-safe:`, so reduced motion gets no transition.
export function Modal({ open, onClose, titleId, initialFocusRef, className = "", children }) {
  const panelRef = useFocusTrap({ active: open, onEscape: onClose, initialFocusRef });

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4"
      style={{ backdropFilter: "blur(var(--blur-overlay))" }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`card w-full max-w-md max-h-[90vh] overflow-y-auto motion-safe:animate-fade-up ${className}`}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
