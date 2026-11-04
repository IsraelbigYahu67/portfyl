import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Eye, X } from "lucide-react";

import OnboardingView, { choiceHandler } from "../components/onboarding/OnboardingView";
import { useRouteFocusAnnouncer } from "../hooks/useRouteFocusAnnouncer";
import { findSupportedBroker } from "../lib/onboardingBrokers";

// Read-only replay of the first-run onboarding for signed-in users.
//
// PURE FRONTEND by design: choices only update local React state and explain
// what the real onboarding would do -- no portfolio is created and nothing is
// saved. OnboardingPreview.test.jsx enforces it: it walks the whole import
// graph from this file (static, side-effect, re-export and dynamic imports,
// transitively) and fails if it reaches the API client (src/api), the portfolio
// context (src/App), anything under src/analytics, an axios / firebase /
// @sentry package, or a specifier it cannot resolve (such as a Vite alias).

export const PREVIEW_EXIT_PATH = "/settings?section=preferences";

// One outcome per ONBOARDING_CHOICE_KEYS entry, plus "blank" for the separate
// "Start with a blank portfolio" link (OnboardingPreview.test.jsx checks this).
// Each takes the broker picked in step 1 (null on the unsupported screen).
export const OUTCOMES = Object.freeze({
  import: (broker) => (broker?.fileKind
    ? `Opens the import for your ${broker.name} ${broker.fileKind} file. You see a preview of the file and nothing is saved until you confirm it.`
    : "Opens the import for a Portfyl CSV. You see a preview of the file and nothing is saved until you confirm it."),
  demo: () => "Creates a clearly labelled sample portfolio and opens the dashboard so you can look around.",
  broker: (broker) => `Creates an empty portfolio called “${broker?.name ?? "My portfolio"}” and opens Settings → Connections${broker ? ` with ${broker.name} first` : ""}.`,
  blank: () => "Creates an empty portfolio and opens the dashboard, ready for manual transactions.",
});

export default function OnboardingPreview() {
  const [selected, setSelected] = useState(null);
  const [brokerKey, setBrokerKey] = useState(null);
  const [unsupportedName, setUnsupportedName] = useState(null);
  const broker = findSupportedBroker(brokerKey);
  // A new step starts with nothing chosen.
  const changeBroker = (key) => { setSelected(null); setBrokerKey(key); };
  const changeUnsupported = (name) => { setSelected(null); setUnsupportedName(name); };
  const mainRef = useRef(null);
  // The preview renders outside AppShell, so it announces itself: entering it
  // moves focus to its h1 instead of leaving it on <body>.
  useRouteFocusAnnouncer(mainRef);

  const choose = Object.fromEntries(Object.keys(OUTCOMES).map((key) => [key, () => setSelected(key)]));

  const banner = (
    <div className="card flex flex-col gap-3 border border-brand/40 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <span className="w-9 h-9 shrink-0 rounded-xl bg-brand/10 text-brand flex items-center justify-center">
          <Eye size={18} aria-hidden="true" />
        </span>
        <div>
          <p className="font-semibold text-ink">Onboarding preview</p>
          <p className="text-xs leading-5 text-muted">
            You are replaying the welcome screen. Nothing you click here creates a portfolio or saves anything.
          </p>
        </div>
      </div>
      {/* replace: browser Back from Settings must not return into the preview. */}
      <Link
        to={PREVIEW_EXIT_PATH}
        replace
        className="btn-ghost inline-flex items-center justify-center gap-1.5 self-start min-h-11 md:min-h-0 text-sm font-medium sm:self-auto"
      >
        <X size={14} aria-hidden="true" />
        Exit preview
      </Link>
    </div>
  );

  // The view mounts this live region with each step that has choices (step 2
  // and the unsupported screen), before anything is chosen, and only its
  // content changes, so screen readers announce the first choice too. Empty,
  // it is a zero-height block whose margins collapse into its neighbours' gap.
  const notice = (
    <div role="status">
      {selected && (
        <div className="card border border-brand/30 text-sm">
          <p className="font-semibold text-ink">In the real onboarding</p>
          <p className="mt-1 text-muted">{OUTCOMES[selected](broker)}</p>
          <p className="mt-2 text-xs text-muted">Preview only — nothing was created.</p>
        </div>
      )}
    </div>
  );

  return (
    <OnboardingView
      mainRef={mainRef}
      brokerKey={brokerKey}
      onBrokerChange={changeBroker}
      unsupportedName={unsupportedName}
      onUnsupportedChange={changeUnsupported}
      onChoose={(key) => choiceHandler(choose, key)()}
      onStartBlank={choose.blank}
      banner={banner}
      notice={notice}
      selected={selected}
    />
  );
}
