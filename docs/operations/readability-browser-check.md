# Readability browser check

Manual verification companion to `npm run audit:readability` (see
`frontend/scripts/audit-readability.mjs`). The automated scan only catches
sub-floor source patterns (`text-[8-11px]` utilities, CSS `font-size` below
12px) — it cannot see computed browser contrast, real layout overflow, or
keyboard focus. Run this checklist before any release that touches
typography, theme tokens, or chart styling, and re-run it after
`docs/superpowers/plans/2026-09-19-portfyl-public-demo.md` and
`docs/superpowers/plans/2026-09-19-portfyl-activation-analytics.md` add new
public/demo surfaces.

## Viewports

Test each page at all four:

| Label | Size | Represents |
|---|---|---|
| Mobile | 390×844 | iPhone 12/13/14-class phone |
| Tablet portrait | 768×1024 | iPad-class tablet, portrait |
| Tablet landscape | 1024×768 | iPad-class tablet, landscape |
| Desktop | 1440×900 | Common laptop viewport |

## Appearances

Test each page in all three (Settings → Appearance): **Premium**, **Classic
light**, **Classic dark**.

## Representative pages

- Public landing (`/`)
- Login, Register, Forgot password, Verify email
- Onboarding, Import (CSV preview step)
- Dashboard, Allocation, Analytics
- Dividends, Transactions, Cash, Watchlists, Options
- A stock detail page (`/stock/:ticker`) with financials, valuation, and
  ownership tabs open
- Tax Report, Screener (local edition only)
- Settings, cloud Pricing, Assistant

## Per-page checks

For every page × viewport × appearance combination:

- [ ] **Critical numeric values** (headline balances, table cells, chart
      axis/legend text) are visually ≥ their documented floor: 16px
      headline, 14px ordinary value, 12px metadata/label/axis/legend. Use
      the browser inspector's computed `font-size`, not a visual guess.
- [ ] **Contrast** meets target: use a contrast-checking devtool or
      extension on primary text (≥ 4.5:1), and on gain/loss pills, chart
      grid lines, and focus rings (≥ 3:1). Spot-check against
      `frontend/src/lib/themeTokens.js`'s `THEME_CONTRAST_PAIRS` if a value
      looks borderline.
- [ ] **Gain/loss meaning** is never color-only: an explicit `+`/`−` sign or
      word is present alongside the color.
- [ ] **No page-level horizontal scrolling.** Dense tables/calendars may
      scroll horizontally *within their own container*
      (`overflow-x-auto`), but the page itself must not.
- [ ] **Charts retain their accessible summary or table equivalent**
      (`ChartSummary` disclosure, or an inline table) with the same
      formatted values as the chart.
- [ ] **Keyboard focus is visible** when tabbing through nav, controls,
      table sort headers, and chart summary toggles.

## Recording results

Note the commit/build hash, date, and any deviations (with a linked
follow-up) at the bottom of this section for the release under review.
Automated source scanning (`npm run audit:readability`, the Vitest and
pytest suites, both production builds) must also be green before sign-off —
this checklist is a supplement, not a replacement.
