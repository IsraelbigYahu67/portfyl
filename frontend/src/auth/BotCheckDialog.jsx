import { useState } from "react";

import { Modal } from "../components/ui/Modal";
import { useI18n } from "../i18n/I18nProvider";
import TurnstileWidget from "./TurnstileWidget";
import { turnstileSiteKey } from "./turnstileConfig";

// Cloudflare names Brazilian Portuguese "pt-br"; the other app languages match.
const WIDGET_LANGUAGE = { pt: "pt-br" };

// The one-time challenge shown when a brand-new account is about to be created
// (AuthProvider opens it after the server answers `bot_check_required`).
export default function BotCheckDialog({ open, onToken, onCancel }) {
  const { t, language } = useI18n();
  const siteKey = turnstileSiteKey();
  const [failed, setFailed] = useState(false);

  return (
    <Modal open={open} onClose={onCancel} titleId="bot-check-title" className="space-y-4 p-6">
      <h2 id="bot-check-title" className="text-lg font-bold">{t("One quick check")}</h2>
      {siteKey ? (
        <>
          <p className="text-sm text-muted">
            {t("Confirm you are a person to finish creating your Portfyl account.")}
          </p>
          <TurnstileWidget
            siteKey={siteKey}
            language={WIDGET_LANGUAGE[language] ?? language}
            onToken={(token) => {
              setFailed(false);
              onToken(token);
            }}
            onError={() => setFailed(true)}
          />
          {failed && (
            <p role="alert" className="text-sm font-medium text-loss">
              {t("The sign-up check did not pass. Please try again.")}
            </p>
          )}
        </>
      ) : (
        <p role="alert" className="text-sm text-muted">
          {t("The sign-up check is not available right now. Please try again later or write to support@portfyl.com.")}
        </p>
      )}
      <div className="flex justify-end">
        <button type="button" onClick={onCancel} className="btn-ghost min-h-11 px-5 text-sm font-semibold">
          {t("Cancel")}
        </button>
      </div>
    </Modal>
  );
}
