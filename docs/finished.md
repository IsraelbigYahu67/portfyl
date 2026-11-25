# Hotové plány

Plány, které jsou ke dni 2026-11-25 splněné na 100 %. Většina byla smazána ze `docs/superpowers/plans/`; ty, na které ještě odkazuje kód nebo dokumentace, tam zůstaly.
Plné znění každého z nich je v historii gitu (`git log --diff-filter=D -- docs/superpowers/plans/<soubor>`).

- `2026-07-03-portfyl-merge` – sloučení původních repozitářů do jednoho `main`.
- `2026-07-04-portfyl-cash-model` – model hotovosti (`cash_ledger`, `broker_cash`) a stránka Cash.
- `2026-07-08-cash-model-v2` – druhá verze modelu hotovosti s navazujícími úpravami ledgeru.
- `2026-07-13-broker-sync-schedule` – plánovaná synchronizace brokerů přes `jobs.py` (`sync_due`).
- `2026-07-24-dividend-growth-and-overview` – růst dividend (`dividend_growth.py`) a přehledová stránka.
- `2026-07-30-neumorphism-theme-style` – neumorfní styl motivu, později zahrnutý do Clay palety.
- `2026-08-01-insider-transactions-weekly-dot-chart` – týdenní bodový graf insider transakcí (`insiderWeekly.js`).
- `2026-08-30-portfyl-premium-redesign` – Premium/Clay redesign popsaný v `DESIGN.md` a `themeTokens.js`.
- `2026-09-01-portfyl-multiuser-foundation` – Workstreamy B a C: PostgreSQL s Alembicem, Firebase identita, tenancy `User → Membership → Workspace`, UUID ID a vynucené RLS.
- `2026-09-01-portfyl-multiuser-foundation-prompt` – zadání pro Workstreamy B a C, které je splněné.
- `2026-09-03-portfyl-edition-boundary` – technická hranice edic `local` a `cloud` (`edition.py`, edition manifest ve Vite).
- `2026-09-03-portfyl-job-triggering` – externí spouštění jobů přes Cloud Scheduler a stav `JobRun`.
- `2026-09-03-portfyl-secrets-jobs-prompt` – zadání pro Workstream D, které je splněné.
- `2026-09-04-portfyl-secrets-jobs` – Workstream D: šifrované secrety přes KMS a Fernet, redigované logy, dead-letter stav, audit log a zdraví subsystémů.
- `2026-09-05-portfyl-rate-limiting-implementation` – rate limiting (`rate_limit.py`, `edge_trust.py`, `RateLimitBucket`).
- `2026-09-07-portfyl-data-export-account-deletion` – export dat a smazání účtu (od 2026-11-18 okamžité).
- `2026-09-07-portfyl-onboarding-import-safety` – náhled importu s detekcí duplicit a 24hodinový bod pro vrácení.
- `2026-09-13-ux-01-data-trust` – stavy `date_status` a `income_status` u dat, kterým lze věřit.
- `2026-09-13-ux-02-platform-state` – jednotné stavy načítání a chyb (`AsyncSection`, `ErrorState`).
- `2026-09-13-ux-03-responsive-a11y` – responzivita a přístupnost (`useFocusTrap`, `MobileNavDrawer`, spodní navigace).
- `2026-09-13-ux-04-scalable-collections` – stránkování a škálovatelné seznamy (`Pagination`).
- `2026-09-13-ux-06-portfolio-insights` – rozhodovací pohledy v Allocation a Analytics.
- `2026-09-13-ux-07-product-flows` – URL záložky a produktové toky (`UrlTabs`, `Stock.tabs`).
- `2026-09-19-portfyl-demo-activation-readability-roadmap` – rozcestník tří plánů níže (demo, aktivace, čitelnost).
- `2026-09-19-portfyl-public-demo` – veřejné demo s izolací dat (`DemoBootstrap`, `demoPortfolio.js`).
- `2026-09-19-portfyl-readability-system` – systém čitelnosti písma a audit `audit:readability`.
- `2026-09-20-portfyl-cash-reconciliation` – porovnání hotovosti s brokerem (`get_reconciliation`, karta na Cash).
- `2026-10-03-t212-cash-stream` – hotovostní proud z Trading 212 ověřený na živém účtu.
- `2026-10-06-t212-sync-speed` – zrychlení synchronizace T212 na přibližně 14 s s změřenými rate limity.
- `2026-10-10-portfyl-allocation-targets` – cílové alokace (migrace 0023, `AllocationTargets.jsx`).
- `2026-10-13-portfyl-wip-completion` – dokončení rozpracovaných částí (`demo_cleanup.py`, dashboard, `code_stats.py`).
- `2026-10-16-portfyl-landing-clay` – původní Clay landing page, později nahrazená novým redesignem.
- `2026-11-14-portfyl-onboarding-flow` – první spuštění s demem, importem a připojením brokera.
- `2026-11-15-onboarding-broker-connect` – připojení brokera v onboardingu (`ConnectStep.jsx`, `useOnboardingConnect.js`).
- `2026-11-15-portfyl-own-emails-wave1` – vlastní e-maily přes Brevo, první vlna (ověření a reset hesla).
- `2026-11-16-portfyl-own-emails-review-fixes` – opravy z review vlastních e-mailů, všechny vlny A až C jsou zmergnuté.
- `2026-11-19-portfyl-free-trial-completion` – dokončení 10denního trialu Pro (banner, Turnstile, právní texty); plán je jen na nezmergnuté větvi `docs/free-trial-completion-plan`, výsledek je v `2026-11-22-free-trial-findings.md`.
- `2026-11-19-free-trial-verification` – důkazy z testů, buildů a Lighthouse pro trial (2026-11-20 a 21).
- `2026-11-21-free-trial-live-walkthrough` – ruční živý průchod scénářů a až i, všechny prošly 2026-11-22; nálezy mimo trial jsou v `2026-11-22-free-trial-findings.md`.

- `2026-09-20-t212-snapshot-first-sync` – rychlý snapshot pozic a zůstatků z Trading 212, vázání na účet přes otisk, obnovitelné běhy historie a ověření na živém účtu (21 pozic sedělo s ledgerem). Soubor plánu zůstává v docs/superpowers/plans/, protože na něj odkazují kód, migrace 0014–0016 a hub Broker importers and sync.
- `2026-09-24-t212-corporate-actions-incremental-sync` – korporátní akce z T212 (párování reverse splitů, `needs_review`), inkrementální sync a 30denní audity; všechny kroky odškrtnuté 2026-11-25 podle tabulky stavu v plánu. Soubor plánu zůstává ze stejného důvodu.

## Related

- Architecture: [[Portfyl]] · [[Deploy and operations]]
