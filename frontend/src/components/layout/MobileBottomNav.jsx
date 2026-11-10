import { matchPath, useLocation } from "react-router-dom";
import { useT } from "../../i18n/I18nProvider";
import { useBottomNavPaths } from "../../lib/bottomNavPrefs";
import BottomNavBar, { MORE_KEY } from "./BottomNavBar";
import { useNavGroups } from "./NavGroupsContext";
import { resolveBottomNavItems } from "./navigation";

// The page whose route matches `pathname`, or "More" when it is not in the bar
// (or the drawer is open). "/" only matches exactly, every other page by prefix.
export function activeBarKey(items, pathname, drawerOpen = false) {
  if (drawerOpen) return MORE_KEY;
  const match = items.find(({ to }) => matchPath({ path: to, end: false }, pathname) && (to !== "/" || pathname === "/"));
  return match ? match.to : MORE_KEY;
}

// The pages in the bar for this user and edition (their pick from Settings >
// Preferences, the default four otherwise).
export function useBottomNavItems() {
  const groups = useNavGroups();
  const { paths } = useBottomNavPaths();
  return resolveBottomNavItems(groups, paths);
}

// Thumb-reach navigation for phones (DESIGN.md section 8): the pages the user
// picked (four by default) plus "More", which opens the full drawer. Hidden from
// `lg` up, where the sidebar takes over. Opaque on purpose so page text never
// shows through.
export default function MobileBottomNav({ open = false, onOpenMenu, onNavigate }) {
  const t = useT();
  const { pathname } = useLocation();
  const items = useBottomNavItems();

  return (
    <nav aria-label={t("Main")} className="app-bottomnav lg:hidden fixed inset-x-0 bottom-0 z-40 border-t border-hairline">
      <BottomNavBar
        items={items}
        activeKey={activeBarKey(items, pathname, open)}
        moreOpen={open}
        onOpenMenu={onOpenMenu}
        onNavigate={onNavigate}
      />
    </nav>
  );
}
