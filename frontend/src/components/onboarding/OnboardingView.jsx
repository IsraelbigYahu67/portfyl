import { useId, useState } from "react";
import { AlertCircle, Check, Link2, Loader2, Upload } from "lucide-react";

import BrokerGuides from "../import/BrokerGuides";
import T212ApiGuide from "../settings/T212ApiGuide";
import { Badge } from "../ui/Badge";
import PreferencesChip from "./PreferencesChip";
import { brokerMethods, filterBrokers, findSupportedBroker } from "../../lib/onboardingBrokers";
import { translate, useI18n, useT } from "../../i18n/I18nProvider";

// Pure presentation of the first-run onboarding (docs/prototypes/
// onboarding-preview.html). It deliberately imports nothing from the API
// client or analytics: the real Onboarding page wires the actions to the
// server, and OnboardingPreview reuses this exact view with local-only actions
// so signed-in users can walk through it again safely.
//
// The flow is controlled by its parent:
//   step 1  no brokerKey          -> "Which broker do you use?"
//   step 1b unsupportedName set   -> "Portfyl doesn't support X yet"
//   step 2  brokerKey supported   -> choices tailored to that broker
// The language and display currency are not a step: they are guessed, and
// shown as a chip (PreferencesChip) the visitor can confirm or change.

// Every page that renders this view keys its handlers by these. The pages'
// tests compare their handler maps with this list, so a new choice cannot ship
// without wiring. "blank" is not a choice: it is the separate onStartBlank link.
// "import" stays last: OnboardingPreview.test.jsx's import-graph guard reads a
// quoted "import" followed by another quoted string as a side-effect import.
export const ONBOARDING_CHOICE_KEYS = Object.freeze(["broker", "demo", "import"]);

const english = (text, vars) => translate(null, text, vars);

// The handler for a choice. A missing one is a wiring bug; it is logged and
// does nothing instead of throwing a TypeError from inside a click handler,
// where no error boundary would catch it.
export function choiceHandler(handlers, key) {
  const handler = Object.prototype.hasOwnProperty.call(handlers, key) ? handlers[key] : undefined;
  if (typeof handler === "function") return handler;
  return () => console.error(`Onboarding choice "${key}" has no handler.`);
}

// Step 2's cards for `broker`, most direct route first (the primary one). The
// sample portfolio is not a card: Choices offers it as a quieter link.
export function onboardingChoices(broker, t = english) {
  const fileImport = broker.fileKind
    ? {
      key: "import",
      icon: Upload,
      title: broker.api
        ? t("Import your {broker} {fileKind}", { broker: broker.name, fileKind: broker.fileKind })
        : t("Import your {broker} file", { broker: broker.name }),
      // A file-only broker's steps are the export guide under the cards, so
      // the card keeps just the reassurance; an API broker's card still
      // carries its one-line hint.
      description: broker.api
        ? `${t(broker.hint)} ${t("You'll see a preview before anything is saved.")}`
        : t("You'll see a preview before anything is saved."),
    }
    : {
      key: "import",
      icon: Upload,
      title: t("Import a Portfyl CSV"),
      description: t("Prefer a file? Preview a Portfyl CSV before anything is saved."),
    };
  if (!broker.api) return [{ ...fileImport, primary: true }];
  return [
    {
      key: "broker",
      icon: Link2,
      title: t("Connect {broker}", { broker: broker.name }),
      description: t("Sync automatically with your {credential}. Read-only: Portfyl can't trade.", { credential: t(broker.credential) }),
      primary: true,
    },
    fileImport,
  ];
}

// The inset "well" used for chips, matching the Import progress trough.
const WELL_STYLE = { background: "var(--bg-subtle, var(--surface-hover))", boxShadow: "var(--clay-inset-sm, none)" };
// Marks the recommended choice. An outline, not a Tailwind ring: the ring is a
// box-shadow and Clay cards replace box-shadow with their raised depth.
const PRIMARY_OUTLINE = { outline: "2px solid color-mix(in srgb, var(--brand) 35%, transparent)" };


function StepHeader({ eyebrow, title, children }) {
  return (
    <div className="text-center space-y-3">
      <img src="/portfyl-mark.svg" alt="" className="w-14 h-14 object-contain mx-auto" />
      {eyebrow && <p className="eyebrow text-brand">{eyebrow}</p>}
      <h1 className="font-display text-3xl font-bold text-ink">{title}</h1>
      {children && <p className="text-sm text-muted max-w-xl mx-auto">{children}</p>}
    </div>
  );
}


function SelectedBadge() {
  const t = useT();
  return (
    <Badge tone="brand">
      <Check size={14} aria-hidden="true" />
      {t("Selected")}
    </Badge>
  );
}


function BrokerIcon({ broker }) {
  return (
    <img
      src={broker.icon}
      alt=""
      width={44}
      height={44}
      className="w-11 h-11 shrink-0 rounded-[14px] object-cover"
      style={{ boxShadow: "var(--clay-raise-sm, none)" }}
    />
  );
}


// Step 1: which broker? Checks support before the user invests any effort.
function BrokerPick({ onPick, onUnsupported }) {
  const { language, t } = useI18n();
  const searchId = useId();
  const [query, setQuery] = useState("");
  const { supported, unsupported } = filterBrokers(query, language);
  const typed = query.trim();
  const unknown = typed && !supported.length && !unsupported.length;

  return (
    <div className="space-y-8">
      <StepHeader eyebrow={t("Step 1 of 2")} title={t("Which broker do you use?")}>
        {t("Portfyl reads your trades from your broker, so we check first that yours is supported. Finding out costs nothing.")}
      </StepHeader>

      <div className="space-y-1.5">
        <label htmlFor={searchId} className="eyebrow">{t("Search brokers")}</label>
        <input
          id={searchId}
          type="search"
          autoComplete="off"
          placeholder={t("e.g. Trading 212, Robinhood…")}
          className="input min-h-[44px]"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      {supported.length > 0 && (
        <section aria-labelledby="onboarding-supported" className="space-y-4">
          <h2 id="onboarding-supported" className="eyebrow">{t("Supported")}</h2>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {supported.map((broker) => (
              <li key={broker.key}>
                <button
                  type="button"
                  onClick={() => onPick(broker.key)}
                  className="card card-interactive w-full h-full flex items-center gap-3 text-left !p-4"
                >
                  <BrokerIcon broker={broker} />
                  <span className="min-w-0">
                    <span className="block font-semibold text-ink">{broker.name}</span>
                    <span className="block text-xs text-muted">{brokerMethods(broker, t)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {unsupported.length > 0 && (
        <section aria-labelledby="onboarding-unsupported" className="space-y-4">
          <h2 id="onboarding-unsupported" className="eyebrow">{t("Not supported yet")}</h2>
          <ul className="flex flex-wrap gap-2.5">
            {unsupported.map((name) => (
              <li key={name}>
                <button
                  type="button"
                  onClick={() => onUnsupported(name)}
                  className="min-h-[44px] rounded-full px-4 text-sm font-medium text-muted hover:text-ink"
                  style={WELL_STYLE}
                >
                  {name}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {unknown && (
        <div className="card flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm text-ink">{t("“{name}” isn't in our list.", { name: typed })}</span>
          <button type="button" onClick={() => onUnsupported(typed)} className="btn-ghost text-sm">{t("Check this broker")}</button>
        </div>
      )}
    </div>
  );
}


// Step 1b: the broker can't be read. Say so before the user pays anything.
// `name` is free text the visitor typed: it only ever reaches the page through
// t()'s plain-text {name} interpolation and React's escaping, never rich() or
// raw HTML.
function Unsupported({ name, busy, onBack, onDemo, notice, onNotify, notifyState }) {
  const t = useT();
  const sending = notifyState === "sending";
  return (
    <div className="max-w-md mx-auto space-y-6">
      <div className="text-center space-y-3">
        <span className="w-14 h-14 rounded-[20px] bg-brand-light text-brand flex items-center justify-center mx-auto">
          <AlertCircle size={26} aria-hidden="true" />
        </span>
        <h1 className="font-display text-2xl font-bold text-ink">{t("Portfyl doesn't support {name} yet", { name })}</h1>
        <p className="text-sm text-muted">
          {t("We can only read trades from the brokers on our list, so there would be nothing to show for {name}. Better to know before you pay anything.", { name })}
        </p>
      </div>
      <div className="card space-y-3">
        {onNotify && notifyState === "sent" && (
          <p role="status" className="text-sm text-ink text-center">
            {t("Thanks, we'll e-mail you when {name} is supported.", { name })}
          </p>
        )}
        {onNotify && notifyState !== "sent" && (
          <>
            <button
              type="button"
              onClick={onNotify}
              disabled={busy != null || sending}
              className="btn-primary w-full min-h-[44px] flex items-center justify-center gap-2"
            >
              {sending && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
              {t("Notify me when {name} is supported", { name })}
            </button>
            {notifyState === "error" && (
              <p role="alert" className="text-sm text-loss">{t("We couldn't save that. Please try again.")}</p>
            )}
          </>
        )}
        <button type="button" onClick={onBack} disabled={busy != null} className="btn-ghost w-full min-h-[44px]">{t("Choose another broker")}</button>
        <button type="button" onClick={onDemo} disabled={busy != null} className="btn-ghost w-full min-h-[44px] flex items-center justify-center gap-2">
          {busy === "demo" && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
          {t("Look around with sample data (free)")}
        </button>
      </div>
      {notice}
    </div>
  );
}


// Step 2: how to get this broker's data in.
function Choices({ broker, busy, selected, onChoose, onChangeBroker, onStartBlank, notice }) {
  const t = useT();
  const selectable = selected !== undefined;
  const choices = onboardingChoices(broker, t);

  return (
    <div className="space-y-8">
      <StepHeader eyebrow={t("Step 2 of 2 · {broker}", { broker: broker.name })} title={t("Add your first portfolio")}>
        {t("Good news, {broker} is supported.", { broker: broker.name })}{" "}
        {broker.api ? t("Connect it for automatic sync, or import a file.") : t("Import your export file to get started.")}
      </StepHeader>

      <div className={`grid gap-5 ${choices.length === 2 ? "md:grid-cols-2 max-w-2xl mx-auto" : "max-w-md mx-auto"}`}>
        {choices.map(({ key, icon: Icon, title, description, primary }) => {
          const isSelected = selectable && selected === key;
          // The selected state is an outline plus a "Selected" badge: Clay
          // hides card borders (.theme-clay .card) and owns the card
          // box-shadow, so neither a border nor a ring would show there.
          return (
            <button
              key={key}
              type="button"
              onClick={() => onChoose(key)}
              disabled={busy != null}
              className={`card card-interactive flex flex-col items-start justify-start gap-4 text-left disabled:opacity-60 ${
                isSelected ? "outline outline-2 outline-offset-4 outline-brand" : ""
              }`}
              style={primary && !isSelected ? PRIMARY_OUTLINE : undefined}
              aria-label={title}
              aria-pressed={selectable ? isSelected : undefined}
            >
              <span className="flex w-full items-start justify-between gap-3">
                <span className="w-10 h-10 shrink-0 rounded-[14px] bg-brand-light text-brand flex items-center justify-center">
                  {busy === key ? <Loader2 size={20} className="animate-spin" /> : <Icon size={20} />}
                </span>
                {isSelected && <SelectedBadge />}
              </span>
              <span className="block space-y-1.5">
                <span className="block font-semibold text-ink">{title}</span>
                <span className="block text-xs leading-5 text-muted">{description}</span>
              </span>
            </button>
          );
        })}
      </div>

      {!broker.api && (
        <div className="max-w-2xl mx-auto">
          <BrokerGuides only={broker.key} />
        </div>
      )}

      {notice}

      {broker.key === "trading212" && <T212ApiGuide className="max-w-2xl mx-auto" />}

      <div className="space-y-2 text-center">
        <button
          type="button"
          onClick={() => onChoose("demo")}
          disabled={busy != null}
          className="inline-flex min-h-[44px] items-center justify-center gap-2 text-sm font-medium text-brand hover:underline disabled:opacity-50"
        >
          {busy === "demo" && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
          {t("Just look around with sample data first")}
        </button>
        <p className="text-xs text-muted">
          {t("Sample data is marked as demo data and never mixed into a real import unless you choose to keep it.")}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
        <button type="button" onClick={onChangeBroker} disabled={busy != null} className="min-h-[44px] text-sm font-medium text-brand hover:underline disabled:opacity-50">
          {t("Change broker")}
        </button>
        <button type="button" onClick={onStartBlank} disabled={busy != null} className="min-h-[44px] text-sm font-medium text-muted underline-offset-4 hover:text-ink hover:underline disabled:opacity-50">
          {busy === "blank" ? t("Preparing blank portfolio…") : t("Start with a blank portfolio")}
        </button>
      </div>
    </div>
  );
}


export default function OnboardingView({
  // Step state, owned by the parent (the real page keeps brokerKey in the URL
  // so "Leave import" can return to step 2).
  // The display currency, shown in the language/currency chip. Without
  // onCurrencyChange the chip is not shown.
  currency = null,
  onCurrencyChange = undefined,
  brokerKey = null,
  onBrokerChange,
  unsupportedName = null,
  onUnsupportedChange,
  // "Notify me when X is supported" on the unsupported screen. Without
  // onNotify the button is not shown; notifyState is "idle", "sending",
  // "sent" or "error".
  onNotify = undefined,
  notifyState = "idle",
  onChoose,
  onStartBlank,
  busy = null,
  error = null,
  banner = null,
  notice = null,
  // Leave undefined for plain action buttons (the real onboarding). A value,
  // null included, makes the choices toggle buttons with aria-pressed, the
  // way the preview uses them.
  selected = undefined,
  // Optional ref for a route focus announcer; the view then renders <main>
  // as a programmatic focus target (tabIndex -1, never a visible ring).
  mainRef = undefined,
}) {
  const broker = findSupportedBroker(brokerKey);
  const pickBroker = (key) => {
    onUnsupportedChange(null);
    onBrokerChange(key);
  };

  let step;
  let stepKey;
  if (unsupportedName) {
    stepKey = "unsupported";
    step = (
      <Unsupported
        name={unsupportedName}
        busy={busy}
        notice={notice}
        onNotify={onNotify}
        notifyState={notifyState}
        onBack={() => pickBroker(null)}
        onDemo={() => onChoose("demo")}
      />
    );
  } else if (broker) {
    stepKey = broker.key;
    step = (
      <Choices
        broker={broker}
        busy={busy}
        selected={selected}
        notice={notice}
        onChoose={onChoose}
        onChangeBroker={() => pickBroker(null)}
        onStartBlank={onStartBlank}
      />
    );
  } else {
    stepKey = "pick";
    step = <BrokerPick onPick={pickBroker} onUnsupported={onUnsupportedChange} />;
  }

  return (
    <main
      ref={mainRef}
      tabIndex={mainRef ? -1 : undefined}
      className={`relative min-h-screen bg-bg px-6 pb-12 flex items-center justify-center ${onCurrencyChange ? "pt-20" : "pt-12"} ${mainRef ? "!outline-none" : ""}`}
    >
      {onCurrencyChange && (
        <div className="absolute right-4 top-4 z-10 md:right-6">
          <PreferencesChip currency={currency} onCurrencyChange={onCurrencyChange} />
        </div>
      )}
      <div className={`w-full space-y-8 ${stepKey === "unsupported" || stepKey === broker?.key ? "max-w-4xl" : "max-w-3xl"}`}>
        {banner}

        {error && (
          <div role="alert" className="card border border-loss/40 bg-loss/10 text-sm text-loss">
            {error}
          </div>
        )}

        <div key={stepKey} className="animate-fade-up">
          {step}
        </div>
      </div>
    </main>
  );
}
