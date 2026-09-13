import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

function isAvailable(element) {
  const style = window.getComputedStyle(element);
  return !element.hidden && style.display !== "none" && style.visibility !== "hidden";
}

export function useFocusTrap({ active, onEscape, initialFocusRef } = {}) {
  const containerRef = useRef(null);
  const previouslyFocusedRef = useRef(null);
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;

  useEffect(() => {
    if (!active) return undefined;

    previouslyFocusedRef.current = document.activeElement;
    const container = containerRef.current;
    const focusables = () => (
      container
        ? Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter(isAvailable)
        : []
    );

    (initialFocusRef?.current || focusables()[0])?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        if (onEscapeRef.current) {
          event.preventDefault();
          onEscapeRef.current();
        }
        return;
      }
      if (event.key !== "Tab") return;

      const items = focusables();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previouslyFocusedRef.current?.isConnected) {
        previouslyFocusedRef.current.focus();
      }
    };
  }, [active, initialFocusRef]);

  return containerRef;
}
