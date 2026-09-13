# UX Plan 2: Platform Removal and Async-State Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every authenticated portfolio user directly into Portfyl, remove the fictitious platform gate, and make request failures visibly different from legitimate empty data.

**Architecture:** Delete `PlatformContext` from routing and treat broker connection as Settings data. Introduce one API-error normalizer and one compositional async boundary, then apply that boundary to primary pages and independent dashboard/analytics widgets while preserving existing query/mutation contracts.

**Tech Stack:** React 18, React Router 7, TanStack Query, Axios, Vite 6, Vitest/Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design.md` (§4.2, §4.4, §6, §7.2, §12.3)

## Global Constraints

- An authenticated user with at least one portfolio reaches Dashboard regardless of Trading 212 connection status; an authenticated user with no portfolio still reaches Onboarding.
- `sb_platform` is ignored and removed once during authenticated startup. Other `sb_*` preferences remain untouched.
- Trading 212 stays under Settings → Connections. Removing the platform gate does not imply a connection is active.
- Async-state precedence is loading → error → empty → content. Errors include retry unless retry is unsafe.
- Independent Dashboard/Analytics queries receive independent boundaries; one provider failure must not erase healthy widgets.
- Mutations keep toast/inline errors and are not hidden inside query boundaries.
- Skeletons reserve approximate final height; do not replace a chart/table with a one-line loading label.
- Use existing tokens/primitives; no new state manager or component library.
- Preserve local/cloud capability filtering and every Plan 1 data-trust contract.
- Work on `codex/ux-02-platform-state`, based on integration HEAD after Plan 1; merge into `codex/portfyl-ux-overhaul`, never `main`.

Run before editing:

```powershell
$branch = (git branch --show-current).Trim()
if ($branch -eq 'main') { throw 'Refusing to work on main' }
git status --short
```

## File Structure

- Create `frontend/src/lib/apiError.js` + tests: safe human-readable extraction.
- Create `frontend/src/components/ui/AsyncSection.jsx` + tests; export it and `ErrorState` from the UI barrel.
- Modify `frontend/vite.config.js`: worktree API proxy override.
- Modify `frontend/src/App.jsx`, `PortfolioSwitcher.jsx`, `Onboarding.jsx`, routing tests; delete authenticated use of `PlatformLanding`.
- Modify primary pages and add one contract-style async-state test file per page group.

---

## Task 1: Normalize API errors safely

**Files:**
- Create: `frontend/src/lib/apiError.js`
- Create: `frontend/src/lib/apiError.test.js`

**Interfaces:**
- Produces: `getApiErrorMessage(error, fallback = "We couldn't load this data.") -> string`.

- [ ] **Step 1: Write failing tests**

```js
import { getApiErrorMessage } from "./apiError";

it.each([
  [{ response: { data: { detail: "Portfolio unavailable" } } }, "Portfolio unavailable"],
  [{ response: { data: { detail: [{ loc: ["query", "limit"], msg: "Invalid value" }] } } }, "Invalid value"],
  [{ code: "ECONNABORTED" }, "The request timed out. Please try again."],
  [{ request: {} }, "We couldn't reach Portfyl. Check your connection and try again."],
  [new Error("Readable failure"), "Readable failure"],
])("normalizes %o", (error, expected) => {
  expect(getApiErrorMessage(error)).toBe(expected);
});

it("never exposes stack text or object coercion", () => {
  expect(getApiErrorMessage({ response: { data: { detail: { secret: "x" } } } }, "Safe fallback"))
    .toBe("Safe fallback");
});
```

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- apiError.test.js`

- [ ] **Step 3: Implement the normalizer**

```js
export function getApiErrorMessage(error, fallback = "We couldn't load this data.") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter((msg) => typeof msg === "string" && msg.trim());
    if (messages.length) return messages.join("; ");
  }
  if (error?.code === "ECONNABORTED" || /timeout/i.test(error?.message || "")) {
    return "The request timed out. Please try again.";
  }
  if (error?.request && !error?.response) {
    return "We couldn't reach Portfyl. Check your connection and try again.";
  }
  if (typeof error?.message === "string" && error.message.trim() && !error.stack?.includes(error.message + "\n")) {
    return error.message.trim();
  }
  return fallback;
}
```

Do not stringify response objects or stacks.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- apiError.test.js`

```powershell
git add frontend/src/lib/apiError.js frontend/src/lib/apiError.test.js
git commit -m "feat(ui): normalize API errors into safe user messages"
```

## Task 2: Shared `AsyncSection` state boundary

**Files:**
- Create: `frontend/src/components/ui/AsyncSection.jsx`
- Create: `frontend/src/components/ui/AsyncSection.test.jsx`
- Modify: `frontend/src/components/ui/index.js`

**Interfaces:**
- Produces: `AsyncSection({ isLoading, error, onRetry, loading, isEmpty, empty, children })`.

- [ ] **Step 1: Write precedence/accessibility tests**

```jsx
import { render, screen, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
import AsyncSection from "./AsyncSection";

it("uses loading, error, empty, content precedence", () => {
  const { rerender } = render(<AsyncSection isLoading loading={<p>Skeleton</p>} error={new Error("Boom")} isEmpty empty={<p>Empty</p>}><p>Data</p></AsyncSection>);
  expect(screen.getByRole("status")).toHaveTextContent("Skeleton");
  rerender(<AsyncSection error={new Error("Boom")} isEmpty empty={<p>Empty</p>}><p>Data</p></AsyncSection>);
  expect(screen.getByRole("alert")).toHaveTextContent("Boom");
  rerender(<AsyncSection isEmpty empty={<p>Empty</p>}><p>Data</p></AsyncSection>);
  expect(screen.getByText("Empty")).toBeInTheDocument();
  rerender(<AsyncSection><p>Data</p></AsyncSection>);
  expect(screen.getByText("Data")).toBeInTheDocument();
});

it("offers retry only when provided", () => {
  const retry = vi.fn();
  render(<AsyncSection error={new Error("Nope")} onRetry={retry}><span /></AsyncSection>);
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(retry).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- AsyncSection.test.jsx`

- [ ] **Step 3: Implement by composing existing primitives**

```jsx
import ErrorState from "./ErrorState";
import { getApiErrorMessage } from "../../lib/apiError";

export default function AsyncSection({ isLoading, error, onRetry, loading, isEmpty, empty, children }) {
  if (isLoading) return <div role="status" aria-label="Loading">{loading}</div>;
  if (error) return <div role="alert"><ErrorState message={getApiErrorMessage(error)} onRetry={onRetry} /></div>;
  if (isEmpty) return empty;
  return children;
}
```

Add named barrel exports for `AsyncSection` and `ErrorState`.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- AsyncSection.test.jsx primitives.test.jsx`

```powershell
git add frontend/src/components/ui/AsyncSection.jsx frontend/src/components/ui/AsyncSection.test.jsx frontend/src/components/ui/index.js
git commit -m "feat(ui): add shared loading error empty content boundary"
```

## Task 3: Worktree-safe Vite API proxy

**Files:**
- Modify: `frontend/vite.config.js`
- Create: `frontend/vite.config.test.js`

**Interfaces:**
- Produces: `server.proxy["/api"].target = process.env.VITE_API_PROXY_TARGET || "http://localhost:8000"`.

- [ ] **Step 1: Add a failing config test**

Export `createConfig({ mode, env })` from `vite.config.js` and assert:

```js
import { createConfig } from "./vite.config.js";

it("defaults API proxy to port 8000", () => {
  expect(createConfig({ mode: "development", env: {} }).server.proxy["/api"].target)
    .toBe("http://localhost:8000");
});

it("uses VITE_API_PROXY_TARGET for a worktree server", () => {
  expect(createConfig({ mode: "development", env: { VITE_API_PROXY_TARGET: "http://localhost:8001" } }).server.proxy["/api"].target)
    .toBe("http://localhost:8001");
});
```

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- vite.config.test.js`

- [ ] **Step 3: Refactor without changing edition resolution**

```js
export function createConfig({ mode, env = process.env }) {
  const edition = resolveFrontendEdition(env, mode);
  return {
    // keep existing define/plugins/resolve/test blocks verbatim
    server: {
      port: 5173,
      allowedHosts: [".serveousercontent.com", ".trycloudflare.com"],
      proxy: { "/api": { target: env.VITE_API_PROXY_TARGET || "http://localhost:8000", changeOrigin: true } },
    },
  };
}

export default defineConfig(({ mode }) => createConfig({ mode, env: process.env }));
```

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- vite.config.test.js && npm run build && npm run build:cloud`

```powershell
git add frontend/vite.config.js frontend/vite.config.test.js
git commit -m "chore(dev): allow worktree API proxy target override"
```

## Task 4: Remove platform state and route gating

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/App.routing.test.jsx`
- Delete: `frontend/src/pages/PlatformLanding.jsx`

**Interfaces:**
- Produces: `AppLayout` with one authenticated route tree; Plan 3 wraps it in `AppShell`.

- [ ] **Step 1: Replace routing tests with failing product behavior**

Add assertions that a portfolio user with no `sb_platform` renders Dashboard, a stale `sb_platform` is removed, no portfolio renders Onboarding, and local/cloud edition routes remain capability-filtered. Remove mocks/assertions for `PlatformProvider`/`PlatformLanding`.

```jsx
it("routes a portfolio user directly to Dashboard without broker state", async () => {
  localStorage.removeItem("sb_platform");
  mocks.fetchPortfolios.mockResolvedValue([{ id: "p1", name: "CSV portfolio" }]);
  renderApp("/");
  expect(await screen.findByRole("heading", { name: /portfolio overview/i })).toBeInTheDocument();
});

it("removes the obsolete platform key", async () => {
  localStorage.setItem("sb_platform", "t212");
  renderApp("/");
  await screen.findByRole("heading", { name: /portfolio overview/i });
  expect(localStorage.getItem("sb_platform")).toBeNull();
});
```

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- App.routing.test.jsx`

- [ ] **Step 3: Collapse `App.jsx`**

Delete `PlatformContext`, `usePlatform`, `PlatformProvider`, the `PlatformLanding` import, and both `if (!platform)` / `platform === "t212"` branches. In `AuthGate`, mount `AppLayout` directly under `ConfirmProvider`. In `AppLayout`, call `localStorage.removeItem("sb_platform")` in a mount-only effect and render the full shared route set whenever portfolios exist. Render `<AutoLoad />` unconditionally for portfolio users; Plan 8 will reduce what it prefetches.

Delete `PlatformLanding.jsx` only after:

```powershell
rg -n "PlatformLanding|usePlatform|PlatformProvider|sb_platform" frontend/src
```

shows only the locations intentionally being edited and tests that assert cleanup.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- App.routing.test.jsx Root.test.jsx edition.test.jsx`

```powershell
git add frontend/src/App.jsx frontend/src/App.routing.test.jsx
git rm frontend/src/pages/PlatformLanding.jsx
git commit -m "feat(routing): remove platform gate and enter Dashboard directly"
```

## Task 5: Remove platform coupling from onboarding, switcher, and sidebar

**Files:**
- Modify: `frontend/src/pages/Onboarding.jsx`
- Modify: `frontend/src/pages/Onboarding.test.jsx`
- Modify: `frontend/src/components/PortfolioSwitcher.jsx`
- Modify: `frontend/src/components/Sidebar.jsx`
- Modify: `frontend/src/App.routing.test.jsx`

**Interfaces:**
- Consumes: single route model from Task 4.

- [ ] **Step 1: Add failing tests**

Remove `usePlatform` mocks. Assert demo activation goes to `TRACKER_HOME`, import activation goes to `/import`, broker activation goes to `/settings`, and selecting a portfolio never writes `sb_platform`. Add a sidebar assertion that navigation is visible without platform state and has no “Change platform” action.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- Onboarding.test.jsx App.routing.test.jsx`

- [ ] **Step 3: Remove coupling**

In `Onboarding`, delete `usePlatform` and `setPlatform("t212")`. In `PortfolioSwitcher`, delete `usePlatform` and any `setPlatform(null)` behavior. In `Sidebar`, remove `usePlatform`, `platform` checks, and the platform-reset control; keep portfolio switcher, appearance controls, account menu, and current navigation until Plan 3/7 move them.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- Onboarding.test.jsx App.routing.test.jsx`

```powershell
git add frontend/src/pages/Onboarding.jsx frontend/src/pages/Onboarding.test.jsx frontend/src/components/PortfolioSwitcher.jsx frontend/src/components/Sidebar.jsx frontend/src/App.routing.test.jsx
git commit -m "refactor(ui): decouple onboarding and navigation from broker state"
```

## Task 6: Dashboard and Analytics widget-level async states

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/pages/Analytics.jsx`
- Create: `frontend/src/pages/Dashboard.async.test.jsx`
- Create: `frontend/src/pages/Analytics.async.test.jsx`

**Interfaces:**
- Consumes: `AsyncSection` and `getApiErrorMessage`.

- [ ] **Step 1: Write failing isolation tests**

For Dashboard, reject `fetchMovers` while resolving summary/holdings/performance and assert the hero/performance remain plus a Movers error and retry button. For Analytics, reject correlation while resolving metrics/comparison and assert metric headings remain plus a correlation error. Then click each retry and assert only its query function is called again.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- Dashboard.async.test.jsx Analytics.async.test.jsx`

- [ ] **Step 3: Wrap independent queries**

Destructure `error` and `refetch` for every query. Wrap each Dashboard widget (`performance`, `heatmap`, `earnings`, `holdings`, `insiderBuys`, `movers`) and each Analytics block (`metrics`, `comparison`, `sectors`, `correlation`) in its own `AsyncSection`. Supply existing `SkeletonChart`/`SkeletonRows` at final dimensions and existing empty states. Do not put one page-wide boundary around independent providers.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- Dashboard.async.test.jsx Analytics.async.test.jsx`

```powershell
git add frontend/src/pages/Dashboard.jsx frontend/src/pages/Analytics.jsx frontend/src/pages/Dashboard.async.test.jsx frontend/src/pages/Analytics.async.test.jsx
git commit -m "feat(states): isolate Dashboard and Analytics query failures"
```

## Task 7: Page-level async states for portfolio workflows

**Files:**
- Modify: `frontend/src/pages/Allocation.jsx`
- Modify: `frontend/src/pages/Transactions.jsx`
- Modify: `frontend/src/pages/Dividends.jsx`
- Modify: `frontend/src/pages/TaxReport.jsx`
- Create: `frontend/src/pages/PortfolioPages.async.test.jsx`

**Interfaces:**
- Consumes: `AsyncSection`; preserves Plan 1 Dividends/Tax behavior.

- [ ] **Step 1: Add one failing error/empty/retry case per page**

Use API mocks and MemoryRouter. Reject each primary query and assert a `role="alert"` and named Retry; resolve `[]`/empty payload and assert the page's existing empty copy instead. Ensure Tax Report's local-only test runs under the local Vitest mode.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- PortfolioPages.async.test.jsx`

- [ ] **Step 3: Apply page boundaries**

For each query destructure `error`/`refetch`, render a size-matched Skeleton, pass a domain-specific `EmptyState`, and keep mutations outside the boundary. Preserve Transactions' current unpaged query for now; Plan 4 changes only the collection transport. Preserve Dividends trust groupings and Tax Report precision from Plan 1.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- PortfolioPages.async.test.jsx Dividends.trust.test.jsx TaxReport.precision.test.jsx`

```powershell
git add frontend/src/pages/Allocation.jsx frontend/src/pages/Transactions.jsx frontend/src/pages/Dividends.jsx frontend/src/pages/TaxReport.jsx frontend/src/pages/PortfolioPages.async.test.jsx
git commit -m "feat(states): distinguish portfolio page failures from empty data"
```

## Task 8: Page-level async states for research and settings

**Files:**
- Modify: `frontend/src/pages/Search.jsx`
- Modify: `frontend/src/pages/Watchlists.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/pages/Assistant.jsx`
- Modify: `frontend/src/pages/Stock.jsx`
- Create: `frontend/src/pages/ResearchPages.async.test.jsx`

**Interfaces:**
- Consumes: shared async/error contracts; mutation errors remain inline/toasted.

- [ ] **Step 1: Add failing tests**

Assert Search distinguishes “enter a symbol” from request failure; Watchlists distinguishes no lists from load failure; Settings distinguishes disconnected from status failure; Assistant distinguishes unconfigured from config failure; Stock shows provider error plus Retry without raw response objects.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- ResearchPages.async.test.jsx`

- [ ] **Step 3: Apply boundaries and safe copy**

Use `AsyncSection` around each page's primary query result, preserve legitimate empty actions, and use `getApiErrorMessage` for form/mutation fallbacks where those files currently read `response.data.detail` directly. Do not wrap destructive mutations in `AsyncSection`.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- ResearchPages.async.test.jsx`

```powershell
git add frontend/src/pages/Search.jsx frontend/src/pages/Watchlists.jsx frontend/src/pages/Settings.jsx frontend/src/pages/Assistant.jsx frontend/src/pages/Stock.jsx frontend/src/pages/ResearchPages.async.test.jsx
git commit -m "feat(states): add explicit research and settings request states"
```

## Task 9: Phase verification and browser matrix

**Files:**
- Create: `docs/superpowers/plans/ux-02-platform-state-verification.md`

- [ ] **Step 1: Run frontend gates**

```powershell
cd frontend
npm test
npm run test:cloud
npm run build
npm run build:cloud
```

- [ ] **Step 2: Run worktree servers**

Backend on 8001 and frontend on 5174 with `$env:VITE_API_PROXY_TARGET='http://localhost:8001'`. Confirm the open `:5173` tab remains a different checkout if applicable.

- [ ] **Step 3: Browser matrix**

At all four required viewports verify: CSV portfolio reaches Dashboard without broker connection; no-portfolio reaches Onboarding; broker choice leads to Settings; forced failures on Dashboard, Allocation, Transactions, Dividends, Analytics, Search, Stock, Watchlists, Settings, Assistant, and Tax Report show error/retry rather than empty data; retry recovers; local/cloud routes stay gated; no new console errors or overflow.

- [ ] **Step 4: Record and commit evidence**

```powershell
git add docs/superpowers/plans/ux-02-platform-state-verification.md
git commit -m "docs(ux): record platform-state phase verification"
```

## Self-review notes

- Spec §6 platform removal maps to Tasks 4–5; §7.2 maps to Tasks 1–2 and 6–8; §12.3 maps to Task 3.
- Plan 3 receives the exact interfaces it names: no platform provider/gate, `getApiErrorMessage`, and `AsyncSection`.
- Plan 4 may replace collection query mechanics but must retain these error/empty boundaries.
