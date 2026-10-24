import { useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import AccountMenu from "../AccountMenu";
import PortfolioSwitcher from "../PortfolioSwitcher";
import { preloadRoute } from "./navigation";

// Same liquid-pour timing as SegmentedControl (DESIGN.md, motion rules).
const LEADING = "0.28s cubic-bezier(0.34, 1.1, 0.64, 1)";
const TRAILING = "0.45s cubic-bezier(0.34, 1.1, 0.64, 1) 0.05s";

export default function DesktopSidebar({ groups }) {
  const { pathname } = useLocation();
  const navRef = useRef(null);
  const previousTop = useRef(null);
  const [thumb, setThumb] = useState(null);

  useLayoutEffect(() => {
    const nav = navRef.current;
    const link = nav?.querySelector('a[aria-current="page"]');
    if (!nav || !link) {
      previousTop.current = null;
      setThumb(null);
      return undefined;
    }

    const measure = (animate) => {
      const next = {
        top: link.offsetTop,
        bottom: nav.scrollHeight - link.offsetTop - link.offsetHeight,
        left: link.offsetLeft,
        width: link.offsetWidth,
        // 1 = moving down (bottom edge leads), -1 = moving up (top edge leads).
        direction: previousTop.current === null || previousTop.current <= link.offsetTop ? 1 : -1,
        animate,
      };
      setThumb((prev) =>
        prev && prev.top === next.top && prev.bottom === next.bottom && prev.left === next.left && prev.width === next.width
          ? prev
          : next
      );
    };

    measure(previousTop.current !== null);
    previousTop.current = link.offsetTop;

    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => measure(false));
    observer.observe(nav);
    return () => observer.disconnect();
  }, [pathname, groups]);

  const thumbStyle = thumb && {
    top: thumb.top,
    bottom: thumb.bottom,
    left: thumb.left,
    width: thumb.width,
    transition: thumb.animate
      ? `top ${thumb.direction === 1 ? TRAILING : LEADING}, bottom ${thumb.direction === 1 ? LEADING : TRAILING}`
      : "none",
  };

  return (
    <aside
      className="app-sidebar w-[232px] h-full shrink-0 bg-surface-card border-r border-surface-border flex flex-col"
      style={{ boxShadow: "1px 0 0 var(--glass-border-alpha)" }}
    >
      <div className="flex items-center gap-2.5 px-[18px] py-4 border-b border-hairline">
        <img src="/portfyl-mark.svg" alt="Portfyl" className="w-11 h-11 object-contain" />
        <span className="font-display font-bold text-[17px] tracking-tight text-ink leading-tight">Portfyl</span>
      </div>

      <div className="px-3 pt-2">
        <PortfolioSwitcher />
      </div>

      <nav ref={navRef} aria-label="Primary" className="relative flex-1 min-h-0 px-2.5 py-2 space-y-3 overflow-y-auto">
        {thumb && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute rounded-lg bg-[var(--sidebar-active)] shadow-[inset_0_0_0_1px_var(--glass-border-alpha)]"
            style={thumbStyle}
          />
        )}
        {groups.map((group) => {
          const headingId = `desktop-nav-${group.id}`;
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
                      `relative z-10 flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                        isActive
                          ? `font-semibold text-brand${thumb ? "" : " bg-[var(--sidebar-active)] shadow-[inset_0_0_0_1px_var(--glass-border-alpha)]"}`
                          : "text-muted hover:text-ink hover:bg-surface-hover"
                      }`
                    )}
                  >
                    <Icon size={16} aria-hidden="true" />
                    {label}
                  </NavLink>
                ))}
              </div>
            </section>
          );
        })}
      </nav>

      <div className="mt-auto px-3 pb-2">
        <AccountMenu />
      </div>
    </aside>
  );
}
