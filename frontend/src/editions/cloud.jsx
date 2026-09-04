import { CreditCard } from "lucide-react";
import Pricing from "../pages/Pricing";
import UpgradePrompt from "../components/UpgradePrompt";

// Cloud billing code is imported only by the cloud manifest. The local bundle
// therefore has no pricing, trial, checkout, or subscription-management UI.
export const EDITION_ROUTES = Object.freeze([
  { path: "/pricing", capability: "settings", Component: Pricing },
]);
export const EDITION_NAVIGATION = Object.freeze([
  { to: "/pricing", label: "Plan & Billing", icon: CreditCard, capability: "settings" },
]);
export const EditionShell = UpgradePrompt;
