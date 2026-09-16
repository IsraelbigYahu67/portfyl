import { useQuery } from "@tanstack/react-query";
import { fetchStockView } from "../../api";
import { StockOverview } from "../StockDetail";
import { AsyncSection } from "../ui";

export function StockDataTab({ ticker, view, overviewData, sectionIds }) {
  const query = useQuery({
    queryKey: ["stock-view", ticker, view],
    queryFn: () => fetchStockView(ticker, view),
    enabled: Boolean(ticker),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  return (
    <AsyncSection
      isLoading={query.isLoading}
      error={query.error}
      onRetry={() => query.refetch()}
      loading={<div className="p-6 text-sm text-muted animate-pulse">Loading {view}…</div>}
    >
      {query.data ? (
        <StockOverview
          data={{ ...overviewData, ...query.data }}
          sectionIds={sectionIds}
          showHeader={false}
          showCustomizer={false}
        />
      ) : null}
    </AsyncSection>
  );
}
