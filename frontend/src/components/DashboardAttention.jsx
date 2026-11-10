import { Link } from "react-router-dom";
import { AlertTriangle, AlertCircle, Info } from "lucide-react";
import AsyncSection from "./ui/AsyncSection";
import { SkeletonRows } from "./ui";
import { msg, useT } from "../i18n/I18nProvider";

const SEVERITY = {
  critical: { label: msg("Critical"), Icon: AlertTriangle, tone: "text-loss" },
  warning: { label: msg("Warning"), Icon: AlertCircle, tone: "text-amber-400" },
  info: { label: msg("Info"), Icon: Info, tone: "text-muted" },
};

// Presentational list of deterministic attention signals. Severity is stated
// in words, not color alone; every item links to the page that resolves it.
export default function DashboardAttention({ alerts = [], isLoading = false, error, onRetry }) {
  const t = useT();
  return (
    <AsyncSection
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      loading={<SkeletonRows rows={3} cols={1} />}
    >
      {alerts.length === 0 ? (
        <p className="text-sm text-muted py-4 text-center">
          {t("Nothing needs attention right now.")}
        </p>
      ) : (
        <ul className="space-y-2.5" aria-label={t("Portfolio attention")}>
          {alerts.map((alert) => {
            const { label, Icon, tone } = SEVERITY[alert.severity] || SEVERITY.info;
            return (
              <li key={alert.id}>
                <Link
                  to={alert.to}
                  className="flex items-start gap-3 rounded-lg border border-hairline px-3 py-2.5 hover:bg-surface-hover transition-colors"
                >
                  <Icon size={15} className={`${tone} mt-0.5 shrink-0`} aria-hidden="true" />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-ink">{alert.title}</span>
                    <span className="block text-xs text-muted">{alert.detail}</span>
                  </span>
                  <span className={`ml-auto text-xs font-bold uppercase tracking-wider ${tone} shrink-0`}>
                    {t(label)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </AsyncSection>
  );
}
