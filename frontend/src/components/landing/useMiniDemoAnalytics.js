import { useCallback, useEffect, useRef } from "react";
import { useOptionalAnalytics } from "../../analytics/AnalyticsProvider";
import { ANALYTICS_EVENTS } from "../../analytics/eventContract";

// Reports the first use of one mini demo's controls: one landing_minidemo_used
// per demo per page load, and only once the visitor has accepted analytics.
// Without consent (pending or rejected) nothing is sent and nothing is marked,
// so the first interaction after a later "accept" still counts. The "already
// sent" mark lives in a ref, not in browser storage. Outside an
// AnalyticsProvider (prerender, unit tests) it does nothing.
export function useMiniDemoAnalytics(kind, language) {
  const analytics = useOptionalAnalytics();
  const latest = useRef({ analytics, kind, language });
  const sent = useRef(false);

  useEffect(() => { latest.current = { analytics, kind, language }; });

  const reportUse = useCallback(() => {
    if (sent.current) return;
    const { analytics: current, kind: demo, language: lang } = latest.current;
    if (!current || current.consent !== "accepted") return;
    sent.current = true;
    current.capture(ANALYTICS_EVENTS.LANDING_MINIDEMO_USED, { minidemo: demo, language: lang });
  }, []);

  return { reportUse };
}
