import { useQuery } from "@tanstack/react-query";
import { fetchShibuiFilings } from "../../api";
import { formatTableDate } from "../../lib/format";
import { FORM_TYPE_LABELS, sortFilingsNewestFirst } from "../StockDetail";
import { AsyncSection } from "../ui";

export function StockFilingsTab({ ticker }) {
  const query = useQuery({
    queryKey: ["shibui-filings", ticker],
    queryFn: () => fetchShibuiFilings(ticker),
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
  const filings = sortFilingsNewestFirst(query.data?.filings);

  return (
    <AsyncSection
      isLoading={query.isLoading}
      error={query.error}
      onRetry={() => query.refetch()}
      loading={<div className="p-6 text-sm text-muted animate-pulse">Loading filings…</div>}
    >
      <section className="p-4 sm:p-6" aria-labelledby="filings-heading">
        <h3 id="filings-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">SEC filings</h3>
        {filings.length ? (
          <ul className="card !p-0 mt-3 divide-y divide-surface-border overflow-hidden">
            {filings.map((filing, index) => {
              const form = filing.raw_form_type || filing.form_type;
              const title = FORM_TYPE_LABELS[filing.form_type] || FORM_TYPE_LABELS[form];
              return (
                <li key={`${filing.filing_url}-${index}`} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                  <time dateTime={filing.filing_date} className="w-28 shrink-0 tabular-nums text-muted">
                    {formatTableDate(filing.filing_date)}
                  </time>
                  <span className="font-medium">{form}</span>
                  {title ? <span className="text-muted">{title}</span> : null}
                  <a className="ml-auto text-brand hover:underline max-md:py-3" href={filing.filing_url} target="_blank" rel="noreferrer">View filing</a>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-muted">No filings are available for {ticker}.</p>
        )}
      </section>
    </AsyncSection>
  );
}
