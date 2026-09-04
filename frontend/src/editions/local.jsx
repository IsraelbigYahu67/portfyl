import { FileText, Filter } from "lucide-react";
import TaxReport from "../pages/TaxReport";
import Screener from "../pages/Screener";

export const EDITION_ROUTES = Object.freeze([
  { path: "/tax-report", capability: "tax_report", Component: TaxReport },
  { path: "/screener", capability: "screener", Component: Screener },
]);

export const EDITION_NAVIGATION = Object.freeze([
  { to: "/tax-report", label: "Tax Report", icon: FileText, capability: "tax_report" },
  { to: "/screener", label: "Screener", icon: Filter, capability: "screener" },
]);

export function EditionShell() {
  return null;
}
