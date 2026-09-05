import { Layers3 } from "lucide-react";
import Pricing from "../pages/Pricing";
import UpgradePrompt from "../components/UpgradePrompt";

// Plan comparison is cloud-only. It is static until a payment provider is
// deliberately implemented; the local edition does not advertise SaaS tiers.
export const EDITION_ROUTES = Object.freeze([
  { path: "/pricing", capability: "settings", Component: Pricing },
]);
export const EDITION_NAVIGATION = Object.freeze([
  { to: "/pricing", label: "Plans", icon: Layers3, capability: "settings" },
]);
export const EditionShell = UpgradePrompt;
