// Exact click-path for creating the Trading 212 API credentials Portfyl needs.
// Shared by Settings → Connections (next to the key fields) and the first-run
// onboarding (step 2 for Trading 212), so both always show the same steps.
// Portfyl only reads: the two write permissions stay unticked on purpose.

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
  return (
    <section aria-labelledby="t212-api-guide-heading" className={`rounded-xl bg-surface-hover p-4 text-sm ${className}`}>
      <h4 id="t212-api-guide-heading" className="font-semibold text-ink">How to connect Trading 212</h4>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-muted">
        <li>In Trading 212 tap the <Ink>three horizontal lines</Ink> (menu).</li>
        <li>Open <Ink>Settings</Ink>.</li>
        <li>Choose <Ink>API (Beta)</Ink>.</li>
        <li>
          Generate an API key and tick everything <Ink>except</Ink> <Ink>Orders - Execute</Ink> and <Ink>Pies - Write</Ink>. That means:
          <ul aria-label="Permissions to tick" className="mt-1.5 grid list-disc gap-x-6 gap-y-0.5 pl-5 sm:grid-cols-2">
            {T212_PERMISSIONS.map((permission) => <li key={permission}><Ink>{permission}</Ink></li>)}
          </ul>
        </li>
        <li>Copy the <Ink>API key ID</Ink> and the <Ink>Secret key</Ink> and paste them into Portfyl.</li>
      </ol>
    </section>
  );
}
