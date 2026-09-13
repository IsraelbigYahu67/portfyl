// Deterministic portfolio attention signals for the Dashboard. Pure function
// over payloads the Dashboard already fetches — no new endpoint, no scoring
// model: each rule is a plain threshold the user can reason about.
//
// Date-only strings are parsed at UTC midnight so a date never shifts a day
// across timezones. Severity ordering is critical → warning → info; ties
// break on the event date and then the stable id.

const DAY = 86_400_000;
const SEVERITY_RANK = { critical: 0, warning: 1, info: 2 };
const EVENT_WINDOW_DAYS = 14;
const CONCENTRATION_THRESHOLD = 25;

const parseDay = (iso) => (iso ? Date.parse(`${iso}T00:00:00Z`) : NaN);

const within = (iso, today, days) => {
  const delta = (parseDay(iso) - parseDay(today)) / DAY;
  return Number.isFinite(delta) && delta >= 0 && delta <= days;
};

const todayIso = () => new Date().toISOString().slice(0, 10);

export function derivePortfolioAlerts({
  holdings = [],
  dividends = [],
  taxReport = null,
  earnings = [],
  today,
} = {}) {
  const day = today || todayIso();
  const alerts = [];

  for (const h of holdings || []) {
    if (h?.ticker && h.weight != null && h.weight > CONCENTRATION_THRESHOLD) {
      alerts.push({
        id: `concentration-${h.ticker}`,
        severity: "warning",
        title: `Concentration: ${h.ticker}`,
        detail: `${h.ticker} is ${h.weight}% of the portfolio — above the ${CONCENTRATION_THRESHOLD}% concentration threshold.`,
        to: "/allocation",
      });
    }
  }

  for (const d of dividends || []) {
    if (!d?.ticker) continue;
    if (d.income_status === "review") {
      const warnings = Array.isArray(d.warnings) && d.warnings.length
        ? ` (${d.warnings.join(", ")})`
        : "";
      alerts.push({
        id: `dividend-review-${d.ticker}`,
        severity: "warning",
        title: `Review dividend estimate: ${d.ticker}`,
        detail: `${d.ticker}'s dividend estimate is flagged for review${warnings}.`,
        to: "/dividends",
      });
    }
    if (within(d.ex_date, day, EVENT_WINDOW_DAYS)) {
      alerts.push({
        id: `dividend-event-${d.ticker}`,
        severity: "info",
        title: `Dividend soon: ${d.ticker}`,
        detail: `${d.ticker} goes ex-dividend on ${d.ex_date}.`,
        to: "/dividends",
        date: d.ex_date,
      });
    }
  }

  if (taxReport?.summary && taxReport.summary.fx_complete === false) {
    alerts.push({
      id: "tax-fx",
      severity: "warning",
      title: "Tax data incomplete",
      detail: "Some transactions are missing CZK exchange rates, so tax totals exclude those rows.",
      to: "/tax-report",
    });
  }

  for (const e of earnings || []) {
    if (e?.ticker && within(e.date, day, EVENT_WINDOW_DAYS)) {
      alerts.push({
        id: `earnings-${e.ticker}`,
        severity: "info",
        title: `Earnings soon: ${e.ticker}`,
        detail: `${e.ticker} reports earnings on ${e.date}.`,
        to: "/",
        date: e.date,
      });
    }
  }

  return alerts.sort(
    (a, b) =>
      SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
      String(a.date || "").localeCompare(String(b.date || "")) ||
      a.id.localeCompare(b.id)
  );
}
