// "How to get the key" guides shown next to the broker credential forms, in
// Settings → Connections and in the onboarding connect step. Pure view code:
// it must stay importable by the onboarding view (no `api`, no `App`).
import { Info } from "lucide-react";
import { Link } from "react-router-dom";

import { rich, useT } from "../../i18n/I18nProvider";
import { IBKR_FLEX_SECTIONS } from "../../lib/ibkrFlex";

export function IBKRFlexGuide() {
  const t = useT();
  // IBKR's menu and option names stay as IBKR shows them, in <b> / <code>.
  const ink = (text) => rich(text, {
    b: (words) => <span className="text-ink">{words}</span>,
    code: (words) => <code className="font-mono text-ink">{words}</code>,
  });
  return (
    <details className="rounded-lg bg-surface-hover p-4 text-sm">
      <summary className="cursor-pointer font-medium text-ink">{t("How to set up the IBKR Flex Query")}</summary>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-muted">
        <li>{ink(t("In the IBKR portal open <b>Performance & Reports → Flex Queries</b> and create an <b>Activity Flex Query</b>."))}</li>
        <li>
          {t("Enable these sections (select all fields in each):")}
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {IBKR_FLEX_SECTIONS.map(([section, level]) => (
              <li key={section}><span className="text-ink">{section}</span>{level && ` — ${t(level)}`}</li>
            ))}
          </ul>
        </li>
        <li>
          {ink(t("Delivery configuration: format <b>XML</b>, date format <code>yyyyMMdd</code>, time format <code>HHmmss</code>, date/time separator <code>;</code> (semicolon)."))}{" "}
          {ink(t("Period: <b>Last 365 calendar days</b>."))}
        </li>
        <li>{ink(t("Save the query and copy its <b>Query ID</b>. Then open <b>Flex Web Service Configuration</b>, enable it and generate a token."))}</li>
        <li>{t("Paste the token and Query ID above. Lynx accounts use the same steps.")}</li>
      </ol>
      <p className="mt-3 flex items-start gap-2 text-xs text-muted">
        <Info size={14} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
        <span>
          {rich(t("The sync only sees the last 365 days. For older history, run the same query in the portal once per year and upload each XML file on the <link>Import page</link>. Transactions already imported are recognized and skipped."), {
            link: (words) => <Link to="/import" className="text-brand underline">{words}</Link>,
          })}
        </span>
      </p>
    </details>
  );
}

export function EtoroKeyGuide() {
  const t = useT();
  // eToro's menu and permission names stay as eToro shows them.
  const ink = (text) => rich(text, { b: (words) => <span className="text-ink">{words}</span> });
  return (
    <details className="rounded-lg bg-surface-hover p-4 text-sm">
      <summary className="cursor-pointer font-medium text-ink">{t("How to create an eToro API key")}</summary>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-muted">
        <li>{ink(t("In eToro open <b>Settings → Trading → API Key Management</b>."))}</li>
        <li>{ink(t("Create a new key with the <b>Read</b> permission for the <b>Real</b> environment."))}</li>
        <li>{t("Copy the key and paste it above. Portfyl can only read your account; it cannot trade.")}</li>
      </ol>
    </details>
  );
}
