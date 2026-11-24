import { useId, useState } from "react";
import { AlertCircle, FlaskConical, Info, Loader2 } from "lucide-react";

import { EtoroKeyGuide, IBKRFlexGuide } from "../settings/BrokerKeyGuides";
import {
  EMPTY_CREDENTIALS,
  EtoroCredentialsForm,
  IBKRCredentialsForm,
  T212CredentialsForm,
} from "../settings/brokerCredentialForms";
import T212ApiGuide from "../settings/T212ApiGuide";
import { useI18n } from "../../i18n/I18nProvider";

// The "Connect <broker>" step of the first-run onboarding, rendered by
// OnboardingView. Pure presentation: the useOnboardingConnect hook owns the
// plan check, the requests and the phase; the page passes them in as `connect`.
// Imports nothing from the API client, App or analytics (see
// OnboardingPreview.test.jsx's import-graph guard).

const CREDENTIAL_FORMS = {
  trading212: T212CredentialsForm,
  ibkr: IBKRCredentialsForm,
  etoro: EtoroCredentialsForm,
};

function StepHeader({ eyebrow, title }) {
  return (
    <div className="text-center space-y-3">
      <img src="/portfyl-mark.svg" alt="" className="w-14 h-14 object-contain mx-auto" />
      {eyebrow && <p className="eyebrow text-brand">{eyebrow}</p>}
      <h1 className="font-display text-3xl font-bold text-ink">{title}</h1>
    </div>
  );
}

function Guide({ brokerKey }) {
  if (brokerKey === "trading212") return <T212ApiGuide />;
  if (brokerKey === "ibkr") return <IBKRFlexGuide />;
  if (brokerKey === "etoro") return <EtoroKeyGuide />;
  return null;
}

function Progress({ children }) {
  return (
    <p role="status" className="flex items-center justify-center gap-3 py-6 text-sm text-ink">
      <Loader2 size={18} className="animate-spin text-brand" aria-hidden="true" />
      {children}
    </p>
  );
}

// The upgrade block of the gated screen: a free test switch, the Stripe
// checkout behind the consent sentence, or the owner-only note.
function UpgradeBlock({ connect, disabled }) {
  const { t } = useI18n();
  const consentId = useId();
  const [consented, setConsented] = useState(false);
  const { billingEnabled, canManageBilling, onUpgrade } = connect;

  if (!billingEnabled) {
    return (
      <div className="space-y-3">
        <div className="flex items-start gap-3 rounded-2xl border border-hairline bg-surface-card-elevated px-5 py-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-light text-brand">
            <FlaskConical size={17} aria-hidden="true" />
          </span>
          <p className="self-center text-sm font-semibold text-ink">{t("Free plan switching during private testing")}</p>
        </div>
        <button type="button" onClick={onUpgrade} disabled={disabled} className="btn-primary w-full min-h-[44px]">
          {t("Use {plan} for testing", { plan: "Investor" })}
        </button>
      </div>
    );
  }

  if (!canManageBilling) {
    return <p className="text-sm text-muted">{t("Only the workspace owner can change the plan or manage billing.")}</p>;
  }

  return (
    <div className="space-y-3">
      <label htmlFor={consentId} className="flex cursor-pointer items-start gap-3">
        <input
          id={consentId}
          type="checkbox"
          checked={consented}
          onChange={(event) => setConsented(event.target.checked)}
          className="mt-0.5 h-4 w-4 accent-brand"
        />
        <span className="text-sm text-ink">
          {t("I want my subscription to start immediately. I can withdraw from the contract within 14 days of ordering and I will get the full amount back.")}
        </span>
      </label>
      <button type="button" onClick={onUpgrade} disabled={disabled || !consented} className="btn-primary w-full min-h-[44px]">
        {t("Upgrade to Investor")}
      </button>
    </div>
  );
}

function Gated({ broker, connect, disabled }) {
  const { language, t } = useI18n();
  const cents = connect.investorMonthlyCents;
  const body = Number.isFinite(cents)
    ? t("Connecting {broker} imports your history and keeps it up to date. It is part of the Investor plan for {price} a month.", {
      broker: broker.name,
      price: new Intl.NumberFormat(language, { style: "currency", currency: "EUR" }).format(cents / 100),
    })
    : t("Connecting {broker} imports your history and keeps it up to date. It is part of the Investor plan.", { broker: broker.name });

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h2 className="font-display text-xl font-bold text-ink">{t("Automatic sync is part of Investor")}</h2>
        <p className="text-sm text-muted">{body}</p>
      </div>
      <UpgradeBlock connect={connect} disabled={disabled} />
      <div className="space-y-2 border-t border-hairline pt-4">
        {broker.fileKind ? (
          <button type="button" onClick={connect.onImportFree} disabled={disabled} className="btn-ghost w-full min-h-[44px]">
            {t("Import your {broker} {fileKind} for free", { broker: broker.name, fileKind: broker.fileKind })}
          </button>
        ) : (
          <OtherChoices connect={connect} disabled={disabled} />
        )}
      </div>
    </div>
  );
}

function OtherChoices({ connect, disabled }) {
  const { t } = useI18n();
  return (
    <>
      <button type="button" onClick={connect.onChangeBroker} disabled={disabled} className="btn-ghost w-full min-h-[44px]">
        {t("Choose another broker")}
      </button>
      <button type="button" onClick={connect.onDemo} disabled={disabled} className="btn-ghost w-full min-h-[44px]">
        {t("Look around with sample data (free)")}
      </button>
    </>
  );
}

// The typed values live in ConnectStep, not here: this form unmounts while
// "connecting", and a failed connect must bring the user back to their input.
function Form({ broker, connect, disabled, values, setValues }) {
  const CredentialsForm = CREDENTIAL_FORMS[broker.key];
  return (
    <div className="space-y-3">
      <Guide brokerKey={broker.key} />
      <CredentialsForm values={values} onChange={setValues} onSubmit={() => connect.onSubmit(values)} busy={disabled} />
    </div>
  );
}

export default function ConnectStep({ broker, connect, busy = null }) {
  const { t } = useI18n();
  const { phase, notice, error } = connect;
  const [values, setValues] = useState(EMPTY_CREDENTIALS[broker.key]);
  const working = phase === "connecting" || phase === "syncing";
  const disabled = busy != null || working;

  let content = null;
  if (phase === "loading") {
    content = <Progress>{t("Checking your plan…")}</Progress>;
  } else if (phase === "gated") {
    content = <Gated broker={broker} connect={connect} disabled={disabled} />;
  } else if (phase === "form") {
    content = <Form broker={broker} connect={connect} disabled={disabled} values={values} setValues={setValues} />;
  } else if (phase === "connecting") {
    content = <Progress>{t("Connecting to {broker}…", { broker: broker.name })}</Progress>;
  } else if (phase === "syncing") {
    content = <Progress>{t("Importing your history from {broker}…", { broker: broker.name })}</Progress>;
  } else if (phase === "unavailable") {
    content = (
      <div className="space-y-4">
        <p className="text-sm text-ink">{t("Connecting eToro is temporarily unavailable. Choose another broker or look around with sample data.")}</p>
        <div className="space-y-2">
          <OtherChoices connect={connect} disabled={disabled} />
        </div>
      </div>
    );
  } else if (phase === "sync-failed" || phase === "load-error") {
    content = (
      <button type="button" onClick={connect.onRecheck} disabled={disabled} className="btn-primary w-full min-h-[44px]">
        {t("Try again")}
      </button>
    );
  }

  return (
    <div className="space-y-8">
      <StepHeader eyebrow={t("Step 2 of 2 · {broker}", { broker: broker.name })} title={t("Connect {broker}", { broker: broker.name })} />

      <div className="card mx-auto max-w-2xl space-y-4">
        {notice === "canceled" && (
          <p role="status" className="flex items-start gap-2 text-sm text-muted">
            <Info size={16} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
            {t("Checkout was cancelled. You have not been charged.")}
          </p>
        )}
        {notice === "processing" && (
          <div role="status" className="space-y-2">
            <p className="flex items-start gap-2 text-sm text-muted">
              <Info size={16} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
              {t("Your payment is being processed. Your plan will switch shortly.")}
            </p>
            <button type="button" onClick={connect.onRecheck} disabled={disabled} className="btn-ghost min-h-[44px]">
              {t("Check again")}
            </button>
          </div>
        )}
        {error && (
          <div role="alert" className="flex items-center gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss">
            <AlertCircle size={16} aria-hidden="true" />
            {error}
          </div>
        )}
        {content}
      </div>

      {!connect.locked && !working && (
        <div className="text-center">
          <button type="button" onClick={connect.onBack} disabled={disabled} className="btn-ghost min-h-[44px]">
            {t("Back")}
          </button>
        </div>
      )}
    </div>
  );
}
