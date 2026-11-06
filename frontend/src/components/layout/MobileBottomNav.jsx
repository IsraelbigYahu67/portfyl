import { Menu } from "lucide-react";
import { NavLink, matchPath, useLocation } from "react-router-dom";
import { BOTTOM_NAV_ITEMS } from "./navigation";

// Thumb-reach navigation for phones (DESIGN.md section 8): the four pages used
// most plus "More", which opens the full drawer. Hidden from `lg` up, where the
// sidebar takes over. Opaque on purpose so page text never shows through.
export default function MobileBottomNav({ open = false, onOpenMenu }) {
  const { pathname } = useLocation();
  const onPrimary = BOTTOM_NAV_ITEMS.some(({ to }) => matchPath({ path: to, end: false }, pathname) && (to !== "/" || pathname === "/"));
  const moreActive = open || !onPrimary;

  const itemClass = (active) =>
    `flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 rounded-2xl px-1 text-xs font-semibold transition-colors ${
      active ? "text-brand" : "text-muted hover:text-ink"
    }`;

  return (
    <nav aria-label="Main" className="app-bottomnav lg:hidden fixed inset-x-0 bottom-0 z-40 border-t border-hairline">
      <div className="mx-auto flex max-w-xl items-stretch gap-1 px-2 pt-1.5 pb-1.5">
        {BOTTOM_NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => itemClass(isActive)}>
            <Icon size={20} aria-hidden="true" />
            <span className="max-w-full truncate">{label}</span>
          </NavLink>
        ))}
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label="More, open navigation menu"
          aria-expanded={open}
          aria-controls="mobile-nav-drawer"
          aria-haspopup="dialog"
          className={itemClass(moreActive)}
        >
          <Menu size={20} aria-hidden="true" />
          <span>More</span>
        </button>
      </div>
    </nav>
  );
}
