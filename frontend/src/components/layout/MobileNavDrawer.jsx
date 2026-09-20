import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { preloadRoute } from "./navigation";

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

export default function MobileNavDrawer({ groups, open, onClose }) {
  const { pathname } = useLocation();
  const previousPathnameRef = useRef(pathname);
  const restoreFocusRef = useRef(true);
  const containerRef = useFocusTrap({ active: open, onEscape: onClose, restoreFocusRef });

  useEffect(() => {
    if (open) restoreFocusRef.current = true;
  }, [open]);

  useEffect(() => {
    const routeChanged = previousPathnameRef.current !== pathname;
    previousPathnameRef.current = pathname;
    if (routeChanged && open) {
      restoreFocusRef.current = false;
      onClose();
    }
  }, [pathname, open, onClose]);

  if (!open) return null;

  const transitionClass = prefersReducedMotion()
    ? ""
    : "transition-transform duration-200 ease-out";

  return (
    <div
      data-testid="mobile-nav-backdrop"
      className="lg:hidden fixed inset-0 z-[70] bg-black/30"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={containerRef}
        id="mobile-nav-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        className={`h-full w-[280px] max-w-[85vw] bg-surface-card border-r border-hairline overflow-y-auto ${transitionClass}`}
      >
        <div className="flex items-center justify-between px-4 py-2 border-b border-hairline">
          <span className="font-display font-bold text-[15px] text-ink">Navigation</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation menu"
            className="w-11 h-11 inline-flex items-center justify-center rounded-lg text-muted hover:text-ink hover:bg-surface-hover"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="Primary" className="px-2.5 py-3 space-y-4">
          {groups.map((group) => {
            const headingId = `mobile-nav-${group.id}`;
            return (
              <section key={group.id} aria-labelledby={headingId}>
                <h2 id={headingId} className="data-label px-3 pb-1">
                  {group.label}
                </h2>
                <div className="space-y-0.5">
                  {group.items.map(({ to, label, icon: Icon, preload }) => (
                    <NavLink
                      key={to}
                      to={to}
                      onMouseEnter={() => preloadRoute(preload)}
                      onFocus={() => preloadRoute(preload)}
                      end={to === "/"}
                      className={({ isActive }) => (
                        `min-h-11 flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                          isActive
                            ? "font-semibold text-brand bg-[var(--sidebar-active)]"
                            : "text-muted hover:text-ink hover:bg-surface-hover"
                        }`
                      )}
                    >
                      <Icon size={17} aria-hidden="true" />
                      {label}
                    </NavLink>
                  ))}
                </div>
              </section>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
