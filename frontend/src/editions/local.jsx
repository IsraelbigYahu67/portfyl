import { FileText, Filter } from "lucide-react";
import { lazy } from "react";
import { fetchLocalTaxReport } from "./localApi";

const loadTaxReport = () => import("../pages/TaxReport");
const loadScreener = () => import("../pages/Screener");
export const EDITION_ROUTES = Object.freeze([
  { path: "/tax-report", capability: "tax_report", Component: lazy(loadTaxReport), preload: loadTaxReport },
  { path: "/screener", capability: "screener", Component: lazy(loadScreener), preload: loadScreener },
]);

export const EDITION_NAVIGATION = Object.freeze([
  { to: "/tax-report", label: "Tax Report", icon: FileText, capability: "tax_report", preload: loadTaxReport },
  { to: "/screener", label: "Screener", icon: Filter, capability: "screener", preload: loadScreener },
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
