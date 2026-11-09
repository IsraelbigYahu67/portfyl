import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown } from "lucide-react";

import { IBKR_FLEX_SECTIONS } from "../../lib/ibkrFlex";
import { rich, useT } from "../../i18n/I18nProvider";

const Ink = ({ children }) => <span className="text-ink">{children}</span>;
const Code = ({ children }) => <code className="font-mono text-ink">{children}</code>;

// Broker menu labels stay as the broker shows them (in English, inside <b>);
// only the sentence around them is translated.
function guides(t) {
  const ink = (text) => rich(text, { b: (words) => <Ink>{words}</Ink>, code: (words) => <Code>{words}</Code> });
  const settingsLink = (text) => rich(text, {
    link: (words) => <Link to="/settings?section=connections" className="text-brand underline">{words}</Link>,
  });
  return [
    {
      id: "ibkr",
      name: "Interactive Brokers",
      file: "Activity Flex XML",
      steps: [
        ink(t("In the IBKR portal open <b>Performance & Reports → Flex Queries</b> and create an <b>Activity Flex Query</b>.")),
        <>
          {t("Enable these sections (all fields):")}
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {IBKR_FLEX_SECTIONS.map(([section, level]) => (
              <li key={section}><Ink>{section}</Ink>{level && ` — ${level}`}</li>
            ))}
          </ul>
        </>,
        ink(t("Format <b>XML</b>, date <code>yyyyMMdd</code>, time <code>HHmmss</code>, separator <code>;</code>.")),
        t("Run it for one year at a time (a statement covers at most 365 days) and upload every XML. Lynx accounts use the same steps."),
      ],
      note: settingsLink(t("To keep it up to date automatically, connect the Flex Web Service in <link>Settings → Connections</link>.")),
    },
    {
      id: "degiro",
      name: "Degiro",
      file: t("two CSV files"),
      steps: [
        ink(t("Open <b>Inbox → Transactions</b>, pick whole months and choose <b>Export → CSV</b>.")),
        ink(t("Open <b>Inbox → Account Statement</b> for the same period and choose <b>Export → CSV</b>.")),
        t("Upload both files, one after the other. Trades come from Transactions, dividends and cash from the Account Statement."),
      ],
    },
    {
      id: "xtb",
      name: "XTB",
      file: "Excel (.xlsx)",
      steps: [
        ink(t("In <b>xStation 5</b> (web) open <b>Account history → Cash operations</b>.")),
        ink(t("Choose the whole period and <b>Export</b> to Excel.")),
        t("Upload the .xlsx file. Stocks, ETFs, dividends and cash are imported; CFD trades are counted and skipped."),
      ],
    },
    {
      id: "schwab",
      name: "Charles Schwab",
      file: "CSV",
      steps: [
        ink(t("Open <b>Accounts → History → Transactions</b>, select <b>All</b> and <b>Export</b>.")),
        t("Export whole quarters: Schwab cuts an export at 1,500 rows."),
      ],
    },
    {
      id: "fidelity",
      name: "Fidelity",
      file: "CSV",
      steps: [ink(t("Open <b>Activity & Orders</b>, choose the period and click <b>Download</b>."))],
    },
    {
      id: "etoro",
      name: "eToro",
      file: t("API key, no file"),
      steps: [
        ink(t("In eToro open <b>Settings → Trading → API Key Management</b> and create a key.")),
        ink(t("Give it the <b>Read</b> permission for the <b>Real</b> environment.")),
        settingsLink(t("Paste the key in <link>Settings → Connections</link>.")),
      ],
    },
  ];
}

const GUIDE_IDS = ["ibkr", "degiro", "xtb", "schwab", "fidelity", "etoro"];

export default function BrokerGuides({ initialOpen = null }) {
  const t = useT();
  const [open, setOpen] = useState(() => (GUIDE_IDS.includes(initialOpen) ? initialOpen : null));
  return (
    <section aria-labelledby="broker-guides-heading" className="card space-y-3">
      <div>
        <h2 id="broker-guides-heading" className="font-semibold">{t("How to export from your broker")}</h2>
        <p className="mt-1 text-xs text-muted">{t("Rows already in the portfolio are recognized and skipped, so overlapping exports are safe.")}</p>
      </div>
      <ul className="space-y-2">
        {guides(t).map((guide) => {
          const expanded = open === guide.id;
          const panelId = `broker-guide-${guide.id}`;
          return (
            <li key={guide.id} className="rounded-xl bg-surface-hover">
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={panelId}
                onClick={() => setOpen(expanded ? null : guide.id)}
                className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left text-sm"
              >
                <span className="font-medium text-ink">{guide.name}</span>
                <span className="flex items-center gap-2 text-xs text-muted">
                  {guide.file}
                  <ChevronDown size={16} aria-hidden="true" className={`transition-transform motion-reduce:transition-none ${expanded ? "rotate-180" : ""}`} />
                </span>
              </button>
              {expanded && (
                <div id={panelId} className="px-4 pb-4 text-sm text-muted">
                  <ol className="list-decimal space-y-2 pl-5">
                    {guide.steps.map((step, index) => <li key={index}>{step}</li>)}
                  </ol>
                  {guide.note && <p className="mt-3 text-xs">{guide.note}</p>}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
