import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, AlertCircle, Info, X, ArrowRight } from "lucide-react";

// Same deterministic signals as DashboardAttention, laid out as cards
// (dashboard variant A). Severity is stated in words, not color alone.
const SEVERITY = {
  critical: { label: "Critical", Icon: AlertTriangle, tone: "var(--loss)" },
  warning: { label: "Warning", Icon: AlertCircle, tone: "#D97706" },
  info: { label: "Info", Icon: Info, tone: "var(--brand)" },
};

const VISIBLE = 3;

export default function InsightCards({ alerts = [] }) {
  // Dismissal lasts for this visit only: the signals are derived from live
  // data, so a still-true problem comes back on the next load.
  const [dismissed, setDismissed] = useState(() => new Set());
  const [expanded, setExpanded] = useState(false);
  const open = alerts.filter((alert) => !dismissed.has(alert.id));

  if (open.length === 0) {
    return <p className="text-sm text-muted py-4 text-center">Nothing needs attention right now.</p>;
  }

  const shown = expanded ? open : open.slice(0, VISIBLE);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Portfolio attention">
        {shown.map((alert) => {
          const { label, Icon, tone } = SEVERITY[alert.severity] || SEVERITY.info;
          return (
            <article
              key={alert.id}
              className="card !p-4 flex flex-col gap-2 min-w-0"
              style={{ boxShadow: `var(--shadow-ambient), inset 0 0 0 1.5px color-mix(in srgb, ${tone} 50%, transparent)` }}
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold text-ink"
                  style={{ background: `color-mix(in srgb, ${tone} 22%, var(--surface-card-elevated))` }}
                >
                  <Icon size={12} aria-hidden="true" style={{ color: tone }} />
                  {label}
                </span>
                <button
                  type="button"
                  aria-label={`Dismiss ${alert.title}`}
                  onClick={() => setDismissed((prev) => new Set(prev).add(alert.id))}
                  className="grid place-items-center w-7 h-7 rounded-full text-muted hover:text-ink hover:bg-surface-hover"
                >
                  <X size={14} aria-hidden="true" />
                </button>
              </div>
              <h3 className="text-sm font-semibold text-ink leading-snug">{alert.title}</h3>
              <p className="text-xs text-muted">{alert.detail}</p>
              <Link to={alert.to} className="mt-auto inline-flex items-center gap-1 self-start text-xs font-semibold text-brand hover:text-brand-dim">
                Review <ArrowRight size={12} aria-hidden="true" />
              </Link>
            </article>
          );
        })}
      </div>
      {open.length > VISIBLE && (
        <button type="button" onClick={() => setExpanded((value) => !value)} className="text-xs font-semibold text-brand hover:text-brand-dim">
          {expanded ? "Show fewer" : `Show all ${open.length} signals`}
        </button>
      )}
    </div>
  );
}
