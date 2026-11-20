import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Clock, X } from "lucide-react";

import { useAuth } from "../../auth/AuthProvider";
import { useT } from "../../i18n/I18nProvider";
import { billingStatusQuery } from "../../lib/billingStatusQuery";
import { markNoticeSeen, noticeValue, readNoticeSeen, trialMessage, trialState } from "../../lib/trial";
import { Badge } from "../ui/Badge";
import { useEntitlementRefresh } from "./useEntitlementRefresh";

const TONE = { active: "brand", ended: "neutral", not_eligible: "info" };

// Cloud only (mounted by the cloud edition's shell). Shows the trial countdown,
// why a trial ended, or that none was given; the Pricing page carries the same
// text, so the banner stays out of its way there.
export default function TrialBanner() {
  const t = useT();
  const { pathname } = useLocation();
  const workspaceId = useAuth().currentWorkspace?.id;
  const { data: status } = useQuery(billingStatusQuery);
  const [seen, setSeen] = useState(() => readNoticeSeen(workspaceId));

  useEntitlementRefresh(status);
  useEffect(() => {
    setSeen(readNoticeSeen(workspaceId));
  }, [workspaceId]);

  const state = trialState(status);
  if (state.phase === "none" || pathname === "/pricing") return null;
  const value = noticeValue(state);
  if (seen === value) return null;

  const dismiss = () => {
    markNoticeSeen(workspaceId, value);
    setSeen(value);
  };

  return (
    <div role="status" className="card mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3 animate-fade-up sm:mb-6">
      <div className="flex min-w-0 flex-wrap items-center gap-3">
        <Clock size={16} aria-hidden="true" className="shrink-0 text-brand" />
        <Badge tone={TONE[state.phase]}>{t("Trial")}</Badge>
        <p className="min-w-0 text-sm font-semibold text-ink">{trialMessage(state, t)}</p>
      </div>
      <div className="flex items-center gap-2">
        <Link to="/pricing" className="btn-primary inline-flex min-h-11 items-center text-sm">
          {t("Compare plans")}
        </Link>
        <button
          type="button"
          onClick={dismiss}
          aria-label={t("Dismiss trial notice")}
          className="btn-ghost grid h-11 w-11 shrink-0 place-items-center rounded-full"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
