# Portfyl public landing (portfyl.com) → Clay style

**Goal:** Restyle the public landing at `portfyl.com/` so it looks like the
live app's **Clay** appearance (warm organic palette, soft raised/inset depth,
pill controls, 24px cards). Copy, analytics, routing, and Access coverage stay
exactly as they are.

**Source of truth for the look:** `DESIGN.md` (sections 3–8). Read it first.

## What is "portfyl.com" in code

| Piece | File |
|---|---|
| Landing page (cloud edition `/`, `HAS_PUBLIC_HOME`) | `frontend/src/pages/Welcome.jsx` |
| Its styles (self-contained, ~155 lines) | `frontend/src/pages/Welcome.css` |
| CZ/EN/DE copy | `frontend/src/pages/welcomeCopy.js` (no changes planned) |
| Tests | `frontend/src/pages/Welcome.test.jsx` |
| Screenshots shown on the page | `frontend/public/landing/*-live-20260911.png` |
| Route selection (landing vs demo vs tracker) | `frontend/src/Root.jsx` (no changes) |
| Public demo `portfyl.com/demo` | `frontend/src/demo/*` (optional phase 2) |

### Why it does not look like the app today

- `Welcome.css` has its own **sage-green palette** (`#243c32`, `#f8f9f5`,
  `#859371`…), ~60 hard-coded hex values, none of them app tokens.
- `Welcome` renders outside `App.jsx`, so `applyAppearance()` never runs:
  no `--bg`/`--brand`/`--clay-*` variables exist on the page.
- Shapes are sharp (6–14px radii, 1px borders), flat shadows, a glass-blur
  header — DESIGN.md says *never glass-blur on Clay*.
- Screenshots are from 2026-09-11, the old look (dark `#0b1224` window).

## Non-goals

- No copy/text changes, no new links (the landing deliberately has no
  login/registration/pricing links — `docs/operations/2026-09-10-public-landing.md`).
- No analytics/event-contract changes (`landing_viewed`, `demo_started` stay).
- No backend, migration, or Cloudflare Access changes.
- Do not edit `index.css`, `themeTokens.js`, or `App.jsx` in this work (see
  "Parallel safety").

## Parallel safety (read before starting)

- The main checkout currently has **uncommitted design work** (`DESIGN.md` is
  untracked; `index.css`, `themeTokens.js`, `SegmentedControl.jsx`, many
  dashboard components are modified). A worktree cut from `main` would not see
  it. **Step 0 must land that work first** (commit/merge on main, or wait for
  the session that owns it).
- This work then runs on its own branch/worktree `feat/landing-clay` and owns
  only: `Welcome.jsx`, `Welcome.css`, `Welcome.test.jsx`, new files in
  `frontend/public/landing/`, and one new section in `DESIGN.md`.
- Dev servers on non-default ports (e.g. backend :8010, Vite :5180) if another
  session is running :8000/:5173.

## Tasks

### 0. Prerequisite — land the current Clay work on `main`
Commit/merge the in-progress design changes so `DESIGN.md`, the Clay tokens
and `SegmentedControl` are in Git. Then `git worktree add` → `feat/landing-clay`.

### 1. Token bridge (Welcome.jsx)
- Import `CLAY_TOKENS` from `lib/themeTokens.js` and set the same CSS variables
  `applyAppearance()` sets (`--bg`, `--bg-subtle`, `--surface-card`,
  `--surface-card-elevated`, `--ink`, `--muted`, `--brand`, `--brand-hover`,
  `--brand-light`, `--shadow-ambient`, `--shadow-inset`, `--radius-card`…) as an
  inline `style` on the `.welcome` root — read `applyAppearance()` to copy the
  exact variable names. Values come from `themeTokens.js`, never retyped.
- Add class `theme-clay` to the root (both the language screen and the main
  page) so `index.css`'s `--clay-raise`, `--clay-raise-sm`, `--clay-inset-sm`,
  `--clay-raise-brand`, `--clay-raise-hover` resolve. Check no `.theme-clay X`
  descendant rule restyles landing elements unexpectedly (Welcome uses no
  Tailwind utility classes, so leakage should be nil — verify in the browser).
- Fonts: `font-display` (Plus Jakarta Sans) for h1–h3, Inter for body
  (already imported via `fonts.css`).

### 2. Rewrite Welcome.css section by section (no hex values left)

| Section | Clay treatment |
|---|---|
| Page | `--bg` + the same warm mesh gradient as `.theme-clay body` |
| Header | floating **pill top bar** like `.app-topbar`: `--surface-card-elevated`, `--clay-raise`, radius 999, 12–16px from the top; remove `backdrop-filter` |
| Beta badge | small inset pill (`--clay-inset-sm`) |
| Language switch + preview switch | inset trough + raised active pill with bold brand text. Prefer reusing `components/ui/SegmentedControl.jsx` (sliding liquid pill) if its API fits the `aria-pressed` buttons the tests use; otherwise mimic `.segmented` styling |
| Headings | Plus Jakarta Sans, tracking ~-0.03em (not -4px); accent line in `--brand` (check AA for large text) |
| Primary CTA | brand pill, `--clay-raise-brand`; hover lift 1px + scale 1.06, press 0.97 + `--clay-inset-sm` |
| Secondary link | ghost pill, `--clay-raise-sm` |
| Hero orbits | soft raised clay blobs in `--brand-light` / Sand tones instead of flat discs |
| Hero window | raised clay frame, radius 28px, light window bar with inset dots; drop the dark background |
| Float chip | raised clay pill tile (`.pop-tile`-like), lift 3px/scale 1.04 on hover |
| Broker ribbon | inset trough band, brokers as small raised chips |
| Feature cards | raised clay cards, 24px radius, **no border**, icon in round `--brand-light` badge; hover lift 4px / scale 1.01 |
| Showcase | `--bg-subtle` band; screenshot in raised clay frame |
| FAQ | each `<details>` a raised 20px card (16px gap); `+` in a small round raised button that rotates |
| Closing panel | large raised clay panel, 28px radius, faint `--brand-light` radial |
| Language screen | three raised clay cards, code chip inset, hover lift |
| Footer | muted text, no border |

Rules from DESIGN.md: spring easing `cubic-bezier(0.34, 1.56, 0.64, 1)` 0.2–0.32s
using the standalone `translate`/`scale` properties; light from top-left;
≥24px between raised cards; text ≥12px; focus = 3px brand outline, 2px offset;
touch targets ≥44px on mobile; `prefers-reduced-motion` turns motion off.

### 3. New screenshots in Clay
- Capture four new screenshots (allocation, stock, dashboard, performance) from
  a local dev instance in the **Clay** appearance, using **synthetic demo data
  only** (onboarding "demo" data or `sample_portfolio.csv`) — never a real
  portfolio. Keep the existing "interface concept / illustrative data" labels.
- Save as `frontend/public/landing/<name>-clay-20261016.png` (new name = cache
  bust), compress (target < 150 KB each, 2x crop), update `screenshotPath`,
  `imageSizes`, and the `src` expectations in `Welcome.test.jsx`.
- Leave the old `-live-20260911` files in place until the deploy is verified;
  delete them in a follow-up.

### 4. Tests and builds (edition-sensitive: landing is cloud-only)
From `frontend/`: `npm test`, `npm run test:cloud`, `npm run build`,
`npm run build:cloud` — all green.

### 5. Visual verification
Run the cloud edition locally, open `/` (language screen and main page) at
1440px, 768px and 375px. Check: no horizontal scroll, header pill wraps
cleanly, shadows do not collide, focus ring visible, contrast AA, reduced
motion respected, `/demo` CTA still works. Run a Lighthouse pass and compare
performance/accessibility against the current production page.

### 6. DESIGN.md
Add a short section "Public landing (portfyl.com)": it always renders Clay,
gets tokens from `CLAY_TOKENS` via the `.welcome` root, and lists the landing
specific pieces (pill header, clay blobs, raised FAQ cards).

### 7. Deploy (needs the owner's go-ahead)
Frontend-only change → frontend overlay build
(`deploy/cloudbuild-frontend-overlay.yaml`) per `deploy/cloudrun.md`. After
deploy: anonymous `https://portfyl.com/` and its images/JS/CSS return 200;
`/dashboard`, `/login`, `/api/auth/me` still behind Access.

## Phase 2 (optional, separate session, can run in parallel)
`/demo` currently renders with default `:root` (Classic) tokens because
`DemoShell` never applies an appearance. Apply `CLAY_TOKENS` + `theme-clay`
there too so the landing → demo jump feels like one product. Owns only
`frontend/src/demo/*`.

## Done when
- No hex colors remain in `Welcome.css`; every color/shadow is a token.
- Landing and language screen visually match the app's Clay look on desktop
  and mobile; screenshots show the Clay app.
- All four frontend test/build commands pass; DESIGN.md updated.
- Deployed and the Access checks in step 7 pass.
