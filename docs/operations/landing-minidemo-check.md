# Landing mini demos: check page (plan S3)

Plan: `docs/superpowers/plans/2026-11-18-portfyl-landing-mini-dema-5-smazat-demo.md`, section S3.
Branch: `feature/landing-mini-dema-5-smazat-demo-s3` (on top of `main` with S1 and S2 merged).
Checked on 2026-11-19 with `npx vite --mode edition-cloud --port 5183` (dev server) and the
`npm run build:cloud` output. The landing page needs no backend or database.

## What was built

Five live mini demos under the features on `/`, `/en/` and `/de/`. Each one is the shared panel from
`components/showcase/` inside `AppScope` (Clay tokens and the app's dictionary for the page language):

| Demo | Panel | Data | Opens with | Control |
|---|---|---|---|---|
| allocation | `AllocationPanel` | `showcaseData` (3 portfolios, fixed rate) | grouped by position, currency CZK (cs), EUR (de), USD (en) | positions / sectors / currencies |
| stock | `StockValuationPanel` | `demoPortfolio` holding + `SHOWCASE_PE_HISTORY` | MSFT | MSFT / JNJ / PG |
| performance | `PerformancePanel` | `demoPortfolio.performance` + S&P 500 | growth | value / growth |
| dividends | `DividendsPanel` | `demoPortfolio.dividends` | received | received / upcoming |
| portfolios | `PortfoliosPanel` | `showcaseData` | currency by language | CZK / EUR / USD |

All texts come from `minidemo/miniDemoLabels.js` (pure mappers over `COPY[language].miniDemo`). Every change of a
control calls `onUse()`; the hook sends at most one `landing_minidemo_used` per demo and page load, after consent.

Small layout fixes made to the shared panels (props unchanged): card padding `p-4` on phones; the value column of
`AllocationBreakdownList` is as wide as its text (it clipped `1 117 391,75 Kc`); on phones the name column of the list is
narrower and the Recharts legend is hidden when the donut has more than 8 slices (17 legend entries pushed the donut out of
its box). `Welcome.css`: `min-height` of the demo bodies set to the measured live heights (allocation 34rem, stock 59rem,
performance 30rem, dividends 24rem, portfolios 26rem) so the page does not jump when a demo loads.

## Size (`npm run build:cloud`, then the guard)

| | Baseline (`landing-bundle-baseline.json`, measured on 942374d) | Now | Limit (+5120) |
|---|---|---|---|
| entry (initial JS + CSS, gzip) | 83 944 B | 85 516 B (+1 572) | 89 064 B |
| `Welcome` static closure (gzip) | 99 651 B | 103 333 B (+3 682) | 104 771 B |

`node scripts/landing-bundle-guard.mjs dist --baseline scripts/landing-bundle-baseline.json`: `ok: true`, no violations,
5 frames in each of `index.html`, `en/index.html`, `de/index.html`, no digit in their text, no Recharts, no
`portfyl-showcase-v1` and no sample-portfolio name in the static graph. The increase over the baseline comes from S2 (frame,
copy for three languages, analytics event); S3 only touches lazy chunks, so the static numbers did not move because of it.
`npm run measure:bundle`: initial JS 71 825 B, initial CSS 13 691 B, combined 85 516 B (83.5 KiB), gzip level 9.

Cost of the live demos (loaded only when a frame comes within 200 px of the screen): the five `Mini*.jsx` chunks are
0.5 to 1.2 KB gzip each, plus the shared `miniDemoLabels` chunk (1.1 KB). The first demo that draws a chart pulls the app's
chart chunks: about 120 to 140 KB gzip of JavaScript, of which Recharts (`chartTheme`) is 101 KB and is shared by all
demos; the dividends demo needs about 15 KB on top of that shared part. The Czech or German dictionary adds one chunk of
about 40 KB gzip. Nothing of this is on the initial path.

## Visual and accessibility check

Method: headless Chrome 157 over the DevTools protocol (one screenshot of each frame, fixed header and cookie banner hidden
for the shot) plus the built-in browser for keyboard checks. 45 frame screenshots (5 demos x 3 languages x 3 widths).

- All 15 frames became live on `/`, `/en/`, `/de/` at 1280, 768 and 360 px.
- Horizontal scroll: `document.documentElement.scrollWidth` equals the viewport width (1280, 768, 360) on all three pages.
- Look: the frames show the app's Clay look (warm cards, 24 px radius, Clay shadow, sliding `SegmentedControl`, chart colors in
  the `--chart-N` order). Headings, paragraphs and links outside the frames keep the flat landing look (full-page screenshot
  of `/en/` reviewed; `Welcome.css` rules for them are untouched and guarded by `:where(:not(.welcome-minidemo-app *))`).
- Keyboard (built-in browser, `/en/`): Tab moves between the buttons of a demo, Enter and Space both change the selection
  (`aria-pressed` follows), `:focus-visible` is true and draws a 2.7 px brand outline.
- `prefers-reduced-motion: reduce` (emulated): all five demos work, the `SegmentedControl` thumb transition is 0 s.
- Text tables: every frame has one `sr-only` table with a `caption` (rows: 17 / 20 / 25 / 9 / 3). Controls are
  `role="group"` with `aria-label`, buttons are `type="button"`.
- No text below 12 px inside any frame (computed font sizes checked in all five).
- Long German labels ("Fuenfjahresdurchschnitt des KGV", "Waehrungen") do not break the layout at 360 px; the button
  row scrolls sideways inside the control.
- Dev console: the only warning is React's `fetchPriority` prop on the hero `Shot` image (existing, not from the demos).

Screenshots (not tracked in git): `C:\Users\tomzo\AppData\Local\Temp\claude\4f7287ebdcc80c59\b35026bf-c68f-43c7-b3a3-878ff9e5db1e\scratchpad\shots\<lang>-<width>-<kind>.png`
(`lang` cs|en|de, `width` 1280|768|360, `kind` allocation|stock|performance|dividends|portfolios), and the full-page view
`...\scratchpad\pg\page-en-top.jpg`.

## Found, not fixed (outside the S3 file list)

1. **Stock demo shows four "No data" tiles** (EV/EBITDA, P/S, P/FCF, P/B): the app's `ValuationHistoryCharts` always draws
   all five multiples and the sample data only has P/E. It is the real component, but on a landing page the empty tiles are
   noise. Fix would be either sample history for the other multiples in `showcaseData.js` or a prop on
   `ValuationHistoryCharts` to show P/E only.
2. **Second `h1` in the live stock demo**: `StockHeader` renders the ticker as `h1` (only after the lazy demo loads, so not in
   the prerendered HTML). A `headingLevel` prop on `StockHeader` would fix it.
3. **Dividends demo shows USD** (`demoPortfolio` is in USD), also on the Czech and German pages; the other demos follow the
   page language's currency. The sample data has no per-currency dividends.
4. The portfolios hero chip "Dividends" shows a dash (no dividend total in `showcaseData`).
5. `npm run audit:readability` reports `components/dashboard/DividendBarsCard.jsx:143 text-[10px]`; it does so on clean `main`
   as well (not caused by S3).
6. `Root.test.jsx` (edition-cloud), the `/terms` (once `/privacy/`) case, timed out in `findByRole` (default 1 s, cold Legal
   chunk) in 4 of 5 full `test:cloud` runs on this branch, also with the two new test files excluded; it passed in the 5th
   full run, in every isolated run after a warm-up, and in 3 of 3 full runs on a clean `main` checkout. Not understood
   beyond "timing under load"; the test file is not part of S3, so it was left alone.

## Open questions for the owner (O1 to O3 from the plan)

- **O1 look**: demos draw Clay (recommended). Premium (mesh gradient, translucent cards) would need separate work inside the frame.
- **O2 main button while sign-ups are closed**: recommended "Try the examples" scrolling to `#funkce`; alternative a text only
  "Closed beta". Plan wave 3 assumes the recommended one.
- **O3 after launch**: watch `landing_minidemo_used` and `signup_cta_clicked` / `signup_started` in PostHog against the period
  before `/demo` is removed.

Not verified: the real hosted app side by side (needs `DATABASE_URL` and a login); the comparison was against `DESIGN.md`
sections 3 to 6 and the `/demo/*` pages' look. The screenshots have not been sent to the owner (`SendUserFile` is not available
to this session); the paths above are the hand-off.
