# Portfyl Commercial Market-Data Vendor Requirements

Prepared: 2026-09-07

## Purpose

This is the comparable request-for-information package for Portfyl's cloud
edition. It translates the current product into explicit data and licensing
questions so a low headline API price cannot be mistaken for customer-display
or redistribution permission.

No vendor has been selected or contacted through this record. Public pages are
evidence for a shortlist only; the launch gate requires written terms for the
actual Portfyl use case.

## Product description for vendors

Portfyl is an EU-hosted, multi-tenant portfolio analytics SaaS for self-directed
investors, initially focused on Czech/EU users of Trading 212 and Interactive
Brokers. Users import or synchronize their own trades and see portfolio value,
performance, allocation, dividends, benchmarks, alerts, and security research.

- Initial private beta: 20-50 users.
- Plans under test: Free, Investor, and Pro; payments are not active.
- Cloud region: EU (Google Cloud Run) with Neon PostgreSQL and Cloudflare edge.
- Data is requested server-side. Vendor keys are never exposed to browsers.
- Portfyl may cache normalized observations to control latency/cost and compute
  derived analytics, but does not sell bulk feeds or offer raw vendor downloads.
- User JSON export covers the user's portfolio/account data, not a raw market-
  data cache.
- Tax Report and Screener are local-only and are not part of this commercial
  cloud request.
- Delayed/end-of-day data is acceptable for the initial product. Real-time
  exchange data should be quoted separately rather than silently bundled.

## Required data coverage

### Launch-critical

1. **Instrument reference/search:** stable instrument identifier, ticker,
   exchange/MIC, name, asset type, trading currency, country, active/delisted
   status, and symbol-change history where available.
2. **Historical prices:** adjusted and unadjusted daily OHLCV, latest delayed or
   EOD value, trading date/timezone, adjustment method, and at least ten years
   of history for supported instruments.
3. **Corporate actions:** splits and cash distributions with ex-date, payment
   date, record/declaration dates when available, currency, and correction
   handling.
4. **Foreign exchange:** historical/latest daily FX pairs needed to normalize
   USD, EUR, GBP, CHF, PLN and other broker currencies into CZK.
5. **Equities and ETFs:** US plus relevant European listings used by T212/IBKR;
   the vendor must return a machine-readable coverage file so Portfyl can test
   its real beta symbol set before committing.
6. **Fundamentals:** normalized quarterly/annual income statement, balance sheet,
   cash flow, shares, market capitalization, valuation ratios, margins, growth,
   and filing/report dates with restatement/correction behaviour.
7. **Calendars:** historical/upcoming earnings and dividends with explicit
   source/update timestamps.
8. **Benchmarks:** daily history for the indices/ETFs used in portfolio
   comparisons, with the licensed display form made explicit.

### Valuable but separately priceable

- analyst estimates/consensus and rating history;
- ETF holdings, sector/country exposure, TER/expense ratio, and fund metadata;
- company profiles, classifications and logos;
- news/sentiment;
- intraday/delayed quotes and WebSocket delivery;
- options reference/market data.

SEC EDGAR may remain the direct source for US insider filings if its fair-access
and attribution requirements are met. A market-data quote does not need to
bundle that feed unless it materially improves reliability or licensing.

## Exact rights Portfyl needs in writing

Please answer each row `included`, `excluded`, or `separate fee/agreement` and
identify any exchange-specific exception.

| Right/use | Portfyl requirement |
|---|---|
| Authenticated customer display | Show prices, fundamentals, dividends, calendars, and source/freshness labels in a paid or free SaaS UI. |
| Derived analytics | Compute and display portfolio value, P/L, TWR/XIRR inputs/results, allocation, risk, valuation, dividend statistics, charts, and comparisons. |
| Server-side caching | Cache normalized values across requests/tenants for a stated duration and retain historical observations. |
| Database storage | Store the fields needed for reproducible calculations, corrections, and source timestamps in EU infrastructure. |
| Browser/API transmission | Return the minimum chart/table fields to an authenticated user's browser; Portfyl has no public raw-data API. |
| Reports/exports | Include derived figures and limited displayed observations in future PDF/CSV reports; exclude bulk/raw vendor redistribution. |
| AI use | Supply minimum licensed facts to an assistant and display a derived natural-language explanation with attribution. State whether model training is prohibited separately from inference. |
| Marketing/demo | Use delayed/sample data in screenshots, a demo portfolio, and public product previews. Quote separately if public display differs from authenticated display. |
| Multi-tenant use | One Portfyl vendor credential serving many customer workspaces without per-user vendor accounts or keys. |
| Contractor/support access | Allow least-privilege engineering/support access for operation and incident response. |
| Backup/DR | Include normalized licensed data in encrypted, expiring database backups and temporary recovery branches. |
| Termination | State deletion/return deadlines, continued display/derived-history rights, and migration/export assistance after termination. |

## Vendor response matrix

The written response should fill every field below. Blank or "standard terms"
answers do not close the launch gate.

| Area | Required response |
|---|---|
| Contracting entity | Legal vendor/entity, contract jurisdiction, minimum term, renewal and termination notice. |
| Commercial rights | Exact plan/agreement granting authenticated display and multi-tenant SaaS use. |
| Redistribution boundary | Which returned fields may reach a browser/report and what is considered prohibited redistribution. |
| Exchange rights | Included exchanges, separate licenses/fees, professional-user counts and reporting duties. |
| Coverage | Machine-readable symbols/exchanges, asset types, history depth, delisted/symbol-change handling. |
| Fundamentals | Markets/companies, fields, update latency, restatements, point-in-time availability and source lineage. |
| Corporate actions | Event types/dates/currencies, corrections and historical completeness. |
| FX/benchmarks | Coverage, source, delay, history, benchmark/index display constraints. |
| Cache/storage | Permitted live-cache TTL, historical retention, shared cache, derived database and backup treatment. |
| AI/reports | Inference/context/output, PDF/CSV, screenshot/demo and attribution rules. |
| Delivery | REST/bulk/WebSocket, quotas, burst/concurrency policy, overage, sandbox/trial and stable IDs. |
| Quality/SLA | Availability/latency commitment, correction notification, status feed, support severity and response time. |
| Privacy/security | Processing regions, subprocessors, DPA, SCC/transfer basis, security documentation and breach notice. |
| Price | Beta/startup and production price, exchange/user/device fees, add-ons, overage, taxes, implementation fees and next scaling tiers. |
| Portability | Notice for schema/coverage changes, versioning, termination export and transition period. |

## Initial official-source shortlist

### 1. EODHD

**Why evaluate:** Official documentation advertises broad stocks/ETFs/funds,
indices, FX and bonds coverage, 70+ exchanges and 30+ years of history, plus
historical/EOD, fundamentals, calendars, dividends and splits. That maps well to
Portfyl's broad portfolio/research surface.

**Licensing warning:** EODHD states that ordinary pricing-page packages are for
personal use and commercial licensing requires a separate request. Its terms
prohibit a personal user from selling, retransmitting, redistributing or
displaying the data. Only a written commercial quote that explicitly covers
Portfyl's customer display, caching and derived analytics is usable.

Official evidence:

- [Commercial vs personal licence](https://eodhd.com/financial-apis/commercial-vs-personal-license-use)
- [Terms and conditions](https://eodhd.com/financial-apis/terms-conditions)
- [API coverage quick start](https://eodhd.com/financial-apis/quick-start-with-our-financial-data-apis)
- [Bulk EOD, splits and dividends](https://eodhd.com/financial-apis/bulk-api-eod-splits-dividends)
- [Bulk fundamentals](https://eodhd.com/financial-apis/bulk-fundamentals-api-via-extended-fundamentals-plan)

### 2. Twelve Data

**Why evaluate:** It has an explicit business-plan path and broad multi-market
API positioning. In its March 2026 update it published Venture at USD 499/month
and Enterprise at USD 1,099/month as business tiers, which gives an early price-
floor signal for Portfyl's low subscription prices.

**Licensing warning:** Twelve Data says business plans allow commercial display
subject to exchange licensing, that non-US regions can require extra approval,
and that redistribution requires a separate agreement. Its terms also allow
exchange-specific agreements, fees, professional status and attribution. The
quote must identify the exact T212/IBKR exchange set rather than promise a
generic global package.

Official evidence:

- [Commercial and personal usage](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage)
- [Terms: redistribution and third-party data](https://twelvedata.com/terms)
- [March 2026 business pricing update](https://twelvedata.com/news/march-2026-updates)

### 3. Tiingo

**Why evaluate:** Tiingo publishes predictable internal-commercial pricing and
an explicit redistribution-sales path. Its APIs include EOD adjusted/unadjusted
prices, distributions/splits, FX and fundamentals, with stable permaTicker
identifiers useful for symbol changes.

**Coverage concern:** The official fundamentals documentation describes 5,500+
US equities/ADRs and a separate add-on. That may be insufficient for Portfyl's
European fundamental-research ambitions even if price coverage is acceptable.

**Licensing warning:** The USD 50/month commercial plan is internal-use only.
Tiingo's terms and developer documentation require a separate redistribution
licence for data shown through a website/app to users. Portfyl must not budget
using the internal-commercial number.

Official evidence:

- [Pricing](https://www.tiingo.com/about/pricing)
- [General API/licensing documentation](https://www.tiingo.com/documentation/general)
- [Terms of use](https://api.tiingo.com/tos/)
- [Developer and redistribution programme](https://www.tiingo.com/documentation/appendix/developers)
- [EOD data](https://www.tiingo.com/documentation/end-of-day)
- [Fundamentals coverage](https://www.tiingo.com/documentation/fundamentals)

## Preliminary conclusion

Request comparable written quotes from EODHD and Twelve Data first. Include
Tiingo as a licensing-transparency and price comparison, but require a clear
answer on European fundamentals before investing in an integration trial.

The proposed Investor EUR 4.99 / Pro EUR 7.99 prices may be below the viable
floor once commercial display, exchange and per-user fees are included. Do not
reduce the requested rights to preserve the headline price; adjust features,
delay level, user limits or pricing after quotes arrive.

## Draft enquiry (not sent)

```text
Subject: Commercial market-data display licence for EU portfolio analytics SaaS

Hello,

Portfyl is an EU-hosted multi-tenant portfolio analytics SaaS for self-directed
Trading 212 and Interactive Brokers users. We are preparing a 20-50-user private
beta and need delayed/EOD equity and ETF prices, FX, corporate actions,
fundamentals and calendars for US and relevant European listings.

Data would be requested server-side, normalized/cached in EU infrastructure,
displayed to authenticated customers and used for derived portfolio analytics.
We do not resell a raw feed or expose a public market-data API. We may include
derived figures and limited displayed observations in reports and minimum facts
in an AI-generated explanation.

Please complete or respond against the attached requirements matrix, especially
the exact rights for customer display, browser transmission, multi-tenant cache
and storage, derived analytics, reports/AI, exchange fees, DPA/regions and
termination. Please quote both the private-beta stage and the next production
tier, with every exchange, professional-user, add-on and overage fee itemized.

Thank you.
```

Sending this enquiry is a representational external action and is deliberately
not performed by this repository task.
