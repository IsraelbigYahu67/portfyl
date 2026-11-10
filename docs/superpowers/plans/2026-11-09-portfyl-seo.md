# Portfyl SEO — research and plan

Date: 2026-11-09. Status: **Wave 1 implemented on branch
`claude/dreamy-gates-mlpwia` (not merged, not deployed); Wave 0 needs the
owner (live access, Cloudflare and search-console accounts).** The owner
accepted every recommendation in §7 (O1–O6) on 2026-11-09. This plan
covers only the public marketing host `portfyl.com`. The tracker on
`app.portfyl.com` and every authenticated route stay out of search on purpose.

Read first: `CLAUDE.md`, `DESIGN.md` (any landing/content page is a frontend
change), `docs/operations/2026-09-10-public-landing.md` (how `/` is served and
which paths Cloudflare Access protects), and the monetization plan
`2026-09-01-portfyl-saas-monetization.md` (Tax Report and Screener are never
advertised in cloud; market-data display rights are still open).

## 1. Goal

Organic search becomes a steady, cheap acquisition channel for the cloud
edition. In order:

1. Searches for the brand ("portfyl") land on a page that explains the product
   in the searcher's language.
2. Czech investors searching for a portfolio/dividend tracker that works with
   their broker (Trading 212 first) find Portfyl. Czech is the market with the
   weakest competition (see §3).
3. Later, English-speaking Trading 212 users in the EU/UK, then German
   speakers, who face strong local competition.

Non-goals: ranking the app itself, public per-stock pages before market-data
rights allow it (§5.6), tax content (§5.5), paid search.

## 2. Audit of the current state (code as of 2026-11-09)

| # | Finding | Where | SEO impact |
|---|---|---|---|
| A1 | **The language gate hides all content from crawlers.** On a first visit `/` shows only "Vítejte. Welcome. Willkommen. Choose your language." The real landing copy renders only after a click, or when `portfyl_landing_language` is in localStorage. Crawlers never click and start with empty storage. | `frontend/src/pages/Welcome.jsx` (state `language`, `chooseLanguage`) | **Blocker.** Google and Seznam index a three-word chooser, with no product description, keywords or links. |
| A2 | **Three languages share one URL.** CZ/EN/DE swap on the client at `/`. | `Welcome.jsx`, `welcomeCopy.js` | Only one version can be indexed, and hreflang is impossible. |
| A3 | **Empty HTML shell, client-side rendering only.** `index.html` holds just `<div id="root">`, so every word needs JavaScript. | `frontend/index.html`, `frontend/src/Root.jsx` | Google renders it late, if at all. SeznamBot's JS rendering is reported to be weak (§3.2), and most AI crawlers don't run JS. |
| A4 | **No head metadata.** It has `<html lang="en">`, `<title>Portfyl</title>`, and no description, canonical, hreflang, Open Graph/Twitter card or structured data. The page title and `lang` are set from JS only after a language is chosen. | `frontend/index.html`, `Welcome.jsx:71-75` | Weak snippets, no share previews, and the wrong language signal for Czech. |
| A5 | **No `robots.txt` or `sitemap.xml`.** The SPA fallback answers every unknown path, these two included, with `index.html` and HTTP 200. | `backend/main.py` `_spa_file_response` / `spa_fallback`; `frontend/public/` | Crawlers get HTML where they expect robots/sitemap, and nothing tells them which URLs exist. |
| A6 | **Soft 404s.** An unknown path on `portfyl.com` (e.g. `/foo`) returns 200 and boots the tracker, which then sends the visitor to login. Paths Cloudflare Access covers return 302. | `Root.jsx` (falls through to `<Tracker />`), `main.py` | Junk URLs can be indexed as duplicates of the login page. |
| A7 | **There is only one marketing page.** Everything public is `/` (navigation by in-page anchors), `/terms`, `/privacy` and `/demo`. | `Root.jsx`, `lib/routes.js` | Nothing exists to rank for anything but the brand. |
| A8 | **Copy promises less than the product does, on purpose.** Public copy names Trading 212 and CSV only. IBKR claims were removed on 2026-09-11, and the Degiro/XTB/Schwab/Fidelity/eToro importers run on synthetic fixtures (`CLAUDE.md`). | `welcomeCopy.js` | Broker pages may only be built for brokers we can honestly claim (§5.3). |
| A9 | ~~Landing images are heavy.~~ **Corrected during Wave 1:** the four live screenshots are 17–30 kB JPEGs (despite the `.png` name) with explicit sizes; only two unused 300 kB concept PNGs were heavy, and they are deleted. | `frontend/public/landing/` | None left; confirm LCP with Lighthouse in S0. |
| A10 | **The app host is correctly private.** `app.portfyl.com` is behind Access as a whole host, and tracker paths on `portfyl.com` are behind path-scoped Access. | Cloudflare (outside this repo) | Good. Add `noindex` defensively anyway (§5.2). |
| A11 | **The CSP allows `script-src 'self'` only.** | `backend/security_headers.py` | JSON-LD in a `<script type="application/ld+json">` data block doesn't execute, so CSP doesn't block it and Google reads it. Prerendered HTML must still add **no inline executable** scripts. |
| A12 | **Live checks are pending.** This research ran in a sandbox that could not reach `portfyl.com` (all requests timed out), so live headers, Cloudflare bot settings and indexing status are unverified. | — | Task S0 re-checks them. |

**Conclusion.** Before content, the site needs crawlable, language-specific
HTML. Writing articles before A1–A6 are fixed would be wasted effort.

## 3. Research findings

### 3.1 Search engines in the target markets

- **Czech Republic:** Google has about 81% share and Seznam about 11–13%
  (StatCounter 2025; other 2025 estimates give Seznam 11–15%). Seznam's share
  is slowly falling. CZ is still the one European market where a domestic
  engine keeps a double-digit share, so **Seznam is worth supporting**, and it
  costs little once HTML is prerendered.
- **DE/EN markets:** Google dominates. Bing matters indirectly, because its
  index feeds several AI assistants' search.

### 3.2 JavaScript rendering

- Google renders JS, but in a deferred second pass. Third-party guidance
  agrees that pure client-side rendering is the riskiest option and that
  **SSR or build-time prerendering** gives crawlers real HTML on the first
  request.
- **SeznamBot:** no official Seznam documentation was found. Third-party
  guides say its JS rendering is weak and a CSR-only React app "may simply not
  be indexed". Treat prerendering as mandatory for Seznam.
- **AI crawlers** (ChatGPT search, Perplexity, Claude) mostly do not execute
  JS. One team reports their marketing pages were "an empty HTML shell" for AI
  crawlers until they prerendered.
- Prerendering options for a Vite + React Router 7 SPA:
  (a) a custom build step using `react-dom/server` plus `hydrateRoot`
  (the Prestruct project is an example of this pattern);
  (b) React Router framework mode's `prerender` option, which would mean
  migrating the router setup;
  (c) `vite-ssg`, `vite-plugin-prerender` or `react-snap`-style headless
  snapshots. One warning applies to all: pages missing from the prerender
  route list **silently** drop out, so the list must be tested.

### 3.3 Multilingual setup (Google guidance)

- Give each language its own URL, with reciprocal, absolute hreflang that
  includes a self-reference and `x-default`.
- **Don't auto-redirect by guessed language** (Accept-Language or IP). Offer
  a visible language switcher. If the root URL redirects, it must be the
  `x-default`.
- Google detects a page's language from its content, not from `lang` or
  hreflang. Each language version therefore needs real translated content,
  not a translated title over English text.
- Each language edition needs human review. A case study of a programmatic
  stock site found Google rejected non-English pages with mismatched language
  as low quality.

### 3.4 Competition

- **EN:** Sharesight (has a Trading 212 partner page and blog), Snowball
  Analytics (help article "import Trading 212"), Delta, Portseido (has a
  `/dividend-tracker/trading-212` page), AllInvestView (has a "Trading 212
  portfolio tracker" page and import guide), Portfolio Dividend Tracker,
  Stock Unlock. **The common pattern:** a broker-specific tracker landing
  page, a step-by-step CSV export/import guide, and "X alternatives" or
  "X vs Y" comparison pages. Several comparison sites are run by vendors, so
  the space is crowded but formulaic.
- **DE:** Parqet and getquin dominate. Semrush data suggests much of their
  search traffic is branded/navigational (Parqet: mostly direct visits,
  Google about 5%). getquin has per-stock forum pages (user-generated
  content). This market is hard to break into, so it comes last.
- **CZ:** no established Czech-language tracker with Trading 212 support was
  found. Holdista, aimed at CZ/SK investors, is pre-launch and focused on
  Degiro/XTB. Czech finance media (e15, money.cz, banky.cz, dauc.cz) own the
  informational queries (taxes, how to invest) but don't sell a tracker.
  **Czech commercial-intent queries look open.** That is Portfyl's best entry
  point.
- **Trading 212 community forum:** users repeatedly ask for dividend and
  portfolio tracking. Several indie trackers promote themselves there, which
  shows demand and also shows the forum is already full of self-promotion.

### 3.5 Quality and policy constraints

- **YMYL:** finance content is "Your Money or Your Life". Raters look for a
  clear operator identity, author expertise, sources and accuracy. E-E-A-T is
  a rater framework, not a single ranking switch, but it shapes what ranks for
  money topics.
- **Scaled content abuse** (spam policy since March 2024, still enforced in
  2026): many template pages made mainly to rank violate it, whether a human
  or an AI wrote them. **Auto-generated per-ticker or per-broker pages with
  thin unique value are out.**
- **Rich results:** Google limited FAQ rich results to authoritative
  government/health sites and dropped HowTo rich results in 2023. FAQ/HowTo
  markup won't produce rich snippets for us. Organization, WebSite and
  SoftwareApplication markup still help with entity understanding.

### 3.6 AI search (AI Overviews, AI Mode, assistants)

- Google's 2026 guidance: optimizing for generative AI search *is* SEO.
  There's no separate system, no special markup is required, and **`llms.txt`
  isn't used** by Google Search (Mueller called it "a temporary crutch").
  Pages must be indexed and snippet-eligible, and original "non-commodity"
  content is the lever.
- No major AI provider has confirmed reading `llms.txt`. It is optional and
  low priority.
- **Cloudflare** has blocked known AI crawlers by default on new zones since
  July 2025, and can manage `robots.txt` with Content Signals
  (`search=yes, ai-train=no`). That setting has to be an explicit decision,
  because blocking AI *search* crawlers removes Portfyl from assistant
  answers.

## 4. Strategy decisions

| Decision | Recommendation | Why |
|---|---|---|
| Primary market | Czech first, then English, then German. | Open SERPs in CZ; the owner can write and review Czech copy; DE is saturated. |
| URL structure | Subdirectories on `portfyl.com`: `/` = Czech, `/en/`, `/de/`. Content pages under each, e.g. `/sledovani-portfolia-trading-212`, `/en/trading-212-portfolio-tracker`. `x-default` → `/en/`. | One domain keeps all link equity. CZ is the primary market, so it gets the root. **Owner decision needed (O1).** |
| Language chooser | Replace the full-screen gate with a non-blocking switcher in the header, plus at most a one-time *suggestion* banner when the browser language differs. Never auto-redirect. A saved choice may show the banner but must not change what a URL serves. | A1 and Google's redirect guidance. Each URL always returns the same language. |
| Rendering | Build-time prerender of **public routes only**, via a custom `react-dom/server` step (option a). Tracker, demo internals and auth stay CSR. | No router migration and no new runtime dependency; `react-dom/server` is already installed. |
| Indexable set | Language landings, content pages (§5.3–5.4), legal pages (`/terms`, `/privacy` per language). `/demo` is `noindex` until market-data rights cover public display (O3). Everything else is `noindex` or 404. | Keeps the index clean (A6, A10). |
| AI crawlers | Allow search/answer crawlers (Googlebot, Bingbot, SeznamBot, OAI-SearchBot, PerplexityBot, Claude-SearchBot). Training crawlers are the owner's call (O4). | Visibility in AI answers without giving consent to training by default. |

## 4a. Wave 1 — what was built (2026-11-09)

- **One URL per language** (S2). `/` renders Czech, `/en/` English, `/de/`
  German, from the path alone (`lib/routes.js` `LANDING_PATHS`,
  `landingLanguage`). The full-screen language gate is gone. The header
  switcher is the same `SegmentedControl`, now rendering `<a href hreflang>`
  links (new `href` option), and a click saves the choice. A dismissible
  banner offers the visitor's own language (saved choice, else browser
  language; Slovak reads Czech, unsupported languages read English). It
  appears only after mount, so crawlers never see it, and it never
  redirects. The language is saved only on an explicit action (switcher,
  banner, demo CTA), because the demo, legal pages and app read it. On
  landing URLs the consent banner follows the page language.
- **Build-time prerender** (S4). `npm run build:cloud` runs
  `scripts/prerender.mjs` after the client build:
  - it SSR-builds `src/entry-prerender.jsx` and renders the real `<Root>`
    for each page in `src/seo/publicPages.js` (`renderToPipeableStream`,
    `onAllReady`);
  - it writes `dist/prerendered/{,en/,de/}index.html` with the title,
    description, canonical, reciprocal hreflang plus `x-default` → `/en/`,
    Open Graph/Twitter tags, JSON-LD (`Organization`, `WebSite`,
    `SoftwareApplication`, no `offers`) and the page chunk's CSS/modulepreload
    links;
  - it writes `dist/robots.txt` (training crawlers disallowed, search and
    AI-answer crawlers allowed, private paths disallowed, `Sitemap:`) and
    `dist/sitemap.xml`;
  - the build fails if a page renders without an `<h1>`, renders the loading
    fallback, or contains an inline `<script>`.

  `dist/index.html` stays the empty shell. `main.jsx` hydrates only
  prerendered landing URLs off the tracker host; anything else starts clean.
  Open Graph images are `public/og/portfyl-{cs,en,de}.jpg`: 1200×630
  screenshots of the prerendered hero with JS disabled. Regenerate them when
  the hero changes.
- **Backend serving** (S3, `backend/spa_serving.py`):
  - a prerendered page is served only for a non-tracker host and is
    indexable only on `portfyl.com`;
  - `/en` and `/de` redirect 301 to `/en/` and `/de/`;
  - every app-shell response carries `X-Robots-Tag: noindex, nofollow`, and
    so does every response on another host (`app.portfyl.com`, `*.run.app`,
    localhost);
  - another host gets a `robots.txt` that disallows everything;
  - `prerendered/` and `.vite/` are never served directly;
  - the SPA route now also answers `HEAD`.

  The host comes from `X-Forwarded-Host` (set by the app-host Worker), else
  `Host`.
- **Deferred from S3: true 404 status codes for unknown paths.** The frontend's
  routes live in several places (App.jsx auth routes, the authenticated route
  registry, the edition manifests, the demo router), so a generated route
  list needs a small refactor first. Until then, unknown paths get the
  `noindex` shell, which keeps them out of the index. That covers the SEO
  risk; only crawl hygiene is left.
- **S5:** nothing heavy was left to optimise (see A9). Lighthouse numbers come
  from the live site in S0.
- **Legal pages** (`/terms`, `/privacy`) are not prerendered and stay
  `noindex` while they are lawyer-review drafts. Prerender them, with
  path-based language URLs, once the texts are final.
- **Deploy notes.** No Cloudflare Access change is needed: `/en/`, `/de/`,
  `/og/*`, `/robots.txt` and `/sitemap.xml` are outside the protected path
  list, the same as `/`. After deploying, check `curl -I` for `/`, `/en`,
  `/en/`, `/dashboard` and `https://app.portfyl.com/robots.txt` against the
  rules above. Then submit `https://portfyl.com/sitemap.xml` in S1.

## 5. Work plan

The tasks are grouped into waves. Tasks inside a wave touch disjoint files (see
`CLAUDE.md` → "Parallel session safety"). Hotspots: `frontend/package.json` is
untouched unless O2 picks a library, and `backend/main.py` is owned by S3 only.

### Wave 0 — verify and register (no code)

- **S0. Live baseline.** From a machine that can reach `portfyl.com`:
  `curl -sI` on `/`, `/robots.txt`, `/sitemap.xml`, `/foo`, `/dashboard`,
  `https://app.portfyl.com/`. Record status codes and headers. Run `site:portfyl.com` on
  Google and Seznam. Run Lighthouse on `/` (mobile). In Cloudflare, note Bot
  Fight Mode, AI Crawl Control/AI bot blocking, managed `robots.txt` and
  Content Signals settings. Make sure Bot Fight Mode does not challenge
  verified search bots. Save the results to
  `docs/operations/2026-11-xx-seo-baseline.md`.
- **S1. Register properties.** Google Search Console as a **domain property**
  (DNS TXT via Cloudflare), Bing Webmaster Tools (it can import from GSC) and
  Seznam Webmaster (meta-tag or file verification). Decide on IndexNow, which
  Bing supports. Whether Seznam supports it is *unverified*, so check first.

### Wave 1 — crawlable foundation (parallel tasks, disjoint files)

- **S2. Language URLs and non-blocking chooser** (`frontend/src/pages/Welcome.jsx`,
  `Welcome.css`, `welcomeCopy.js`, `frontend/src/lib/routes.js`,
  `frontend/src/Root.jsx`, tests).
  - Treat `/`, `/en`, `/de` (with or without the trailing slash) as public home
    routes. The language comes from the path, not from localStorage.
  - Turn the gate into a header switcher made of real `<a href>` links to the
    other language URLs. Crawlers follow links, not buttons. Keep the a11y
    focus behaviour. Keep `portfyl_landing_language` as a preference that only
    drives the suggestion banner.
  - Legal links follow the page language (`/terms?lang=` → decide in S4
    whether legal pages get path-based language URLs too).
  - Follow DESIGN.md (switcher uses `SegmentedControl` or the existing pill
    links; no new colors).
- **S3. Backend serving rules** (`backend/main.py`, a new
  `backend/seo_routes.py` if it helps, `backend/tests/test_spa_seo.py`).
  - `_spa_file_response`: serve prerendered `dist/<path>/index.html` when it
    exists (e.g. `/en/` → `dist/en/index.html`). Keep `Cache-Control: no-cache`.
  - Send `X-Robots-Tag: noindex` on every SPA-shell response that is **not** a
    prerendered public page, and on every response when the host is
    `app.portfyl.com`.
  - Serve `robots.txt` and `sitemap.xml` as real files (generated by S4) with
    correct content types, never the HTML fallback.
  - **Real 404s on the marketing host.** Unknown paths on `portfyl.com` that are
    neither a public page nor a known tracker route return status 404 with the
    shell, which renders a "not found" page. The tracker route list must come
    from one source (export from `frontend/src/routes`, or a generated JSON
    written by the build). Never hand-maintain a second copy.
  - Fast unit tests cover each rule. Verify `test_event_loop_not_blocked.py`
    still passes (these handlers stay sync `def`).
- **S4. Prerender build step** (new `frontend/scripts/prerender.mjs`, new
  `frontend/src/entry-prerender.jsx`, `frontend/src/seo/` for head data,
  `frontend/vite.config.js`, `frontend/src/main.jsx` for `hydrateRoot` on
  prerendered pages, and the `build:cloud` script line in
  `frontend/package.json`. **package.json is a hotspot: only S4 touches it in
  this wave.**)
  - Vite SSR build of `entry-prerender.jsx` → for each public route, render
    to string and write `dist/<route>/index.html`, injecting into `<head>`
    the title, meta description, canonical, the full hreflang set (+ `x-default`),
    Open Graph and Twitter tags, `og:image` (1200×630 PNG per language,
    stored in `public/og/`), `<html lang>`, and JSON-LD (`Organization`,
    `WebSite`, `SoftwareApplication` without `offers` until pricing is
    public). The build fails if a route in the public list renders empty or
    without a title, description or canonical.
  - Render must not touch `window`/`localStorage` (guard in `Welcome.jsx`).
    Analytics and the consent banner initialise only on the client.
  - Generate `sitemap.xml` (with `xhtml:link` hreflang alternates and
    `lastmod`) and `robots.txt` (`Disallow` for `/api/`, `/demo` until O3, the
    tracker paths; `Sitemap:` line) from **the same public route list**.
  - Local edition (`npm run build`) does not prerender and does not emit a
    sitemap. Cloud only.
  - Verify with `npm test`, `npm run test:cloud`, `npm run build`, and
    `npm run build:cloud`, then `curl` the built HTML. The copy must be visible
    with JS disabled.
- **S5. Core Web Vitals on the landing** (`frontend/public/landing/`,
  `Welcome.jsx` image tags only, after S2 merges or in S2's branch).
  Convert the screenshots to AVIF/WebP with a PNG fallback, add explicit
  `width`/`height`, give the hero `fetchpriority="high"`, and lazy-load the
  gallery. Target: mobile LCP < 2.5 s, CLS < 0.1 in Lighthouse.

### Wave 2 — Czech content that matches real demand

Every page is prerendered (S4 route list), has one H1, unique title and
description, internal links to the landing and `/demo`, and a short "not
investment advice" note where it touches decisions. Each page is written or
reviewed by a person, never bulk-generated (§3.5).

- **S6. Trust pages.** "O nás" (who runs Portfyl, company details already
  required by the legal docs, contact), a methodology page (how performance,
  TWR/XIRR, FX to CZK and dividends are calculated, with links to the code-backed
  definitions), and a data-sources and privacy summary. These pages carry the
  YMYL trust signals that the other pages link to.
- **S7. Broker page: Trading 212** (CZ). "Sledování portfolia a dividend
  z Trading 212": what Portfyl shows, how the sync and CSV import work, and
  limits. Write it from the real flow, with screenshots from the demo
  portfolio.
- **S8. Import guide: Trading 212 CSV export** (CZ). Step by step. Competitor
  guides show what users trip over: selecting all data types (orders,
  dividends, transactions), the export period limit, currencies, and pies.
  Verify each step against a real export before publishing (plan Task 0 in
  the broker-integrations plan).
- **S9. Feature pages** (CZ): dividend tracking ("sledování dividend"),
  performance vs benchmark, allocation (sectors, currencies, countries).
  Never mention Tax Report or Screener (cloud boundary).
- **S10. Explainers that only an analytics product can write well** (CZ):
  "TWR vs XIRR — jak počítat výnos portfolia", "yield on cost", "jak
  porovnat portfolio s indexem". These are "non-commodity" answers with
  worked examples drawn from the methodology page.

Keyword validation runs before each page is written: check demand and wording
in Google Search Console (after S1, impressions show which queries already
appear), Seznam's suggest/Sklik keyword tool, Google autocomplete, and
competitor page titles. Record the target query per page in the page's head
data file (`frontend/src/seo/pages/*.js`) so the intent stays reviewable.

### Wave 3 — English, then German, and links

- **S11. EN versions** of S6–S10. Lead with "Trading 212 portfolio tracker" and
  the import guide, because the English pages compete with Sharesight,
  Portseido and AllInvestView on exactly those pages. Differentiate on depth
  (worked examples, methodology) and EU specifics (multi-currency, CZK/EUR).
- **S12. Comparison pages**: "Portfyl vs Snowball / Sharesight / Parqet /
  getquin" and "alternatives". These must be factual, dated, sourced and
  fair, and updated when a competitor changes pricing. A wrong claim on a
  YMYL comparison page costs trust.
- **S13. DE versions**, once EN pages show traction.
- **S14. Earned links and mentions** (not code): ask the comparison
  directories that list trackers (AllInvestView, FindMyMoat, freenance and
  similar) to add Portfyl; Product Hunt launch at public launch; Czech
  investing communities and media (PR around the launch, a guest article on
  portfolio performance maths). Post in the Trading 212 forum only where it
  answers a question. No link buying.

### Wave 4 — only after Workstream A clears market-data rights

- **S15. Per-instrument or dividend pages.** These only go ahead if the vendor
  agreement explicitly allows **public, unauthenticated display** (the vendor
  requirements doc already flags that public display may be quoted separately).
  Each page must add something a ticker site doesn't, such as a
  dividend-history explanation or Portfyl-specific analysis. Otherwise it is
  scaled-content risk. Start with a small hand-picked set and measure.
- **S16. Index `/demo`.** This only happens if its data is synthetic or the
  rights cover public display. Then remove its `noindex` and `Disallow`.

## 6. Measurement

- **Search Console (Google, Bing, Seznam):** indexed pages, impressions,
  clicks and CTR per page and query, plus coverage errors. Review weekly in
  the first month after Wave 1, then monthly.
- **PostHog** (consent-gated, as today): add a landing-page property for the
  referrer class (organic search, AI assistant, direct, social), then funnel:
  organic landing → demo started → register → first import. Do not add
  identifiers to URLs.
- **Targets** (set again after S0's baseline):
  - All public URLs are indexed in Google and Seznam within 4 weeks of Wave 1.
  - "portfyl" is position 1 in Google and Seznam.
  - Each Wave 2 page has non-brand impressions within 8 weeks.
  - Mobile Lighthouse SEO is 100 and Performance ≥ 90 on every public page.

## 7. Open decisions for the owner

- **O1.** Should `/` be Czech, with `/en/` and `/de/` beside it (recommended),
  or should every language get a prefix (`/cs/`, `/en/`, `/de/`) with `/` as
  an `x-default` chooser? The second option keeps a neutral root, but the
  primary market loses the shortest URL and the root page is thin.
- **O2.** Should prerendering use a custom `react-dom/server` script
  (recommended: no new dependency), or adopt a library or React Router
  framework mode?
- **O3.** Does `/demo` stay `noindex` until market-data rights for public
  display are confirmed (recommended)?
- **O4.** Which AI crawlers to allow: search/answer crawlers only
  (recommended), or training crawlers too? This is configured in Cloudflare
  and `robots.txt`.
- **O5.** Who signs the content (YMYL author identity), and is the owner
  comfortable being named on the "O nás" page?
- **O6.** Should the landing keep saying "Již brzy" (coming soon) once SEO
  starts bringing traffic? A waitlist or demo CTA converts organic visitors
  better than a dead end.

## 8. Rejected or deferred ideas

- **Tax content** ("daňové přiznání akcie Trading 212") has high volume, but
  Tax Report is permanently excluded from cloud, Czech media already own these
  results, and inaccurate tax advice is a YMYL liability. Not planned.
- **FAQ/HowTo schema for rich results.** Google no longer shows these rich
  results for sites like ours (§3.5). Plain FAQ text on the page is fine.
- **`llms.txt`.** Google doesn't use it and no AI provider has confirmed it.
  Optional, at most a 30-minute task after Wave 2.
- **Dynamic rendering (serving different HTML to bots).** Google discourages
  it, and it risks being treated as cloaking. Build-time prerender serves the
  same HTML to everyone.
- **Machine-translated language versions without review** (§3.3).

## 9. Sources

Researched 2026-11-09. Most are secondary sources; the official Google
documents are listed where found.

- Google, localized versions / hreflang: https://developers.google.com/search/docs/advanced/crawling/localized-versions
- Google, multi-regional and multilingual sites: https://support.google.com/webmasters/answer/182192
- John Mueller on hreflang and root redirects (x-default): https://www.seroundtable.com/john-mueller-offers-hreflang-google-seo-advice-35052.html
- StatCounter, search engine share in Czechia: https://gs.statcounter.com/search-engine-market-share/all-globe/czech-republic
- Statista, Czech search engine share 2015–2024: https://statista.com/statistics/1342969/czechia-market-share-of-search-engines
- Czech SEO and SeznamBot JS rendering (third-party): https://x-cmd.com/seo/czech
- Seznam crawling control (robots/sitemap): https://o-seznam.cz/napoveda/vyhledavani/en/crawling-control/
- Seznam Webmaster setup (older, third-party): https://www.aitom.cz/en/blog/2017/05/18/seznam-webmaster-co-umi-a-jak-jej-nastavit/
- Martin Splitt on rendering (SEJ): https://www.searchenginejournal.com/how-rendering-affects-seo-takeaways-from-googles-martin-splitt/537023/
- JS SEO for e-commerce (CSR is the riskiest choice): https://visionary-marketing.co.uk/blog/javascript-seo-ecommerce
- Per-route HTML without SSR for a React SPA: https://luo.app/blog/per-route-html-without-ssr
- React Router pre-rendering: https://reactrouter.com/how-to/pre-rendering
- Prestruct (Vite + React prerender pattern): https://github.com/dhaupin/prestruct
- Google's generative AI search guidance, summary (Semrush): https://www.semrush.com/blog/google-publishes-generative-ai-search-guide/
- "Google says GEO is SEO": https://evolvagency.io/learn/generative-search/google-says-geo-is-seo
- Cloudflare blocks AI crawlers by default: https://www.deeplearning.ai/the-batch/cloudflares-web-crawler-flare-up
- Cloudflare Content Signals Policy: https://www.searchengineworld.com/cloudflare-enters-the-robots-txt-fray-with-a-content-signals-policy-for-ai-bots
- Scaled content abuse and programmatic pages: https://www.digitalapplied.com/blog/programmatic-pages-audit-scaled-content-policy
- YMYL / E-E-A-T for finance: https://www.accuracast.com/news/finance/e-e-a-t-financial-services-seo-guide/
- Fintech programmatic SEO notes: https://usepassionfruit.com/blog/fintech-seo
- Competitors, Trading 212 pages: https://www.sharesight.com/partners/trading-212/ ,
  https://portseido-production.pages.dev/dividend-tracker/trading-212 ,
  https://www.allinvestview.com/trading-212-portfolio-tracker ,
  https://www.allinvestview.com/how-to-import/trading-212/ ,
  https://help.snowball-analytics.com/import-trading212/ ,
  https://support.delta.app/en/articles/8438960-import-csv-from-trading-212
- Competitor landscape: https://freenance.io/financial-tools/best-portfolio-tracker-eu-investors-2026-multi-broker-multi-currency/ ,
  https://www.similarweb.com/ja/website/getquin.com/competitors ,
  https://zh.semrush.com/website/parqet.com/overview
- Trading 212 community demand for trackers: https://community.trading212.com/t/trading-212-dividend-tracker/74823
- Czech tax content landscape (why tax is deferred): https://www.e15.cz/zdaneni-akcii-dividend-danove-priznani-2026
