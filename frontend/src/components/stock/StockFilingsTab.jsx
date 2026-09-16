import { useQuery } from "@tanstack/react-query";
import { fetchShibuiFilings } from "../../api";
import { AsyncSection } from "../ui";

export function StockFilingsTab({ ticker }) {
  const query = useQuery({
    queryKey: ["shibui-filings", ticker],
    queryFn: () => fetchShibuiFilings(ticker),
    staleTime: 60 * 60 * 1000,
    retry: false,
  });

  return (
    <AsyncSection
      isLoading={query.isLoading}
      error={query.error}
      onRetry={() => query.refetch()}
      loading={<div className="p-6 text-sm text-muted animate-pulse">Loading filings…</div>}
    >
      <section className="p-4 sm:p-6" aria-labelledby="filings-heading">
        <h3 id="filings-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">SEC filings</h3>
        {query.data?.filings?.length ? (
          <ul className="mt-3 divide-y divide-surface-border rounded-xl bg-surface">
            {query.data.filings.map((filing, index) => (
              <li key={`${filing.filing_url}-${index}`} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <time className="text-muted">{filing.filing_date}</time>
                <span className="font-medium">{filing.raw_form_type || filing.form_type}</span>
                <a className="ml-auto text-brand hover:underline" href={filing.filing_url} target="_blank" rel="noreferrer">View filing</a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-muted">No filings are available for {ticker}.</p>
        )}
      </section>
    </AsyncSection>
  );
}
