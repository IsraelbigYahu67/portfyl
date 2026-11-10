import { CONSENT_STATES } from "./consent";
import { useAnalytics } from "./AnalyticsProvider";
import { ANALYTICS_COPY, getAnalyticsLanguage } from "./analyticsCopy";

const STATUS_KEY = { accepted: "statusAccepted", rejected: "statusRejected", pending: "statusPending" };

// Reopenable panel for changing an already-made consent choice. Rendered
// wherever a "Manage analytics"/"Analytics preferences" entry point exists
// (Welcome footer, DemoShell footer, the authenticated Data & Privacy
// settings section); AnalyticsProvider owns whether it is currently open.
export default function AnalyticsPreferences({ onClose, language }) {
  const { consent, acceptAnalytics, rejectAnalytics } = useAnalytics();
  const t = ANALYTICS_COPY[ANALYTICS_COPY[language] ? language : getAnalyticsLanguage()];

  return (
    <div className="card space-y-3" role="region" aria-label={t.manage}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold text-ink">{t.manage}</h3>
        {onClose && (
          <button type="button" onClick={onClose} className="text-muted hover:text-ink text-sm">
            {t.close}
          </button>
        )}
      </div>
      <p className="financial-data text-muted">{t.essential}</p>
      <p className="financial-data text-muted">{t.optional}</p>
      <p className="financial-meta font-semibold text-ink">
        {t[STATUS_KEY[consent] || "statusPending"]}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={rejectAnalytics}
          disabled={consent === CONSENT_STATES.REJECTED}
          className="btn-ghost text-sm disabled:opacity-50"
        >
          {t.reject}
        </button>
        <button
          type="button"
          onClick={acceptAnalytics}
          disabled={consent === CONSENT_STATES.ACCEPTED}
          className="btn-primary text-sm disabled:opacity-50"
        >
          {t.accept}
        </button>
      </div>
    </div>
  );
}
