import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";

const CLOSE_MS = 160;
const GAP = 6;
const MAX_H = 280;

/**
 * Portfyl dropdown (replaces the native <select>).
 * options: [{ value, label, lang? }]; onChange receives the chosen value.
 * The list opens with a soft pop and each option fades in one after another.
 * Focus stays on the trigger (aria-activedescendant); no ring on mouse/touch.
 */
export default function Select({
  value,
  onChange,
  options,
  id,
  className = "",
  menuClassName = "",
  disabled = false,
  "aria-label": ariaLabel,
  title,
}) {
  const reactId = useId();
  const listId = `${reactId}-list`;
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const typeahead = useRef({ text: "", timer: null });
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState(null);

  const selectedIndex = Math.max(0, options.findIndex((o) => String(o.value) === String(value)));
  const selected = options.find((o) => String(o.value) === String(value));

  const place = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const below = window.innerHeight - r.bottom - GAP - 8;
    const above = r.top - GAP - 8;
    const wanted = Math.min(MAX_H, options.length * 40 + 12);
    const up = below < wanted && above > below;
    const maxHeight = Math.max(120, Math.min(MAX_H, up ? above : below));
    setPos({
      left: Math.max(8, Math.min(r.left, window.innerWidth - Math.max(r.width, 160) - 8)),
      width: r.width,
      top: up ? undefined : r.bottom + GAP,
      bottom: up ? window.innerHeight - r.top + GAP : undefined,
      maxHeight,
      up,
    });
  }, [options.length]);

  const openMenu = () => {
    if (disabled) return;
    place();
    setActive(selectedIndex);
    setMounted(true);
    requestAnimationFrame(() => setOpen(true));
  };
  const closeMenu = useCallback(() => {
    setOpen(false);
    window.setTimeout(() => setMounted(false), CLOSE_MS);
  }, []);
  const choose = (index) => {
    const opt = options[index];
    if (opt) onChange?.(opt.value);
    closeMenu();
    triggerRef.current?.focus({ preventScroll: true });
  };

  useLayoutEffect(() => {
    if (!mounted) return undefined;
    place();
    const reposition = () => place();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [mounted, place]);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (triggerRef.current?.contains(e.target) || menuRef.current?.contains(e.target)) return;
      closeMenu();
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open, closeMenu]);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [open, active]);

  useEffect(() => () => window.clearTimeout(typeahead.current.timer), []);

  const onKeyDown = (e) => {
    if (disabled) return;
    const last = options.length - 1;
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        openMenu();
      }
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeMenu();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(last, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(last);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Tab") {
      closeMenu();
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
      const ta = typeahead.current;
      window.clearTimeout(ta.timer);
      ta.text += e.key.toLowerCase();
      ta.timer = window.setTimeout(() => { ta.text = ""; }, 600);
      const hit = options.findIndex((o) => String(o.label).toLowerCase().startsWith(ta.text));
      if (hit >= 0) setActive(hit);
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={mounted ? listId : undefined}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        aria-label={ariaLabel}
        title={title}
        disabled={disabled}
        data-value={value ?? ""}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={onKeyDown}
        className={`select-trigger ${className}`}
      >
        <span className="min-w-0 flex-1 truncate text-left" lang={selected?.lang}>{selected ? selected.label : ""}</span>
        <ChevronDown size={16} aria-hidden="true" className={`select-chevron shrink-0 ${open ? "is-open" : ""}`} />
      </button>
      {mounted && pos && createPortal(
        <ul
          ref={menuRef}
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          data-open={open ? "true" : "false"}
          data-up={pos.up ? "true" : "false"}
          className={`select-menu ${menuClassName}`}
          style={{ left: pos.left, minWidth: pos.width, top: pos.top, bottom: pos.bottom, maxHeight: pos.maxHeight }}
        >
          {options.map((o, i) => {
            const isSel = String(o.value) === String(value);
            return (
              <li
                key={String(o.value)}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={isSel}
                data-index={i}
                data-value={String(o.value)}
                data-active={i === active ? "true" : undefined}
                lang={o.lang}
                className="select-option"
                style={{ "--i": Math.min(i, 12) }}
                onPointerEnter={() => setActive(i)}
                onPointerDown={(e) => e.preventDefault()}
                onClick={() => choose(i)}
              >
                <span className="min-w-0 flex-1 truncate">{o.label}</span>
                {isSel && <Check size={15} aria-hidden="true" className="shrink-0" />}
              </li>
            );
          })}
        </ul>,
        document.body,
      )}
    </>
  );
}
