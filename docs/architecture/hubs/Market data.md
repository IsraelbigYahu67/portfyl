---
type: hub
layer: backend
tags: [arch/hub]
generated: false
---
# Market data

Market data is everything Portfyl does not get from the user's own broker: live quotes, price history, fundamentals, exchange rates, company filings and research feeds. It powers the stock detail page, search, watchlists, benchmarks, price alerts and the valuation of every holding. The main source is the free `yfinance` library, which is slow and sometimes wrong, so most of this area is about being careful: timeouts, caches and graceful "no data" answers.

The commercial market-data question (licence to show data to paying customers) is still open. It sits in Workstream A of the SaaS plan, and no vendor has been chosen yet.

## How it works
- **Quotes and fundamentals**: [[market_data]] wraps yfinance `.info`. Each lookup is gated by a short history probe, bounded by a hard timeout in a worker thread (a thin or delisted ticker can otherwise hang for minutes), and cached with a short TTL. Batches run concurrently and share one deadline. The small thread-safe cache comes from [[cache]].
- **Ticker fixes**: [[ticker_map]] remaps tickers Yahoo does not serve under the broker's symbol (for example one LSE ETF that is only available on Amsterdam).
- **Money and FX**: transactions carry `fx_to_czk` and values are pivoted through CZK, then converted to the display currency by [[fx]] (`fetch_fx_to_czk`, `convert_amount`, `bulk_fetch_fx`). A missing rate degrades to the unconverted amount instead of crashing. Currency names are normalized by [[currency_codes]].
- **API**: [[routers.market]] serves search, quotes, history, fundamentals, FX pairs, dividend growth and the research endpoints (insiders, filings, earnings, valuation history). Research endpoints are gated by plan capability (`standard_research`, `advanced_research`, `dividend_analysis`) from [[plans]] and [[entitlements]].
- **Research providers**: [[shibui_client]] talks to the Shibui Finance MCP server for financials, ownership and valuation history. [[edgar_client]] fetches SEC EDGAR filing documents. [[alphavantage_client]] is used only for the on-demand politician-trades feed. [[dividend_growth]] builds per-ticker dividend growth, preferring Shibui data and falling back to yfinance.
- **Benchmarks**: [[routers.benchmarks]] manages benchmark indexes and compares a portfolio against them (custom benchmarks need the Pro plan).
- **Watchlists and alerts**: [[routers.watchlists]] stores lists and symbols with plan limits. Price alerts use the same live prices (see [[Alerts and integrations]]).
- **Deliberate quiet**: yfinance logs "possibly delisted" and "no earnings dates" errors for tickers Yahoo simply lacks. [[main]] sets the `yfinance` logger to CRITICAL on purpose, and the code handles missing data with empty or null checks. Do not "fix" this by turning the noise back on.
- **Frontend**: [[pages.Stock]] (with [[components.stock (folder)]] and [[components.StockDetail]]), [[pages.Search]], [[pages.Watchlists]] (with [[components.watchlists (folder)]]), plus [[hooks.useStockDetail]], [[hooks.useStockIntentPrefetch]] and [[hooks.useStockReportConfig]] for loading and prefetching. [[lib.priceFreshness]] shows how old a price is, and [[components.TickerLink]] links any ticker to its page.
- **Not built yet**: a PostgreSQL market-data cache is designed and planned (docs below) but no code for it exists on this branch. Today only the in-memory caches above exist.

## Key code
- [[market_data]]: bounded, cached yfinance lookups.
- [[cache]]: size-bounded TTL cache.
- [[fx]]: FX rates and currency conversion.
- [[ticker_map]]: Yahoo symbol fixes.
- [[routers.market]]: quote, history, fundamentals and research endpoints.
- [[routers.benchmarks]]: benchmark CRUD and comparison.
- [[routers.watchlists]]: watchlists and items.
- [[shibui_client]]: Shibui Finance MCP client.
- [[edgar_client]]: SEC EDGAR client.
- [[alphavantage_client]]: Alpha Vantage client (politician trades).
- [[dividend_growth]]: dividend growth analytics.
- [[pages.Stock]]: stock detail page.
- [[pages.Search]]: ticker search.
- [[pages.Watchlists]]: watchlists with alert controls.
- [[lib.priceFreshness]]: stale price display helper.

## Data
- [[watchlists (table)]] and [[watchlist_items (table)]]: user lists and their symbols.
- [[benchmarks (table)]] and [[benchmark_components (table)]]: benchmark definitions.
- [[price_alerts (table)]]: alert thresholds that read live prices.
- Market prices themselves are not stored in the database; they are fetched live and cached in memory.

## Related hubs
- [[Portfolio analytics]]
- [[Alerts and integrations]]
- [[Billing and Stripe]]
- [[Broker importers and sync]]
- [[Backend]]

## Docs
- [[superpowers/specs/2026-11-08-portfyl-market-data-cache-design]]: design of the PostgreSQL market-data cache.
- [[superpowers/specs/2026-11-08-portfyl-market-data-cache-review]]: adversarial review of that design.
- [[superpowers/plans/2026-11-12-portfyl-market-data-cache]]: revised v1 plan for the cache.
- [[superpowers/plans/2026-11-09-portfyl-market-data-cache]]: the first draft plan.
- [[superpowers/plans/2026-11-12-portfyl-market-data-cache-fable-prompt]]: kickoff prompt for the cache work.
- [[research/market-data-vendor-requirements-2026-09-07]]: questions to ask commercial data vendors about display rights.
- [[superpowers/specs/2026-07-24-dividend-growth-and-overview-design]]: dividend growth design.
