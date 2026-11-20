import UpgradePrompt from "../UpgradePrompt";
import TrialBanner from "./TrialBanner";

// The cloud edition's always-mounted chrome (see editions/cloud.jsx).
export default function CloudShell() {
  return (
    <>
      <TrialBanner />
      <UpgradePrompt />
    </>
  );
}
