import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { useT } from "../../i18n/I18nProvider";
import AccountMenu from "../AccountMenu";
import { useBottomNavItems } from "./MobileBottomNav";
import { groupsWithoutBottomNav, preloadRoute } from "./navigation";

// Keep in step with .drawer-slide-out-right in index.css.
const DRAWER_EXIT_MS = 200;

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

export default function MobileNavDrawer({ groups, open, onClose }) {
  const t = useT();
  const { pathname } = useLocation();
  const previousPathnameRef = useRef(pathname);
  const restoreFocusRef = useRef(true);
  const containerRef = useFocusTrap({ active: open, onEscape: onClose, restoreFocusRef });
  const barItems = useBottomNavItems();

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

  // Stay mounted for the length of the slide-out so closing animates too.
  const [mounted, setMounted] = useState(open);
  useEffect(() => {
    if (open) {
      setMounted(true);
      return undefined;
    }
    if (prefersReducedMotion()) {
      setMounted(false);
      return undefined;
    }
    const timer = setTimeout(() => setMounted(false), DRAWER_EXIT_MS);
    return () => clearTimeout(timer);
  }, [open]);

  if (!open && !mounted) return null;

  const closing = !open;
  const reduced = prefersReducedMotion();
  const motionClass = reduced ? "" : closing ? "drawer-slide-out-right" : "drawer-slide-in-right";
  const backdropMotionClass = reduced ? "" : closing ? "drawer-backdrop-out" : "";

  // The backdrop covers the whole screen (so nothing shows undimmed around the
  // floating bottom bar) but sits at z-39, just under the bar's z-40: the bar
  // stays on top, visible and tappable. The bottom padding (AppShell's spacer
  // height) makes the panel end above the bar. It sits on the right edge, next
  // to the thumb.
  return (
    <div
      data-testid="mobile-nav-backdrop"
      className={`lg:hidden fixed inset-0 pb-[calc(4.75rem+env(safe-area-inset-bottom))] z-[39] flex justify-end bg-black/30 backdrop-blur-sm ${backdropMotionClass} ${closing ? "pointer-events-none" : ""}`}
      aria-hidden={closing ? "true" : undefined}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={containerRef}
        id="mobile-nav-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={t("Navigation")}
        className={`app-drawer flex h-full w-[280px] max-w-[85vw] flex-col border-l border-hairline overflow-y-auto ${motionClass}`}
      >
        <div className="flex items-center justify-between px-4 py-2 border-b border-hairline">
          <span className="font-display font-bold text-[15px] text-ink">{t("Navigation")}</span>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("Close navigation menu")}
            className="w-11 h-11 inline-flex items-center justify-center rounded-lg text-muted hover:text-ink hover:bg-surface-hover"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>
        <nav aria-label={t("Primary")} className="flex-1 px-2.5 py-3 space-y-4">
          {groupsWithoutBottomNav(groups, barItems).map((group) => {
            const headingId = `mobile-nav-${group.id}`;
            return (
              <section key={group.id} aria-labelledby={headingId}>
                <h2 id={headingId} className="data-label px-3 pb-1">
                  {t(group.label)}
                </h2>
                <div className="space-y-0.5">
                  {group.items.map(({ to, label, icon: Icon, preload }) => (
                    <NavLink
                      key={to}
                      to={to}
                      onMouseEnter={() => preloadRoute(preload)}
                      onFocus={() => preloadRoute(preload)}
                      end={to === "/"}
                      onClick={() => {
                        // A link to the page already open changes no route, so the
                        // effect above would not fire: close the drawer here.
                        if (to !== pathname) return;
                        restoreFocusRef.current = false;
                        onClose();
                      }}
                      className={({ isActive }) => (
                        `min-h-11 flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                          isActive
                            ? "font-semibold text-brand bg-[var(--sidebar-active)]"
                            : "text-muted hover:text-ink hover:bg-surface-hover"
                        }`
                      )}
                    >
                      <Icon size={17} aria-hidden="true" />
                      {t(label)}
                    </NavLink>
                  ))}
                </div>
              </section>
            );
          })}
        </nav>
        <div className="px-3 pb-4 pt-2">
          <AccountMenu />
        </div>
      </div>
    </div>
  );
}
