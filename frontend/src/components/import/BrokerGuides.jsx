import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown } from "lucide-react";

import { IBKR_FLEX_SECTIONS } from "../../lib/ibkrFlex";

const Ink = ({ children }) => <span className="text-ink">{children}</span>;

// How to get each phase-1 broker's history into Portfyl. Formats live in
// backend/importers/formats/; eToro syncs through its API instead of a file.
const GUIDES = [
  {
    id: "ibkr",
    name: "Interactive Brokers",
    file: "Activity Flex XML",
    steps: [
      <>In the IBKR portal open <Ink>Performance &amp; Reports → Flex Queries</Ink> and create an <Ink>Activity Flex Query</Ink>.</>,
      <>
        Enable these sections (all fields):
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          {IBKR_FLEX_SECTIONS.map(([section, level]) => (
            <li key={section}><Ink>{section}</Ink>{level && ` — ${level}`}</li>
          ))}
        </ul>
      </>,
      <>Format <Ink>XML</Ink>, date <code className="font-mono text-ink">yyyyMMdd</code>, time <code className="font-mono text-ink">HHmmss</code>, separator <code className="font-mono text-ink">;</code>.</>,
      <>Run it for one year at a time (a statement covers at most 365 days) and upload every XML. Lynx accounts use the same steps.</>,
    ],
    note: <>To keep it up to date automatically, connect the Flex Web Service in <Link to="/settings?section=connections" className="text-brand underline">Settings → Connections</Link>.</>,
  },
  {
    id: "degiro",
    name: "Degiro",
    file: "two CSV files",
    steps: [
      <>Open <Ink>Inbox → Transactions</Ink>, pick whole months and choose <Ink>Export → CSV</Ink>.</>,
      <>Open <Ink>Inbox → Account Statement</Ink> for the same period and choose <Ink>Export → CSV</Ink>.</>,
      <>Upload both files, one after the other. Trades come from Transactions, dividends and cash from the Account Statement.</>,
    ],
  },
  {
    id: "xtb",
    name: "XTB",
    file: "Excel (.xlsx)",
    steps: [
      <>In <Ink>xStation 5</Ink> (web) open <Ink>Account history → Cash operations</Ink>.</>,
      <>Choose the whole period and <Ink>Export</Ink> to Excel.</>,
      <>Upload the .xlsx file. Stocks, ETFs, dividends and cash are imported; CFD trades are counted and skipped.</>,
    ],
  },
  {
    id: "schwab",
    name: "Charles Schwab",
    file: "CSV",
    steps: [
      <>Open <Ink>Accounts → History → Transactions</Ink>, select <Ink>All</Ink> and <Ink>Export</Ink>.</>,
      <>Export whole quarters: Schwab cuts an export at 1,500 rows.</>,
    ],
  },
  {
    id: "fidelity",
    name: "Fidelity",
    file: "CSV",
    steps: [<>Open <Ink>Activity &amp; Orders</Ink>, choose the period and click <Ink>Download</Ink>.</>],
  },
  {
    id: "etoro",
    name: "eToro",
    file: "API key, no file",
    steps: [
      <>In eToro open <Ink>Settings → Trading → API Key Management</Ink> and create a key.</>,
      <>Give it the <Ink>Read</Ink> permission for the <Ink>Real</Ink> environment.</>,
      <>Paste the key in <Link to="/settings?section=connections" className="text-brand underline">Settings → Connections</Link>.</>,
    ],
  },
];

export default function BrokerGuides() {
  const [open, setOpen] = useState(null);
  return (
    <section aria-labelledby="broker-guides-heading" className="card space-y-3">
      <div>
        <h2 id="broker-guides-heading" className="font-semibold">How to export from your broker</h2>
        <p className="mt-1 text-xs text-muted">Rows already in the portfolio are recognized and skipped, so overlapping exports are safe.</p>
      </div>
      <ul className="space-y-2">
        {GUIDES.map((guide) => {
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
