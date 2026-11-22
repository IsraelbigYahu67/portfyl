---
type: hub
layer: frontend
tags: [arch/hub]
generated: false
---
# Frontend structure

The frontend is a React 18 + Vite 6 single-page app in `frontend/src`. It uses TailwindCSS, `recharts` for charts, `@tanstack/react-query` for server data, `axios` for HTTP and `react-router-dom` 7 for routing. In production the build output (`frontend/dist`) is served by FastAPI from the same origin, so `/api` calls need no CORS. The app is translated into nine languages, and the cloud build also prerenders the public marketing pages for search engines.

## How it works
- Entry: [[src.main]] mounts [[src.Root]] (providers, public pages), which renders [[src.App]] (the signed-in app and its routes). The authenticated route list lives in [[routes (folder)]].
- All HTTP goes through [[src.api]]. Its axios interceptor adds `portfolio_id` (a UUID) from the active portfolio to every request, so call sites never pass it. It also adds the `X-Workspace-ID` header once a workspace is resolved and `X-CSRF-Token` on mutating methods (the token is kept in memory only).
- The interceptor skips `portfolio_id` for `PORTFOLIO_AGNOSTIC_PREFIXES`: `/portfolios`, `/market`, `/watchlists`, `/settings`, `/auth`, `/capabilities`, `/test-plans`, `/billing` and `/broker-requests`. A new cross-portfolio endpoint must add its prefix there.
- Login state lives in [[auth.AuthProvider]] (Firebase sign-in, then a Portfyl session); see [[Auth and sessions]].
- Edition differences are resolved at build time: Vite maps `@edition-manifest` to [[editions.local]] or [[editions.cloud]]. See [[Edition boundary]].
- Folders: `pages` (one file per screen, for example [[pages.Dashboard]]), `components` (reusable pieces, grouped in folders such as [[components.ui (folder)]]), `lib` (pure helpers such as [[lib.format]]), `hooks` (React hooks such as [[hooks.useStockDetail]]).
- i18n: [[i18n (folder)]] holds the provider, the language list and the dictionaries for cs, de, es, fr, it, nl, pl and pt. English is the source text written in the code, so there is no English dictionary.
- Look and feel: `DESIGN.md` ([[DESIGN (md)]]) is the source of truth (warm Clay palette, chart colors, motion rules). Theme tokens come from [[lib.themeTokens]] and `index.css`. Never hardcode hex colors.
- Public pages are listed only in `seo/publicPages.js` ([[seo (folder)]]). `npm run build:cloud` prerenders them through [[src.entry-prerender]] into `dist/prerendered/`, with `robots.txt` and `sitemap.xml`.
- Legacy: `sb_*` localStorage keys keep the old Snowball prefix on purpose, so users keep their preferences.

## Key code
- [[src.main]]: browser entry point (hydrates prerendered HTML when present).
- [[src.Root]]: top-level providers and public routing.
- [[src.App]]: signed-in shell and routes.
- [[src.api]]: axios client and interceptors.
- [[pages.Dashboard]], [[pages.Import]], [[pages.Settings]], [[pages.Pricing]], [[pages.Onboarding]], [[pages.Welcome]]: central pages.
- [[components.ui (folder)]]: shared UI primitives.
- [[components.layout (folder)]]: sidebar, shell and navigation.
- [[components.settings (folder)]]: settings sections.
- [[lib.routes]]: route constants.
- [[lib.displayCurrency]]: display-currency conversion.
- [[src.errorMonitoring]]: browser error reporting.

## Related hubs
- [[Portfyl]], [[Backend]], [[Edition boundary]], [[Auth and sessions]], [[Onboarding and CSV import]], [[Billing and Stripe]], [[Testing]]

## Docs
- [[DESIGN (md)]]: the live design system (read before any UI change).
- [[superpowers/plans/2026-11-09-portfyl-seo]]: prerender and public-page SEO plan.
- [[superpowers/plans/2026-11-06-portfyl-app-languages]]: the nine-language plan and glossary.
- [[superpowers/specs/2026-10-23-clay-ui-audit]]: audit of the Clay UI.
