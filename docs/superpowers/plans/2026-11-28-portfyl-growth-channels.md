# Portfyl growth channels: traffic and SEO beyond the SEO plan

Date: 2026-11-28. Status: **plan, nothing built.** The owner picked these
items on 2026-11-28 from a research pass on traffic and SEO. Everything here
is **in addition to** `2026-11-09-portfyl-seo.md` (the SEO plan). Do not
duplicate its tasks: where an item touches one of them, this plan says so and
links to it.

Read first: `CLAUDE.md`, `DESIGN.md` (calculators, the help centre and the
share card are frontend changes), the SEO plan (§3.5 YMYL and scaled-content
rules, §5 waves, §7 owner decisions), and the header comment in
`frontend/src/seo/pages/index.js` (the contract for every public content page).

## 1. Goal

Bring visitors who are likely to register to `portfyl.com`, from places other
than our own landing page, at low cost, and turn the users we have into a
source of new ones.

Picked by the owner:

| Area | Item | Section |
|---|---|---|
| Traffic | Shareable outputs (year card, read-only links) | §4 G4 |
| Traffic | Referral program | §4 G5 |
| Traffic | Communities (Reddit, Discord, Facebook groups) | §4 G6 |
| Traffic | Building in public and launch sites | §4 G7 |
| SEO | Free calculators | §4 G1 |
| SEO | Public help centre | §4 G2 |
| SEO | YouTube tutorials | §4 G3 |
| SEO | Directories and mentions that AI assistants read | §4 G8 |

**Rejected by the owner on 2026-11-28, do not plan them:** paid partnerships
with finance creators, new importers for brokers used by Czech investors
(Fio e-Broker, Revolut, Portu, Anycoin) as a growth item, original data studies
for media, and the paid-search test and channel-level PostHog campaign codes.
These may come back only if the owner asks.

Non-goals: a broad "investopedia" of economics and monetary policy (assessed
on 2026-11-28: AI answers take most of those clicks, the Czech results are
owned by finance.cz, Portu, e15 and others, and informational readers rarely
register). Tax content stays out (SEO plan §8).

## 2. Global constraints

- **Cloud edition only.** Nothing here ships in the local edition. Never
  mention or link Tax Report, Screener, Options or Polymarket (`backend/edition.py`).
- **Market-data rights are not cleared for public display** (monetization plan
  Workstream A; SEO plan §5 Wave 4). Anything a stranger can see without
  logging in (public pages, share links, videos, screenshots in posts) shows
  **no prices, quotes or market values**. Percentages and weights computed
  from the user's own ledger are the default. Exceptions need the vendor
  agreement to allow public display, checked first.
- **Honest claims only.** Public copy names only what cloud really does today.
  Importers that run on synthetic fixtures (Degiro, XTB, eToro) are not
  advertised until real exports are verified (broker-integrations plan Task 0).
- **YMYL.** Every public page is written or reviewed by a person, carries the
  "not investment advice" note when it touches a decision (the default in
  `ContentPage`), and has a dated `lastmod`. No bulk-generated pages (SEO plan §3.5).
- **Content pages use the existing registry.** Body in
  `frontend/src/pages/content/bodies/<name>.jsx`, metadata in
  `frontend/src/seo/pages/<name>.js`, one line in `CONTENT_PAGES`
  (`frontend/src/seo/pages/index.js`). Prerender, sitemap, hreflang and the
  backend read that list; never add a second route list.
- **Prerendered pages must render without JavaScript** and must not read
  `window`/`localStorage` during render. Content pages are hydrated
  (`frontend/src/main.jsx`), so interactive parts work after load, but the
  prerendered HTML must already show a useful result.
- **Analytics stay consent-gated.** New events are added to
  `frontend/src/analytics/eventContract.js` with an explicit property list.
  No identifiers in URLs except an opaque referral or share token.
  `landing_viewed` already records `utm_source`, `utm_medium` and
  `utm_campaign`. Every link we post outside the site uses the UTM convention
  in §5.
- **Backend rules from `CLAUDE.md`:** database code is plain `def`, never
  `async def`; migrations are additive and update `EXPECTED_ALEMBIC_HEAD` in
  the same change; tenant tables get forced RLS **and** application
  predicates; public IDs are UUIDs or opaque tokens, never integer keys.
- **Hotspots** (one task at a time, see §6): `frontend/src/seo/pages/index.js`,
  `frontend/src/analytics/eventContract.js`, `frontend/src/i18n/messages/*.js`,
  `backend/alembic/versions/`, `backend/database.py`, `backend/entitlements.py`,
  `backend/security_headers.py`, `docs/legal/*`.

## 3. Dependencies on the SEO plan

- **SEO Wave 0** (Search Console, Bing and Seznam Webmaster) should be done
  before G1 and G2, so each new page's impressions are visible from day one.
- **SEO Wave 1** (prerender, language URLs, `robots.txt`, sitemap) must be
  merged and deployed before any page from G1, G2 or G3 is published. The
  content-page registry already exists in the code.
- **SEO S6** (About, methodology, data sources) is the trust page the
  calculators and the help centre link to. If S6 is not live yet, G1 and G2
  link to the landing and the legal pages instead and are updated later.
- **SEO S8** (Trading 212 CSV export guide) is **owned by the SEO plan**. The
  help centre links to it and does not copy it.
- **SEO S14** (tracker comparison directories, Product Hunt, Czech media, the
  Trading 212 forum) stays in the SEO plan. G6, G7 and G8 add other places and
  must not repeat those.

## 4. Workstreams

### G1. Free calculators (SEO)

Why: an interactive tool is something an AI summary cannot replace, people
link to it, it needs no market data (the visitor types their own numbers), and
it leads straight to the product ("Calculate this from your real portfolio").

Pages (Czech first; English in a later task once the Czech ones show
impressions):

| Order | Calculator | Proposed path | Notes |
|---|---|---|---|
| 1 | Compound interest in CZK, with regular deposits | `/kalkulacky/slozene-uroceni/` | Deposit, frequency, years, expected return; table per year and a chart. |
| 2 | Impact of fees over time | `/kalkulacky/dopad-poplatku/` | TER, platform fee, FX fee; "you lose X CZK in 20 years". No broker fee table (that would need upkeep and is a data study, rejected). |
| 3 | XIRR from your own deposits | `/kalkulacky/xirr/` | Date and amount rows, end value; links to the methodology page (S6) and the TWR vs XIRR explainer (S10). |
| 4 | How much do I need to live off my portfolio | `/kalkulacky/renta/` | Withdrawal rate, inflation, horizon. Clear "this is a model, not advice" text. |
| 5 | Currency impact on a CZK return | `/kalkulacky/vliv-kurzu/` | Return in USD/EUR plus a CZK rate change. |
| 6 | Dividend reinvestment | `/kalkulacky/reinvestice-dividend/` | Yield, growth, reinvest yes/no. |
| — | Index page | `/kalkulacky/` | Lists the calculators; generated from the registry by path prefix, not hand-maintained. |

Build rules:

- Pure calculation functions in `frontend/src/lib/calculators/<name>.js` with
  Vitest tests, including edge cases (zero return, negative return, one
  period, XIRR with no sign change, which must show an error and not a number).
- The body component renders a **worked example with default inputs** in the
  prerendered HTML (the table and a sentence with the result), so crawlers and
  no-JS visitors see a real answer. Inputs become editable after hydration.
- Inputs are plain form fields with labels, CZK formatting from
  `frontend/src/lib/format.js`, and `inputmode="decimal"`. Charts use the
  DESIGN.md series colors in order. No new colors.
- Each page has a short explanation of the formula (written by a person),
  links to the related explainer, and one call to action into the demo or
  registration. Nothing is sent to the backend; nothing is stored, except
  optionally the last inputs in `localStorage` as a per-visitor convenience,
  wrapped in try/catch.
- Analytics: one new event `calculator_used` with `calculator` and `language`,
  fired once per page view after the first change. Never the input values.
- Keyword check before each page: Sklik keyword tool, Google autocomplete and,
  once SEO Wave 0 is done, Search Console. Record the chosen query in
  `targetQuery`.

Done when: calculators 1–3 are live in Czech, each has unit tests, renders a
result with JavaScript off, and has non-brand impressions in Search Console
within 8 weeks.

### G2. Public help centre (SEO)

Why: many small how-to queries ("how to import dividends", "why my return
differs from the broker's"), each a small page that catches long-tail search
and saves support time.

- Paths: `/napoveda/<slug>/` (cs), `/en/help/<slug>/`, `/de/hilfe/<slug>/`,
  with an index page per language built from the registry by path prefix.
  Owner decision D5.
- Articles are normal content pages (registry, prerendered, `adviceNote: false`
  for pure how-to pages). Screenshots come from the demo portfolio, with
  amounts and prices that are synthetic or cropped out (§2).
- First set (Czech), each written from the real cloud flow and checked in the
  running app before publishing:
  1. Connecting Trading 212 through the API key (sync).
  2. Importing a CSV: the duplicate-aware preview and the 24-hour undo.
  3. Why Portfyl's return differs from the broker's figure (TWR/XIRR versus
     broker P/L, FX, fees).
  4. How dividends are counted (net after withholding tax, one row per payout).
  5. How currencies are converted to CZK.
  6. Several portfolios in one workspace.
  7. Unsupported broker: what to do, how to ask for it (the broker request).
  8. Plans and the 10-day Pro trial (only facts that are live; update when
     billing switches on).
  9. Deleting the account: immediate and final (the 10 s warning).
  10. Data and privacy in short, linking the full legal pages.
  The Trading 212 CSV export guide is SEO S8. Article 2 links to it.
- Topic source for later articles: support inbox questions, import preview
  error codes, and onboarding drop-off in PostHog (`onboarding-funnel.md`).
- In-app links: the import preview errors and the Settings help entries link
  to the matching article (absolute `https://portfyl.com/...` link, opens in a
  new tab). This is a separate small task, because it touches app files and
  the i18n hotspot.
- Each article has an "updated" date. When the flow it describes changes, the
  change that alters the flow updates the article in the same pull request.
  Add this rule to the help index body so the next agent sees it.

Done when: articles 1–7 are live in Czech, linked from the landing footer and
from the relevant in-app spots.

### G3. YouTube tutorials (SEO)

Why: almost no Czech videos exist for "how to track a Trading 212 portfolio".
Videos show up in Google results and AI answers, and they can sit on the help
and guide pages.

- A Portfyl channel. First 4 videos in Czech, each 2–4 minutes, screen
  recording with voice:
  1. Trading 212: connect or import, first look at the dashboard.
  2. Dividends overview.
  3. Comparing a portfolio with an index.
  4. Allocation by sector, country and currency.
- **Record only with demo data whose prices and values are synthetic, or blur
  them**, until market-data rights cover public display (§2, owner decision D3).
- Title and description in the language of the search query, a link to the
  matching page with UTM (`utm_source=youtube&utm_medium=video&utm_campaign=<slug>`),
  chapters, and Czech subtitles uploaded as a file (not auto-generated).
- On our pages: a click-to-load facade (thumbnail plus a link to YouTube) in a
  small component `frontend/src/pages/content/VideoLink.jsx`. No iframe, so no
  CSP change and no third-party cookies before consent. Embedding with an
  iframe is a later, separate decision (it needs `frame-src` for
  `www.youtube-nocookie.com` in `backend/security_headers.py` and a consent check).
- Optional: `VideoObject` JSON-LD for pages that carry a video, added to the
  prerender head builder. A separate small task, only if Search Console shows
  video impressions are worth it.

Done when: videos 1–2 are published and linked from S7/S8 and the help
centre, and the channel description links to the landing.

### G4. Shareable outputs (traffic)

Two parts with very different risk. Build part A first.

**A. "My year in Portfyl" card (client-side image).**

- A button in the app (Dashboard or Analytics, owner's choice in D2) makes a
  1080×1350 image for social media: return for the year in %, the number of
  dividend payouts, top allocation weights, and the Portfyl logo with
  `portfyl.com`. Rendered in the browser (SVG to PNG); nothing is uploaded.
  The user downloads it or shares it through the Web Share API where
  available.
- **Default content is percentages and weights only.** Absolute amounts
  (portfolio value, dividends in CZK) are an explicit opt-in toggle, off by
  default, because they are personal data and derive from market prices.
  Owner decision D2 confirms this.
- Holdings appear as tickers and weights, never prices.
- Strings in all app languages (`frontend/src/i18n/messages/*.js`, hotspot).
  Look and colors from DESIGN.md tokens.
- Timing: ship in the first half of December so it is ready for year-end
  reviews.
- Analytics: `share_card_created` with `kind` and `with_amounts` (boolean).
- Check with the market-data vendor terms that a user-generated image of
  their own percentages is allowed. If not, ship with weights and dividend
  count only.

**B. Read-only share links (later, gated).**

This item is listed in the monetization plan (`Read-only share links`, §
roadmap). It gives each shared portfolio a public page with "made with
Portfyl". **It starts only when all three gates pass:** market-data rights
allow public display of derived performance, a security review of the design
is done, and the tenant-isolation matrix (`docs/security/tenant-isolation-matrix.md`)
has the new rows.

Design sketch for that review (not final):

- New tenant table `portfolio_share_links`: workspace, portfolio, token hash
  (store only a hash of the random token), options (show amounts: default
  false), created by, created at, expires at, revoked at. Forced RLS.
- One unauthenticated, read-only endpoint resolves the token and returns a
  fixed, minimal projection (weights, % performance against the chosen
  benchmark, dividend count). It must not reuse the authenticated portfolio
  serializers, so no field leaks by accident. Rate-limited, `X-Robots-Tag:
  noindex`, `Cache-Control: no-store`.
- The public page `/s/<token>` is `noindex` and has a "made with Portfyl"
  call to action. The owner can revoke a link at any time in Settings.
- PostgreSQL tests in `backend/tests/postgres/`: Alice's token never shows
  Bob's data, a revoked or expired token returns 404, and the projection has
  exactly the allowed fields.

### G5. Referral program (traffic)

Starts **after payments are switched on** (`PORTFYL_BILLING_ENABLED=1`),
because the reward is tied to a paying customer. The code can be built
earlier behind a switch `PORTFYL_REFERRALS_ENABLED` (default off).

Rules (owner decision D1 confirms the reward):

- Every user has one personal referral link `https://portfyl.com/?ref=<code>`
  (an opaque random code, not the e-mail or user ID).
- The referred person gets a longer Pro trial (proposal: 30 days instead of
  10). The referrer gets one month of Pro **when the referred workspace pays
  its first invoice**, not at sign-up. Both rewards are Portfyl-owned
  entitlement grants, like the trial, not Stripe coupons.
- **Open question for D1:** a referrer who already pays gains nothing from a
  Portfyl-side Pro grant, because Stripe still charges them. Either the reward
  for paying referrers is a Stripe-side credit (first check in Stripe's docs
  whether Managed Payments supports customer balance credits or coupons on
  subscriptions), or the reward is something else for them. Decide before
  building.
- Abuse guards: reuse the trial guard fingerprints (`backend/trials.py`:
  canonical e-mail, IP window, broker account and history marks). A referral
  whose new user matches the referrer on any of them is rejected silently.
  Limit: at most 12 rewarded referrals per referrer per year.
- Privacy: the referrer sees only counts ("2 friends joined, 1 reward"), never
  who joined.
- Terms: a short article in `docs/legal/podminky-uzivani-cs.md` (and the
  other languages) and a note for the lawyer in
  `docs/legal/poznamky-pro-pravnika.md`. Legal text is a hotspot.

Build sketch:

- Migration (additive): `referral_codes` (user, code hash) and `referrals`
  (referrer user, referred user, status `pending|qualified|rewarded|rejected`,
  reason, timestamps). These cross two workspaces, so, like the trial guard
  tables, they are global tables reached only through backend code, holding
  user IDs and no portfolio data. The security review decides the exact RLS
  treatment and records it in the isolation matrix.
- The `ref` parameter travels with the existing registration `source` handling
  and is stored when `/auth/session` creates the user. Never in a cookie
  that outlives registration.
- `billing_sync.py` marks a referral `qualified` when the referred workspace's
  subscription first becomes active and paid. A job (or the same sync step)
  creates the reward grant and sets `rewarded`.
- `resolve_entitlements` order becomes: live subscription, private test
  selection, active trial, active referral grant, Free. Update `CLAUDE.md`
  and the Free trial / Billing hubs when this lands.
- Settings: a "Recommend Portfyl" card with the link, a copy button and the counts.
- Analytics: `referral_link_copied`, and `source_surface=referral` on the
  existing signup events.

### G6. Communities (traffic)

Non-code. Owner's time, about 1–2 hours a week.

- Places, beyond the Trading 212 forum (already SEO S14):
  - Reddit: r/eupersonalfinance, r/Trading212 (English, the whole EU), and
    Czech or Slovak investing subreddits (check which ones are active first).
  - Czech investing Discord servers (for example the Trading 212 and investing
    servers found on 2026-11-28; check activity first).
  - Czech Facebook groups about investing and Trading 212.
- Rules:
  - Read each community's self-promotion rules first and follow them.
  - Always say you are the founder. One account, the owner's own. No fake
    accounts, no asking friends to upvote, no copy-pasted posts.
  - Answer the question first. Link Portfyl only when it really solves what
    was asked, and prefer a link to a help article or calculator over the
    landing.
  - Use UTM on every link (§5), for example
    `utm_source=reddit&utm_medium=community&utm_campaign=eupersonalfinance`.
- Keep a short log (date, place, link, result) outside the repo, for example
  in a spreadsheet. Review monthly which places bring registrations.
- A good, honest way in: a "which broker do you use?" poll in Czech groups.
  It helps you reach people and tells you which importer to build next.

### G7. Building in public and launch sites (traffic)

Non-code.

- **Building in public:** 1–2 posts a week on LinkedIn and X (owner decision
  D4 on using the owner's own name). Topics: decisions and why (for example,
  why Tax Report is local only), real numbers (users, conversion, costs),
  mistakes and fixes, before/after screenshots (synthetic data, §2). Czech for
  LinkedIn, English for X.
- **Czech startup media:** a short pitch with real numbers to CzechCrunch and
  Lupa.cz at the public launch. This is in addition to the Czech finance media
  in SEO S14.
- **Launch sites, staggered, not all in one week:**
  1. BetaList: now, while sign-up is a closed beta.
  2. Indie Hackers: a product page plus a "how I built it" post.
  3. Show HN (Hacker News): once public sign-up is on and the English landing
     and demo are solid. Post as the maker, technical angle (multi-tenant on
     Cloud Run + Neon, RLS), and be there to answer for the whole day.
  4. Product Hunt: owned by SEO S14. Schedule it at least two weeks apart from
     Show HN.
- Launch checklist (before each of 2–4): public sign-up on, English landing
  checked, demo works without logging in, support inbox watched, error
  monitoring on, the fact sheet from G8 ready.

### G8. Directories and mentions that AI assistants read (SEO)

Non-code, except an optional press page.

- **Fact sheet** (do first, everything below reuses it): name, one-line
  description in cs/en/de, logo files, 4 screenshots (synthetic data),
  pricing as it is live, supported brokers (honest list, §2), founder contact.
  Keep it in `docs/operations/press-fact-sheet.md`. Optionally publish it as a
  content page (`/en/press/`, `/media/`) so journalists and directory editors
  find it.
- **Listings:** AlternativeTo (as an alternative to Sharesight, Snowball
  Analytics, Parqet and getquin), SaaSHub, and Firmy.cz (Seznam's business
  directory, a free Seznam presence). G2 and Capterra later, once a few real
  users can leave reviews.
- **"Best portfolio tracker" lists:** find the articles that rank for "best
  portfolio tracker 2026" (EN) and "nejlepší aplikace na sledování portfolia"
  (CZ), and send their authors a short, factual note with the fact sheet. AI
  assistants often draw on such lists and on Reddit threads. The tracker
  comparison directories already in SEO S14 are not repeated here.
- Every listing uses the same facts as the fact sheet. When pricing or the
  broker list changes, update the fact sheet and the listings together.

## 5. UTM convention

All links we place outside portfyl.com use lowercase UTM values:

| Channel | `utm_source` | `utm_medium` | `utm_campaign` |
|---|---|---|---|
| Reddit, Discord, Facebook | `reddit` / `discord` / `facebook` | `community` | community name |
| YouTube | `youtube` | `video` | video slug |
| LinkedIn, X posts | `linkedin` / `x` | `social` | post topic or date |
| Launch sites | `betalist` / `indiehackers` / `hackernews` | `launch` | `launch-2026` or similar |
| Directories | `alternativeto` / `saashub` / `firmy` | `directory` | `listing` |
| Share card / share link | `share` | `card` / `link` | `year-2026` |
| Referral link | none (`ref` param is enough) | | |

Never put a user ID, e-mail or workspace ID in a UTM value.

## 6. Waves and parallel work

Tasks inside a wave touch disjoint files (`CLAUDE.md` → "Parallel session
safety"). Each task works on its own branch off the integration branch.

**Wave 0, now, no code (the owner):** G6 (start), G7 building in public and
BetaList, G8 fact sheet and listings. Precondition: the §5 convention.

**Wave 1, code, in parallel:**

| Task | Owns | Hotspots it owns in this wave |
|---|---|---|
| W1-a Calculators 1–3 (G1) | `frontend/src/lib/calculators/`, `pages/content/bodies/kalkulacka-*.jsx` and `kalkulacky.jsx`, `seo/pages/kalkulacka-*.js` | `frontend/src/seo/pages/index.js`, `frontend/src/analytics/eventContract.js` |
| W1-b Help articles 1–7, text and metadata (G2) | `pages/content/bodies/napoveda-*.jsx`, `seo/pages/napoveda-*.js` | none: registers its pages in W2-a after W1-a merges |
| W1-c Year card (G4 part A) | `frontend/src/components/share/`, one button in the chosen page | `frontend/src/i18n/messages/*.js` |
| W1-d Video facade (G3) | `frontend/src/pages/content/VideoLink.jsx` and its test | none |

W1-c adds its analytics event in W2 (or W1-a adds it for them, agreed in
advance), because `eventContract.js` is owned by W1-a in this wave.

**Wave 2, code:**

- W2-a: register the help pages in `CONTENT_PAGES`, build the help index
  pages, add `share_card_created` to the event contract, link the help centre
  from the landing footer.
- W2-b: in-app links to help articles (import preview errors, Settings).
  Owns the i18n messages in this wave.
- W2-c: calculators 4–6 and the English versions of the live calculators.

**Wave 3, gated:**

- W3-a: referral program (G5). Gate: billing on and decision D1. Owns
  `backend/alembic/versions/`, `backend/database.py`, `backend/entitlements.py`,
  `backend/billing_sync.py` and the legal docs while it runs.
- W3-b: read-only share links (G4 part B). Gate: market-data rights, security
  review, isolation matrix rows. It also needs a migration, so it runs
  **after** W3-a merges, never at the same time.

Verification for every code task: `npm test`, `npm run test:cloud`,
`npm run build`, `npm run build:cloud` (frontend); fast pytest suite plus
`tests/postgres/` for W3 (backend); `python scripts/build_obsidian_architecture.py --verify`
before committing. For public pages, `curl` the prerendered HTML and check
the content is there with JavaScript off.

## 7. Measurement

- PostHog, consent-gated, as today: `landing_viewed` with `referrer_class` and
  the UTM values, then the signup and activation funnel. Report per
  `utm_source` once a month.
- Search Console (Google, Bing, Seznam): impressions and clicks for the
  calculator and help pages.
- Targets for the first 3 months after each item goes live:
  - Calculators: non-brand impressions within 8 weeks; at least one
    unsolicited external link within 3 months.
  - Help centre: articles 1–7 indexed; support questions on those topics go down.
  - Communities and launches: registrations per channel; drop a place after
    3 months with no registrations.
  - Year card: share rate among active users in December and January.
  - Referral: qualified referrals per month after billing is on.

## 8. Owner decisions

- **D1.** Referral reward: how long the referred person's trial is (30 days
  proposed), the referrer's reward, and what a referrer who already pays gets
  (Stripe credit, if Managed Payments allows it, or something else).
- **D2.** Year card: where the button lives (Dashboard or Analytics), and
  confirm the default is percentages and weights only, amounts opt-in.
- **D3.** Videos and public screenshots use synthetic or blurred prices until
  market-data rights cover public display (recommended).
- **D4.** Building in public under the owner's own name? (Ties into SEO plan O5.)
- **D5.** Help centre paths: `/napoveda/`, `/en/help/`, `/de/hilfe/` (recommended).
- **D6.** Calculators: Czech only first (recommended), English after
  impressions show up.

## Related

- Architecture: [[Portfyl]] · [[Frontend structure]] · [[Free trial]] · [[Billing and Stripe]] · [[Market data]]
- Docs: [[superpowers/plans/2026-11-09-portfyl-seo]] · [[superpowers/plans/2026-09-01-portfyl-saas-monetization]] · [[security/tenant-isolation-matrix]] · [[operations/onboarding-funnel]]
