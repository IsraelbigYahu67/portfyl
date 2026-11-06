import {
  Activity,
  ArrowLeftRight,
  CalendarDays,
  LayoutDashboard,
  PieChart,
  Search,
  Settings as SettingsIcon,
  Star,
  Upload,
  Wallet,
} from "lucide-react";
import { TRACKER_HOME } from "../../lib/routes";

export const NAV_GROUPS = Object.freeze([
  {
    id: "portfolio",
    label: "Portfolio",
    items: [
      { to: TRACKER_HOME, label: "Dashboard", icon: LayoutDashboard },
      { to: "/allocation", label: "Allocation", icon: PieChart },
      { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
      { to: "/cash", label: "Cash", icon: Wallet },
    ],
  },
  {
    id: "research",
    label: "Research",
    items: [
      { to: "/search", label: "Search", icon: Search },
      { to: "/watchlists", label: "Watchlists", icon: Star },
    ],
  },
  {
    id: "insights",
    label: "Insights",
    items: [
      { to: "/dividends", label: "Dividends", icon: CalendarDays },
      { to: "/analytics", label: "Analytics", icon: Activity },
    ],
  },
  {
    id: "system",
    label: "System",
    items: [
      { to: "/import", label: "Import", icon: Upload },
      { to: "/settings", label: "Settings", icon: SettingsIcon },
    ],
  },
]);

// Phone bottom bar (MobileBottomNav): the pages used most, in thumb reach.
// "Positions" is the Allocation page, which holds the holdings list. Every path
// also lives in NAV_GROUPS, so the drawer ("More") still lists the full set.
export const BOTTOM_NAV_ITEMS = Object.freeze([
  { to: TRACKER_HOME, label: "Dashboard", icon: LayoutDashboard },
  { to: "/allocation", label: "Positions", icon: PieChart },
  { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/dividends", label: "Dividends", icon: CalendarDays },
]);

export const EDITION_ENTRY_GROUP = Object.freeze({
  "/tax-report": "insights",
});

export const DEFAULT_EDITION_GROUP = "system";

export function preloadRoute(preload) {
  return Promise.resolve().then(() => preload?.()).catch(() => {});
}

export function buildNavGroups(editionEntries, capabilities, sharedRoutes = []) {
  const enabled = new Set(capabilities || []);
  const groups = NAV_GROUPS.map((group) => ({ ...group, items: group.items.map(item => {
    const preload = sharedRoutes.find(route => route.path === item.to)?.preload;
    return preload ? { ...item, preload } : { ...item };
  }) }));

  for (const entry of editionEntries || []) {
    if (!enabled.has(entry.capability)) continue;
    const groupId = EDITION_ENTRY_GROUP[entry.to] || DEFAULT_EDITION_GROUP;
    const group = groups.find((candidate) => candidate.id === groupId);
    if (group) group.items.push(entry);
  }

  return groups;
}
