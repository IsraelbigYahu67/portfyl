import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Eye, X } from "lucide-react";

import OnboardingView, { choiceHandler } from "../components/onboarding/OnboardingView";
import { useRouteFocusAnnouncer } from "../hooks/useRouteFocusAnnouncer";
import { findSupportedBroker } from "../lib/onboardingBrokers";
import { translate, useI18n, useT } from "../i18n/I18nProvider";
import { localCurrencyForLanguage, readStoredCurrency } from "../lib/displayCurrency";

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
// Each takes the broker picked in step 1 (null on the unsupported screen) and
// the translate function (English when left out).
const english = (text, vars) => translate(null, text, vars);
export const OUTCOMES = Object.freeze({
  import: (broker, t = english) => (broker?.fileKind
    ? t("Opens the import for your {broker} {fileKind} file. You see a preview of the file and nothing is saved until you confirm it.", { broker: broker.name, fileKind: broker.fileKind })
    : t("Opens the import for a Portfyl CSV. You see a preview of the file and nothing is saved until you confirm it.")),
  demo: (broker, t = english) => t("Creates a clearly labelled sample portfolio and opens the dashboard so you can look around."),
  broker: (broker, t = english) => (broker
    ? t("Creates an empty portfolio called “{broker}” and opens Settings → Connections with {broker} first.", { broker: broker.name })
    : t("Creates an empty portfolio called “{name}” and opens Settings → Connections.", { name: t("My portfolio") })),
  blank: (broker, t = english) => t("Creates an empty portfolio and opens the dashboard, ready for manual transactions."),
});

export default function OnboardingPreview() {
  const t = useT();
  // Local only: the preview may not reach the currency context in src/App.
  const { language } = useI18n();
  const [currency, setCurrency] = useState(() => readStoredCurrency() ?? localCurrencyForLanguage(language));
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
          <p className="font-semibold text-ink">{t("Onboarding preview")}</p>
          <p className="text-xs leading-5 text-muted">
            {t("You are replaying the welcome screen. Nothing you click here creates a portfolio. A language you pick does apply, as in Settings.")}
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
        {t("Exit preview")}
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
          <p className="font-semibold text-ink">{t("In the real onboarding")}</p>
          <p className="mt-1 text-muted">{OUTCOMES[selected](broker, t)}</p>
          <p className="mt-2 text-xs text-muted">{t("Preview only — nothing was created.")}</p>
        </div>
      )}
    </div>
  );

  return (
    <OnboardingView
      mainRef={mainRef}
      currency={currency}
      onCurrencyChange={setCurrency}
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
