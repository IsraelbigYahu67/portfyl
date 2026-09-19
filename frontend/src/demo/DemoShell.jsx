import { NavLink } from "react-router-dom";
import { useDemoData } from "./DemoDataContext";
import { DEMO_COPY, getDemoLanguage } from "./demoCopy";

const REG_TARGET = `${import.meta.env.VITE_APP_ORIGIN || "https://app.portfyl.com"}/register?source=demo`;

const NAV_ITEMS = [
  { to: "/demo", end: true, key: "overview" },
  { to: "/demo/allocation", key: "allocation" },
  { to: "/demo/analytics", key: "analytics" },
  { to: "/demo/dividends", key: "dividends" },
];

// Compact public shell for the read-only /demo/* routes: nav landmark,
// synthetic-data disclosure with the fixture's as-of date, a link back to
// the marketing site, and the registration CTA. No import/sync/settings/
// assistant/transaction/refresh controls -- those private-app actions are
// omitted entirely, not shown disabled.
export default function DemoShell({ children }) {
  const data = useDemoData();
  const t = DEMO_COPY[getDemoLanguage()];

  return (
    <div className="min-h-screen bg-surface text-ink flex flex-col">
      <header className="border-b border-hairline px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <a href="/" className="font-display font-bold text-lg tracking-tight">Portfyl</a>
        <span className="financial-meta">
          {t.disclosure} · {t.asOfLabel} {data.asOf}
        </span>
        <a href={REG_TARGET} className="btn-primary text-sm">{t.createAccount}</a>
      </header>

      <nav aria-label={t.navigation} className="border-b border-hairline overflow-x-auto">
        <div className="flex gap-1 px-4 py-2 min-w-max">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive ? "bg-brand/10 text-brand" : "text-muted hover:text-ink"
                }`
              }
            >
              {t[item.key]}
            </NavLink>
          ))}
        </div>
      </nav>

      <main className="flex-1 p-4 max-w-6xl w-full mx-auto">{children}</main>

      <footer className="border-t border-hairline px-4 py-3">
        <a href="/" className="text-sm text-muted hover:text-ink">{t.backHome}</a>
      </footer>
    </div>
  );
}
