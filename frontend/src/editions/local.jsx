import { FileText, Layers3 } from "lucide-react";
import { lazy } from "react";
import { fetchLocalTaxReport } from "./localApi";

const loadTaxReport = () => import("../pages/TaxReport");
const loadPricing = () => import("../pages/Pricing");
// Local has no plans and no /api/test-plans route, so the cloud plan
// comparison is shown read-only for reference.
const ReadOnlyPricing = lazy(() => loadPricing().then(({ default: Pricing }) => ({
  default: function LocalPricing() {
    return <Pricing planSwitching={false} />;
  },
})));
export const EDITION_ROUTES = Object.freeze([
  { path: "/tax-report", capability: "tax_report", Component: lazy(loadTaxReport), preload: loadTaxReport },
  { path: "/pricing", capability: "settings", Component: ReadOnlyPricing, preload: loadPricing },
]);

export const EDITION_NAVIGATION = Object.freeze([
  { to: "/tax-report", label: "Tax Report", icon: FileText, capability: "tax_report", preload: loadTaxReport },
  { to: "/pricing", label: "Plans", icon: Layers3, capability: "settings", preload: loadPricing },
]);

export const fetchEditionDashboardSignals = async () => ({
  taxReport: await fetchLocalTaxReport(),
});

// The local edition has no plans (it always resolves to Pro), so nothing
// narrows the capabilities /api/capabilities returns.
export const fetchEditionPlanCapabilities = async () => null;

export function EditionShell() {
  return null;
}

// Mobile-layout preview on desktop is a local-only convenience; cloud's
// manifest supplies pass-through no-ops so it never ships in that bundle.
export { MobilePreviewFrame as EditionAppFrame, ViewModeSetting as EditionViewModeSetting } from "./viewMode";
