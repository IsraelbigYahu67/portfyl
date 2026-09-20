import {
  Activity,
  ArrowLeftRight,
  Bot,
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
    id: "assistant",
    label: "Assistant",
    items: [{ to: "/assistant", label: "AI Assistant", icon: Bot }],
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

export const EDITION_ENTRY_GROUP = Object.freeze({
  "/tax-report": "insights",
  "/screener": "research",
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
