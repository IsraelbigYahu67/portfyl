import { useAnalytics } from "./AnalyticsProvider";
import { CONSENT_STATES } from "./consent";
import { ANALYTICS_COPY, getAnalyticsLanguage } from "./analyticsCopy";

// Self-gated: renders nothing once consent has been decided, so any parent
// can mount it unconditionally. Accept/Reject are equally prominent,
// keyboard-focusable, and rely on the app-wide :focus-visible outline for a
// visible focus ring.
export default function ConsentBanner() {
  const { consent, acceptAnalytics, rejectAnalytics } = useAnalytics();
  if (consent !== CONSENT_STATES.PENDING) return null;
  const t = ANALYTICS_COPY[getAnalyticsLanguage()];

  return (
    <div
      role="region"
      aria-label={t.bannerTitle}
      className="fixed inset-x-0 bottom-0 z-50 border-t border-hairline bg-surface-card-elevated px-4 py-4 shadow-[var(--shadow-ambient)]"
    >
      <div className="mx-auto flex max-w-4xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="financial-data text-muted space-y-1">
          <p className="font-semibold text-ink">{t.bannerTitle}</p>
          <p>{t.essential}</p>
          <p>{t.optional} {t.changeLater}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button type="button" onClick={rejectAnalytics} className="btn-ghost text-sm">
            {t.reject}
          </button>
          <button type="button" onClick={acceptAnalytics} className="btn-primary text-sm">
            {t.accept}
          </button>
        </div>
      </div>
    </div>
  );
}
