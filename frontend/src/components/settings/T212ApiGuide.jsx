// Exact click-path for creating the Trading 212 API credentials Portfyl needs.
// Shared by Settings → Connections (next to the key fields) and the first-run
// onboarding (step 3 for Trading 212), so both always show the same steps.
// Portfyl only reads: the two write permissions stay unticked on purpose.
// The permission names are Trading 212's own labels, so they stay in English.

import { rich, useT } from "../../i18n/I18nProvider";

const Ink = ({ children }) => <span className="font-medium text-ink">{children}</span>;

// Every permission to tick. Everything else, notably "Orders - Execute" and
// "Pies - Write", stays off, so the key can never place a trade.
export const T212_PERMISSIONS = Object.freeze([
  "Account data",
  "History - Dividends",
  "History - Orders",
  "History - Transactions",
  "Metadata",
  "Orders - Read",
  "Pies - Read",
  "Portfolio",
]);

export default function T212ApiGuide({ className = "" }) {
  const t = useT();
  const ink = { b: (words) => <Ink>{words}</Ink> };
  return (
    <section aria-labelledby="t212-api-guide-heading" className={`rounded-xl bg-surface-hover p-4 text-sm ${className}`}>
      <h4 id="t212-api-guide-heading" className="font-semibold text-ink">{t("How to connect Trading 212")}</h4>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-muted">
        <li>{rich(t("In Trading 212 tap the <b>three horizontal lines</b> (menu)."), ink)}</li>
        <li>{rich(t("Open <b>Settings</b>."), ink)}</li>
        <li>{rich(t("Choose <b>API (Beta)</b>."), ink)}</li>
        <li>
          {rich(t("Generate an API key and tick everything <b>except</b> <b>Orders - Execute</b> and <b>Pies - Write</b>. That means:"), ink)}
          <ul aria-label={t("Permissions to tick")} className="mt-1.5 grid list-disc gap-x-6 gap-y-0.5 pl-5 sm:grid-cols-2">
            {T212_PERMISSIONS.map((permission) => <li key={permission}><Ink>{permission}</Ink></li>)}
          </ul>
        </li>
        <li>{rich(t("Copy the <b>API key ID</b> and the <b>Secret key</b> and paste them into Portfyl."), ink)}</li>
      </ol>
    </section>
  );
}
