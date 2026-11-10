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
import { msg } from "../../i18n/I18nProvider";
import { TRACKER_HOME } from "../../lib/routes";

// Labels are English source text marked with msg(); the sidebar, drawer and
// bottom bar translate them with t(label) where they are drawn.

export const NAV_GROUPS = Object.freeze([
  {
    id: "portfolio",
    label: msg("Portfolio"),
    items: [
      { to: TRACKER_HOME, label: msg("Dashboard"), icon: LayoutDashboard },
      { to: "/allocation", label: msg("Allocation"), icon: PieChart },
      { to: "/transactions", label: msg("Transactions"), icon: ArrowLeftRight },
      { to: "/cash", label: msg("Cash"), icon: Wallet },
    ],
  },
  {
    id: "research",
    label: msg("Research"),
    items: [
      { to: "/search", label: msg("Search"), icon: Search },
      { to: "/watchlists", label: msg("Watchlists"), icon: Star },
    ],
  },
  {
    id: "insights",
    label: msg("Insights"),
    items: [
      { to: "/dividends", label: msg("Dividends"), icon: CalendarDays },
      { to: "/analytics", label: msg("Analytics"), icon: Activity },
    ],
  },
  {
    id: "system",
    label: msg("System"),
    items: [
      { to: "/import", label: msg("Import"), icon: Upload },
      { to: "/settings", label: msg("Settings"), icon: SettingsIcon },
    ],
  },
]);

// Phone bottom bar (MobileBottomNav): the pages used most, in thumb reach.
// "Positions" is the Allocation page, which holds the holdings list. Every path
// also lives in NAV_GROUPS, so the drawer ("More") still lists the full set.
// This is the DEFAULT bar; users pick their own in Settings > Preferences
// (see lib/bottomNavPrefs.js and resolveBottomNavItems below).
export const BOTTOM_NAV_ITEMS = Object.freeze([
  { to: TRACKER_HOME, label: msg("Dashboard"), icon: LayoutDashboard },
  { to: "/allocation", label: msg("Positions"), icon: PieChart },
  { to: "/transactions", label: msg("Transactions"), icon: ArrowLeftRight },
  { to: "/dividends", label: msg("Dividends"), icon: CalendarDays },
]);

// The bar calls the Allocation page "Positions"; everywhere else it is
// "Allocation".
const BAR_LABELS = Object.freeze({ "/allocation": msg("Positions") });

// Every page that may sit in the bar: the whole (edition-aware) navigation,
// flattened in sidebar order, with the bar's own labels.
export function bottomNavChoices(groups = NAV_GROUPS) {
  return groups
    .flatMap((group) => group.items)
    .map((item) => ({ ...item, label: BAR_LABELS[item.to] ?? item.label }));
}

// The items to draw in the bar for a stored list of paths, in navigation order
// so the bar looks the same wherever it is rendered. Unknown paths (a page this
// edition does not have) are dropped; if fewer than `min` remain, the default
// bar is used so the bar can never end up empty.
export function resolveBottomNavItems(groups, paths, { min = 2 } = {}) {
  const choices = bottomNavChoices(groups);
  const wanted = new Set(Array.isArray(paths) ? paths : []);
  const picked = choices.filter(({ to }) => wanted.has(to));
  if (picked.length >= min) return picked;
  const fallback = new Set(BOTTOM_NAV_ITEMS.map(({ to }) => to));
  return choices.filter(({ to }) => fallback.has(to));
}

// What "More" lists: the full nav minus the pages already in the bottom bar, so
// nothing appears twice on a phone. Groups left empty are dropped.
export function groupsWithoutBottomNav(groups, barItems = BOTTOM_NAV_ITEMS) {
  const inBar = new Set(barItems.map(({ to }) => to));
  return groups
    .map((group) => ({ ...group, items: group.items.filter(({ to }) => !inBar.has(to)) }))
    .filter((group) => group.items.length > 0);
}

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
