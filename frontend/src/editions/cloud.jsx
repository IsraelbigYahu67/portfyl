import { Layers3 } from "lucide-react";
import { lazy } from "react";
import { fetchTestPlan } from "../api";
import UpgradePrompt from "../components/UpgradePrompt";

// Plan comparison is cloud-only. It is static until a payment provider is
// deliberately implemented; the local edition does not advertise SaaS tiers.
const loadPricing = () => import("../pages/Pricing");
export const EDITION_ROUTES = Object.freeze([
  { path: "/pricing", capability: "settings", Component: lazy(loadPricing), preload: loadPricing },
]);
export const EDITION_NAVIGATION = Object.freeze([
  { to: "/pricing", label: "Plans", icon: Layers3, capability: "settings", preload: loadPricing },
]);
export const EditionShell = UpgradePrompt;

// The desktop-side mobile preview exists only in the local edition.
export const EditionAppFrame = ({ children }) => children;
export const EditionViewModeSetting = () => null;

// Cloud has no Tax Report, so there is no local tax-completeness signal to
// surface. Resolving null keeps the Dashboard's edition hook symmetric without
// importing any local-only API module into the cloud bundle.
export const fetchEditionDashboardSignals = async () => ({ taxReport: null });

// /api/capabilities lists what the cloud edition offers at all; the
// workspace's plan decides which of those it may use right now.
export const fetchEditionPlanCapabilities = async () => (await fetchTestPlan()).capabilities;
