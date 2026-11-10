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

// English fallback for `t` (the i18n translate function): fills {placeholders}.
const english = (text, vars) => text.replace(/\{(\w+)\}/g, (m, key) => (vars && key in vars ? String(vars[key]) : m));

export function derivePortfolioAlerts({
  holdings = [],
  dividends = [],
  taxReport = null,
  earnings = [],
  today,
  t = english,
} = {}) {
  const day = today || todayIso();
  const alerts = [];

  for (const h of holdings || []) {
    if (h?.ticker && h.price_status === "missing") {
      alerts.push({
        id: `price-missing-${h.ticker}`,
        severity: "critical",
        title: t("No current price: {ticker}", { ticker: h.ticker }),
        detail: t("No current price is available for {ticker}, so it is valued at 0 and portfolio totals are understated.", { ticker: h.ticker }),
        to: "/allocation",
      });
    } else if (h?.ticker && h.price_status === "stale") {
      alerts.push({
        id: `price-stale-${h.ticker}`,
        severity: "warning",
        title: t("Out-of-date price: {ticker}", { ticker: h.ticker }),
        detail: t("The latest price for {ticker} is more than 5 days old, so its value may be wrong. The ticker may be delisted or suspended.", { ticker: h.ticker }),
        to: "/allocation",
      });
    }
    if (h?.ticker && h.weight != null && h.weight > CONCENTRATION_THRESHOLD) {
      alerts.push({
        id: `concentration-${h.ticker}`,
        severity: "warning",
        title: t("Concentration: {ticker}", { ticker: h.ticker }),
        detail: t("{ticker} is {weight}% of the portfolio — above the {threshold}% concentration threshold.", { ticker: h.ticker, weight: h.weight, threshold: CONCENTRATION_THRESHOLD }),
        to: "/allocation",
      });
    }
  }

  for (const d of dividends || []) {
    if (!d?.ticker) continue;
    if (d.income_status === "review") {
      const warnings = Array.isArray(d.warnings) && d.warnings.length ? d.warnings.join(", ") : "";
      alerts.push({
        id: `dividend-review-${d.ticker}`,
        severity: "warning",
        title: t("Review dividend estimate: {ticker}", { ticker: d.ticker }),
        detail: warnings
          ? t("{ticker}'s dividend estimate is flagged for review ({warnings}).", { ticker: d.ticker, warnings })
          : t("{ticker}'s dividend estimate is flagged for review.", { ticker: d.ticker }),
        to: "/dividends",
      });
    }
    if (within(d.ex_date, day, EVENT_WINDOW_DAYS)) {
      alerts.push({
        id: `dividend-event-${d.ticker}`,
        severity: "info",
        title: t("Dividend soon: {ticker}", { ticker: d.ticker }),
        detail: t("{ticker} goes ex-dividend on {date}.", { ticker: d.ticker, date: d.ex_date }),
        to: "/dividends",
        date: d.ex_date,
      });
    }
  }

  if (taxReport?.summary && taxReport.summary.fx_complete === false) {
    alerts.push({
      id: "tax-fx",
      severity: "warning",
      title: t("Tax data incomplete"),
      detail: t("Some transactions are missing CZK exchange rates, so tax totals exclude those rows."),
      to: "/tax-report",
    });
  }

  for (const e of earnings || []) {
    if (e?.ticker && within(e.date, day, EVENT_WINDOW_DAYS)) {
      alerts.push({
        id: `earnings-${e.ticker}`,
        severity: "info",
        title: t("Earnings soon: {ticker}", { ticker: e.ticker }),
        detail: t("{ticker} reports earnings on {date}.", { ticker: e.ticker, date: e.date }),
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
