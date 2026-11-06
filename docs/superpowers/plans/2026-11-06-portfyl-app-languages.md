# Portfyl app languages

Date: 2026-11-06. Branch: `feat/app-languages` (worktree `../portfyl-app-languages`).

## Goal

The signed-in app can be used in nine languages: Czech, English, German,
French, Spanish, Italian, Portuguese, Polish and Dutch. The user picks one as
the first onboarding step and can change it later in Settings → Preferences.

## Decisions

- **English is the source language and the key.** Code keeps its English text
  and wraps it: `t("Add your first portfolio")`. Each other language is one
  dictionary, `frontend/src/i18n/messages/<code>.js`, mapping English text to
  the translation. Missing text falls back to English. No new dependency.
- **Placeholders and styled words.** `t("Connect {broker}", { broker })`;
  sentences with emphasised words use `<b>…</b>` tags drawn by `rich()`.
- **Strings defined outside a component** (data modules, constants) are marked
  with `msg("…")` and translated where shown with `t(value)`.
- **Completeness is a test.** `src/i18n/messages.test.js` collects every literal
  `t("…")`/`msg("…")` and fails when a dictionary misses one, keeps a stale
  one, or drops a `{placeholder}`/`<tag>`. Only literal strings are found:
  never build a key with a template or concatenation.
- **Device-level preference,** like theme and currency: localStorage
  `portfyl_language`. First visit: the landing page's choice
  (`portfyl_landing_language`), then the browser's languages, then English.
  A guessed language is not saved, only a user's choice. Per-account storage
  (follows the user across devices) would need a migration; deferred.
- **Lazy dictionaries.** Each language is its own ~4 kB (gzip) chunk; the
  provider holds the first paint until it is loaded, so no flash of English.
- **Number and date formats are unchanged** (they follow the display currency,
  see DESIGN.md §8). Tying them to the language is a separate decision.
- **Backend messages** (API `detail` strings) stay English for now.
- **Legal documents** exist in English and Czech only; their links name the
  language they are in.

## Glossary: words that stay in English

Investors use these as-is, so every language keeps them (lower-case inside a
sentence where the language does that): **Dashboard, Insider** (insider
transakce → "insider transakce"), **Watchlist, ETF, ticker, broker,
benchmark, CSV, API, P/E, Flex Query, onboarding, demo**, the plan names
**Free, Investor, Pro**, theme names **Classic, Premium, Clay**, palette names,
and product/broker names. Brokers' own menu labels (Trading 212 "History",
DEGIRO "Inbox → Transactions", Trading 212 permission names) stay as the
broker shows them in English; only the surrounding sentence is translated.

## Waves

Each wave touches its own files, so waves can run in parallel sessions; the
eight dictionaries are the shared hotspot, so **one wave at a time adds keys
to them** (or each wave appends its block and the later one rebases).

1. **Done (this branch):** i18n core (`src/i18n/`), onboarding language step
   (OnboardingView, Onboarding, OnboardingPreview, onboardingBrokers,
   T212ApiGuide), Settings shell + Preferences language picker,
   SettingsSectionNav, App.jsx loading/error screens.
2. App shell: `components/layout/*` (navigation labels, drawer, top/bottom
   bar), AccountMenu, PortfolioSwitcher, RouteFallback/RouteBoundary, Toast,
   ConfirmDialog. **Blocked until** the uncommitted mobile-nav work in the
   main worktree (navigation.js, MobileNavDrawer.jsx) lands.
3. Auth pages (Login, Register, VerifyEmail, ForgotPassword), Pricing,
   UpgradePrompt.
4. Dashboard and `components/dashboard/*`, PortfolioHero, MetricCard, KpiBox.
5. Allocation, Analytics, Dividends, Cash and their components.
6. Transactions, Import (+ `components/import/*`; Import.jsx shows
   `broker.hint`, which must become `t(broker.hint)`).
7. Stock/StockDetail and `components/stock/*`, Search, Watchlists.
8. Settings cards (T212/IBKR/eToro connection cards, DataPrivacy, Discord,
   SyncSchedule, PortfolioDataManagement), `lib/` user-facing messages.
9. Local edition only: TaxReport.

Each wave: wrap strings, add the keys to all eight dictionaries (run
`npm test` and read `messages.test.js`'s list of missing keys), keep English
tests passing, run `npm test`, `npm run test:cloud`, `npm run build`,
`npm run build:cloud`, then check the pages in Czech and Polish in the browser.

## Verification of wave 1

- `npm test` 1119 passed / 1 skipped, `npm run test:cloud` 1119 passed.
- `npm run build` and `npm run build:cloud` succeed; one chunk per language.
- Browser check still to do: both browser automation profiles were held by
  other sessions on 2026-11-06.
