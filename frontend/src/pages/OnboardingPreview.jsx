import { useState } from "react";
import { Link } from "react-router-dom";
import { Eye, X } from "lucide-react";

import OnboardingView from "../components/onboarding/OnboardingView";

// Read-only replay of the first-run onboarding for signed-in users.
//
// PURE FRONTEND by design: this module must never import ../api, the
// portfolio context, or analytics. Choices only update local React state and
// explain what the real onboarding would do -- nothing is created, saved,
// tracked or sent. OnboardingPreview.test.jsx enforces this.

export const PREVIEW_EXIT_PATH = "/settings?section=preferences";

const OUTCOMES = Object.freeze({
  import: "Opens the CSV import. You see a preview of the file and nothing is saved until you confirm it.",
  demo: "Creates a clearly labelled sample portfolio and opens the dashboard so you can look around.",
  broker: "Creates an empty portfolio called “My portfolio” and opens Settings → Connections.",
  blank: "Creates an empty portfolio and opens the dashboard, ready for manual transactions.",
});

export default function OnboardingPreview() {
  const [selected, setSelected] = useState(null);

  const banner = (
    <div className="card flex flex-col gap-3 border border-brand/40 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <span className="w-9 h-9 shrink-0 rounded-xl bg-brand/10 text-brand flex items-center justify-center">
          <Eye size={18} aria-hidden="true" />
        </span>
        <div>
          <p className="font-semibold text-ink">Onboarding preview</p>
          <p className="text-xs leading-5 text-muted">
            You are replaying the welcome screen. Nothing you click here is saved, tracked or sent anywhere.
          </p>
        </div>
      </div>
      <Link
        to={PREVIEW_EXIT_PATH}
        className="inline-flex items-center justify-center gap-1.5 self-start rounded-full border border-surface-border px-4 py-2 min-h-11 md:min-h-0 text-sm font-medium text-ink hover:border-brand sm:self-auto"
      >
        <X size={14} aria-hidden="true" />
        Exit preview
      </Link>
    </div>
  );

  const notice = selected && (
    <div role="status" className="card border border-brand/30 text-sm">
      <p className="font-semibold text-ink">In the real onboarding</p>
      <p className="mt-1 text-muted">{OUTCOMES[selected]}</p>
      <p className="mt-2 text-xs text-muted">Preview only — nothing was created.</p>
    </div>
  );

  return (
    <OnboardingView
      onChoose={setSelected}
      onStartBlank={() => setSelected("blank")}
      banner={banner}
      notice={notice}
      selected={selected}
    />
  );
}
