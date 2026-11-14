import { Link } from "react-router-dom";
import { Check, ChevronRight, Circle } from "lucide-react";

import { msg, useT } from "../../i18n/I18nProvider";

const LABELS = {
  first_portfolio: msg("Add your first portfolio"),
  second_broker: msg("Add another broker for one combined view"),
  preferences: msg("Check language and currency"),
  dividends: msg("See your dividend calendar"),
};

// The "Getting started" checklist at the top of a new workspace's dashboard.
// It disappears once every step is done; "Hide" dismisses it for good.
export default function WelcomePanel({ items = [], insight = null, onVisit, onDismiss }) {
  const t = useT();
  const done = items.filter((item) => item.done).length;
  if (!items.length || done === items.length) return null;

  return (
    <section aria-labelledby="getting-started-title" className="card animate-fade-up">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h2 id="getting-started-title" className="text-base font-semibold text-ink">{t("Getting started")}</h2>
          {insight && <p className="mt-1 text-sm text-muted">{insight}</p>}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold tabular-nums text-muted">
            {t("{done} of {total} done", { done, total: items.length })}
          </span>
          <button type="button" onClick={onDismiss} className="btn-ghost min-h-11 text-sm">
            {t("Hide")}
          </button>
        </div>
      </div>
      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              to={item.to}
              onClick={() => onVisit?.(item.id)}
              className="flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 text-sm text-ink transition-colors hover:bg-surface-hover"
            >
              <span
                aria-hidden="true"
                className={`grid h-6 w-6 shrink-0 place-items-center rounded-full ${
                  item.done ? "bg-brand/10 text-brand" : "text-muted"
                }`}
              >
                {item.done ? <Check size={14} /> : <Circle size={14} />}
              </span>
              <span className={`min-w-0 flex-1 ${item.done ? "text-muted line-through" : "font-medium"}`}>
                {t(LABELS[item.id])}
              </span>
              <ChevronRight size={16} aria-hidden="true" className="shrink-0 text-muted" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
