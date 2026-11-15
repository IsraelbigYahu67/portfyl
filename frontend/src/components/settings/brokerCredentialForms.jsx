// Credential fields for the three API brokers. Settings → Connections and the
// onboarding connect step both render these, so the markup lives here once.
//
// The forms are controlled and pure: they hold only the show/hide toggle. The
// owner keeps the values, trims them and runs the request. This module must stay
// importable by the onboarding view, so it never reaches `api` or `App`.
import { useState } from "react";
import { Eye, EyeOff, Link as LinkIcon, Loader2 } from "lucide-react";

import { useT } from "../../i18n/I18nProvider";

export const EMPTY_CREDENTIALS = Object.freeze({
  trading212: Object.freeze({ apiKey: "", apiSecret: "" }),
  ibkr: Object.freeze({ flexToken: "", queryId: "" }),
  etoro: Object.freeze({ userKey: "" }),
});

// Every field must hold text once surrounding whitespace is dropped.
export function credentialsComplete(brokerKey, values) {
  const fields = Object.keys(EMPTY_CREDENTIALS[brokerKey] ?? {});
  if (!fields.length) return false;
  return fields.every((field) => typeof values?.[field] === "string" && values[field].trim() !== "");
}

function ConnectButton({ disabled, submitting, onSubmit }) {
  const t = useT();
  return (
    <button type="button" onClick={onSubmit} disabled={disabled} className="btn-primary flex items-center gap-2 text-sm min-h-11 md:min-h-0 disabled:opacity-40">{submitting ? <Loader2 size={16} className="animate-spin" /> : <LinkIcon size={16} />}{t("Connect")}</button>
  );
}

// These render fragments: the owner supplies the `space-y-3` wrapper, so the
// fields and the button stay direct siblings of whatever sits next to them.

export function T212CredentialsForm({ values, onChange, onSubmit, busy = false, submitting = false }) {
  const t = useT();
  const [showKey, setShowKey] = useState(false);
  return (
    <>
      <div>
        <label htmlFor="t212-api-key" className="mb-1.5 block text-sm text-muted">{t("API key ID")}</label>
        <div className="relative">
          <input id="t212-api-key" type={showKey ? "text" : "password"} value={values.apiKey} onChange={(event) => onChange({ ...values, apiKey: event.target.value })} placeholder={t("Paste API key ID here")} className="input pr-10 text-sm" />
          <button type="button" aria-label={showKey ? t("Hide API key") : t("Show API key")} onClick={() => setShowKey((visible) => !visible)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink">{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
        </div>
      </div>
      <div>
        <label htmlFor="t212-api-secret" className="mb-1.5 block text-sm text-muted">{t("Secret key")}</label>
        <input id="t212-api-secret" type="password" value={values.apiSecret} onChange={(event) => onChange({ ...values, apiSecret: event.target.value })} placeholder={t("Paste Secret Key here")} className="input text-sm" />
      </div>
      <ConnectButton disabled={!credentialsComplete("trading212", values) || busy} submitting={submitting} onSubmit={onSubmit} />
    </>
  );
}

export function IBKRCredentialsForm({ values, onChange, onSubmit, busy = false, submitting = false }) {
  const t = useT();
  const [showToken, setShowToken] = useState(false);
  return (
    <>
      <div>
        <label htmlFor="ibkr-flex-token" className="mb-1.5 block text-sm text-muted">{t("Flex Web Service token")}</label>
        <div className="relative">
          <input id="ibkr-flex-token" type={showToken ? "text" : "password"} value={values.flexToken} onChange={(event) => onChange({ ...values, flexToken: event.target.value })} placeholder={t("Paste your Flex Web Service token")} autoComplete="off" className="input pr-10 text-sm" />
          <button type="button" aria-label={showToken ? t("Hide token") : t("Show token")} onClick={() => setShowToken((visible) => !visible)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink">{showToken ? <EyeOff size={16} /> : <Eye size={16} />}</button>
        </div>
      </div>
      <div>
        <label htmlFor="ibkr-query-id" className="mb-1.5 block text-sm text-muted">{t("Flex Query ID")}</label>
        <input id="ibkr-query-id" type="text" inputMode="numeric" value={values.queryId} onChange={(event) => onChange({ ...values, queryId: event.target.value })} placeholder={t("e.g. 123456")} autoComplete="off" className="input text-sm" />
      </div>
      <ConnectButton disabled={!credentialsComplete("ibkr", values) || busy} submitting={submitting} onSubmit={onSubmit} />
    </>
  );
}

export function EtoroCredentialsForm({ values, onChange, onSubmit, busy = false, submitting = false }) {
  const t = useT();
  const [showKey, setShowKey] = useState(false);
  return (
    <>
      <div>
        <label htmlFor="etoro-user-key" className="mb-1.5 block text-sm text-muted">{t("eToro API key")}</label>
        <div className="relative">
          <input id="etoro-user-key" type={showKey ? "text" : "password"} value={values.userKey} onChange={(event) => onChange({ ...values, userKey: event.target.value })} placeholder={t("Paste your eToro API key (Read, Real)")} autoComplete="off" className="input pr-10 text-sm" />
          <button type="button" aria-label={showKey ? t("Hide key") : t("Show key")} onClick={() => setShowKey((visible) => !visible)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink">{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
        </div>
      </div>
      <ConnectButton disabled={!credentialsComplete("etoro", values) || busy} submitting={submitting} onSubmit={onSubmit} />
    </>
  );
}
