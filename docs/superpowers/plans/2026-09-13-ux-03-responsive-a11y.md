# Responsive Shell, Navigation, and Accessibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed desktop-only sidebar/`h-screen` shell with one navigation data source and a responsive `AppShell` (desktop sidebar / mobile top bar + drawer), and give the shell a floor of dialog/drawer/skip-link/route-focus accessibility that later phases reuse.

**Architecture:** Introduce `frontend/src/components/layout/` as the single owner of authenticated shell markup: `navigation.js` (data), `DesktopSidebar.jsx` + `MobileTopBar.jsx` + `MobileNavDrawer.jsx` (presentation), `AppShell.jsx` (composition + focus/skip-link plumbing). A new generic `useFocusTrap` hook backs both the new drawer and the existing `ConfirmDialog`, so trap/Escape/scroll-lock/restore behavior lives in one place. `App.jsx`'s `AppLayout` shrinks to route registration only.

**Tech Stack:** React 18, react-router-dom 7, Tailwind 3.4 (`min-h-dvh` is natively supported), Vitest + React Testing Library, lucide-react icons.

**Spec:** docs/superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design.md (§6, §7.1, §13)

## Global Constraints

- Local/cloud edition boundaries remain intact; Tax Report and Screener stay local-only unless an existing capability manifest explicitly enables them (spec §3).
- The premium theme, design tokens, typography, and shared UI primitives from `2026-08-30-portfyl-premium-redesign-design.md` remain in force — new components consume existing tokens (`--brand`, `--surface-card`, `--ink`, `--muted`, `--hairline`, etc.), never a second visual system (spec §3).
- No new component library, CSS framework, global state manager, or runtime UI dependency (spec §5 principle 7, §19).
- Trust before polish; one source of truth for navigation and async/focus behavior; reversible, isolated, per-phase delivery (spec §5 principles 1, 4, 6).
- `h-screen`, `max-h-screen`, and nested main scrolling are removed; the shell uses `min-h-dvh`; main padding is responsive (`p-4 sm:p-6`) (spec §7.1). Every later plan that touches shell-adjacent markup must not reintroduce a fixed-height or independently-scrolling container.
- The drawer is a labelled modal dialog: closes on Escape and on route change, traps Tab/Shift+Tab, returns focus to its trigger, and prevents background scroll while open (spec §7.1).
- Desktop renders navigation in the sidebar; viewports below the Tailwind `lg` breakpoint (1024px, unmodified default) render a top bar and a modal drawer; capability filtering occurs before either renderer receives the groups (spec §6).
- Git workflow (spec §15): work happens in a dedicated worktree off the current integration-branch HEAD; before editing, run:

  ```powershell
  $branch = (git branch --show-current).Trim()
  if ($branch -eq 'main') { throw 'Refusing to work on main' }
  git status --short
  ```

  Stop if the worktree has unexplained overlapping changes. Commit small coherent steps naming exact files — never `git add -A`. Push the task branch and open a PR targeting `codex/portfyl-ux-overhaul`, never `main`. Merge only after review and green required checks.

**Branch:** `codex/ux-03-responsive-a11y`
**Depends on:** Plan 2 (`codex/ux-02-platform-state`) merged into `codex/portfyl-ux-overhaul`. This plan assumes: `PlatformProvider`/`usePlatform`/`sb_platform` gating and `PlatformLanding`'s role in the *authenticated* route decision are already removed, so `AppLayout` in `App.jsx` renders one route set (not the current two-branch `if (!platform) {...}` / `else {...}` split shown below, which Plan 2 collapses) and an authenticated user with a portfolio already reaches Dashboard directly; `frontend/src/lib/apiError.js` (`getApiErrorMessage(error, fallback)`) and `frontend/src/components/ui/AsyncSection.jsx` (props `isLoading, error, onRetry, loading, isEmpty, empty, children`) exist. This plan does not need to call either directly (the shell itself has no page-level async data beyond the existing `capabilities`/`portfolios` queries in `AppLayout`, which already have their own loading branch), but names them for any later plan reusing shell code.
**Merges into:** `codex/portfyl-ux-overhaul`

**Backend impact:** none. Nav-group capability filtering is 100% client-side today: `frontend/src/editions/filter.js`'s `enabledEditionEntries(entries, capabilities)` filters against the `capabilities` array already returned by `GET /api/capabilities` and fetched in `AppLayout` (`App.jsx`, `useQuery({ queryKey: ["capabilities"], queryFn: fetchCapabilities })`). No backend route or manifest changes are required for this plan; the backend fast/Postgres suites are not part of this phase's gate.

**Sequencing note:** the Style / Appearance / Accent / Display-currency controls currently at the bottom of `Sidebar.jsx` are carried into `DesktopSidebar.jsx` unchanged by this plan. Spec §6's instruction to move them into **Settings → Preferences** is Plan 7's job (it builds the four URL-addressable Settings sections these controls need a home in) — Plan 7 removes them from the sidebar and shrinks it to "portfolio switching, account menu, and compact provider/freshness attribution" per the spec's end state. Do not attempt that relocation here.

---

## Current state (read before starting)

- `frontend/src/components/Sidebar.jsx` (193 lines): fixed `w-[232px] ... h-screen sticky top-0` `<aside>`. Renders `T212_LINKS` (11 hardcoded entries including "Overview") + `enabledEditionEntries(EDITION_NAVIGATION, capabilities)`, gated by `platform === "t212"`. Bottom section (lines 90-189): `AccountMenu`, Style `SegmentedControl`, Appearance `SegmentedControl`, Accent palette buttons, Currency toggle, "Live data via Yahoo Finance" attribution line.
- `frontend/src/App.jsx` (484 lines): `AppLayout` (lines 411-484) currently branches on `usePlatform()` — Plan 2 collapses this to one branch before this plan starts. The shared shell markup either branch uses today: `<div className="flex min-h-screen"><EditionShell/>{platform === "t212" && <AutoLoad/>}<Sidebar capabilities={...}/><main className="flex-1 p-6 overflow-y-auto min-w-0 max-h-screen"><Routes>...</Routes></main></div>`. The `/overview` route renders `<Overview/>` today.
- `frontend/src/editions/local.jsx` exports `EDITION_NAVIGATION = [{ to: "/tax-report", label: "Tax Report", icon: FileText, capability: "tax_report" }, { to: "/screener", label: "Screener", icon: Filter, capability: "screener" }]`. `frontend/src/editions/cloud.jsx` exports `EDITION_NAVIGATION = [{ to: "/pricing", label: "Plans", icon: Layers3, capability: "settings" }]`.
- `frontend/src/components/ui/ConfirmDialog.jsx` (154 lines) already has a hand-rolled 2-button Tab trap, Escape-close, `role="alertdialog"`, `aria-modal`, body-scroll lock — but **no focus restoration** to the element that opened it. This plan generalizes its trap into a reusable hook and gets restoration "for free."
- `frontend/src/pages/Overview.jsx`, `frontend/src/pages/Overview.test.jsx`, and `api.js`'s `fetchOverview` (line 152) have no other consumers repo-wide today besides `Overview.jsx` itself, its test, and the `/overview` route/nav-link this plan removes — confirmed by grep. Once this plan removes the route and nav entry, the spec §6 condition for deletion ("a repository-wide reference scan proves they have no remaining consumers") is met, so Task 6 below deletes them rather than leaving dead code.
- No global `prefers-reduced-motion` CSS guard exists yet; `frontend/src/hooks/useCountUp.js` is the only existing per-component JS `matchMedia("(prefers-reduced-motion: reduce)")` check in the repo — the new drawer's transition follows that same per-component pattern (spec §19 forbids new runtime dependencies, so no motion library).
- Tailwind config (`frontend/tailwind.config.js`) does not override the `lg` breakpoint — it stays the Tailwind default, 1024px / `min-width: 64rem`.

---

### Task 1: Navigation data source

**Files:**
- Create: `frontend/src/components/layout/navigation.js`
- Test: `frontend/src/components/layout/navigation.test.js`

**Interfaces:**
- Produces: `NAV_GROUPS` (static array of `{ id, label, items: [{ to, label, icon }] }`, 5 groups: `portfolio`, `research`, `insights`, `assistant`, `system` — items exclude edition-gated entries), `buildNavGroups(editionEntries, capabilities)` → returns the full merged, capability-filtered array of `{ id, label, items }` ready for both renderers. `EDITION_ENTRY_GROUP` (object mapping edition-nav `to` path → group id, e.g. `{"/tax-report": "insights", "/screener": "research"}`) and `DEFAULT_EDITION_GROUP = "system"` for any edition entry without an explicit mapping (e.g. cloud's `/pricing`).

- [ ] **Step 1: Write the failing test**

```js
// frontend/src/components/layout/navigation.test.js
import { describe, expect, it } from "vitest";
import { buildNavGroups, NAV_GROUPS } from "./navigation";
import { TRACKER_HOME } from "../../lib/routes";

describe("NAV_GROUPS", () => {
  it("has exactly the five named groups in order", () => {
    expect(NAV_GROUPS.map((g) => g.id)).toEqual([
      "portfolio",
      "research",
      "insights",
      "assistant",
      "system",
    ]);
  });

  it("does not contain an Overview entry anywhere", () => {
    const allLabels = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.label));
    expect(allLabels).not.toContain("Overview");
  });

  it("portfolio group has Dashboard, Allocation, Transactions", () => {
    const portfolio = NAV_GROUPS.find((g) => g.id === "portfolio");
    expect(portfolio.items.map((i) => i.to)).toEqual([
      TRACKER_HOME,
      "/allocation",
      "/transactions",
    ]);
  });
});

describe("buildNavGroups", () => {
  const taxReportEntry = { to: "/tax-report", label: "Tax Report", icon: () => null, capability: "tax_report" };
  const screenerEntry = { to: "/screener", label: "Screener", icon: () => null, capability: "screener" };
  const pricingEntry = { to: "/pricing", label: "Plans", icon: () => null, capability: "settings" };

  it("merges Tax Report into Insights and Screener into Research when capabilities enable them", () => {
    const groups = buildNavGroups(
      [taxReportEntry, screenerEntry],
      ["tax_report", "screener"]
    );
    const insights = groups.find((g) => g.id === "insights");
    const research = groups.find((g) => g.id === "research");
    expect(insights.items.some((i) => i.to === "/tax-report")).toBe(true);
    expect(research.items.some((i) => i.to === "/screener")).toBe(true);
  });

  it("omits an edition entry whose capability is not enabled", () => {
    const groups = buildNavGroups([taxReportEntry], []);
    const insights = groups.find((g) => g.id === "insights");
    expect(insights.items.some((i) => i.to === "/tax-report")).toBe(false);
  });

  it("falls back unmapped edition entries to the System group", () => {
    const groups = buildNavGroups([pricingEntry], ["settings"]);
    const system = groups.find((g) => g.id === "system");
    expect(system.items.some((i) => i.to === "/pricing")).toBe(true);
  });

  it("never mutates the base NAV_GROUPS array", () => {
    const before = JSON.parse(JSON.stringify(NAV_GROUPS.map((g) => g.items.map((i) => i.to))));
    buildNavGroups([taxReportEntry], ["tax_report"]);
    const after = NAV_GROUPS.map((g) => g.items.map((i) => i.to));
    expect(after).toEqual(before);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/layout/navigation.test.js`
Expected: FAIL — `Cannot find module './navigation'` (file doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

```js
// frontend/src/components/layout/navigation.js
import {
  LayoutDashboard,
  PieChart,
  ArrowLeftRight,
  Search,
  Star,
  CalendarDays,
  Activity,
  Upload,
  Settings as SettingsIcon,
  Bot,
} from "lucide-react";
import { TRACKER_HOME } from "../../lib/routes";

export const NAV_GROUPS = Object.freeze([
  {
    id: "portfolio",
    label: "Portfolio",
    items: [
      { to: TRACKER_HOME, label: "Dashboard", icon: LayoutDashboard },
      { to: "/allocation", label: "Allocation", icon: PieChart },
      { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
    ],
  },
  {
    id: "research",
    label: "Research",
    items: [
      { to: "/search", label: "Search", icon: Search },
      { to: "/watchlists", label: "Watchlists", icon: Star },
    ],
  },
  {
    id: "insights",
    label: "Insights",
    items: [
      { to: "/dividends", label: "Dividends", icon: CalendarDays },
      { to: "/analytics", label: "Analytics", icon: Activity },
    ],
  },
  {
    id: "assistant",
    label: "Assistant",
    items: [{ to: "/assistant", label: "AI Assistant", icon: Bot }],
  },
  {
    id: "system",
    label: "System",
    items: [
      { to: "/import", label: "Import", icon: Upload },
      { to: "/settings", label: "Settings", icon: SettingsIcon },
    ],
  },
]);

// Until edition manifests expose a group field directly, this adapter assigns
// known edition nav entries to their spec-mandated group and anything
// unrecognized (e.g. cloud's /pricing) to System — see spec §6.
export const EDITION_ENTRY_GROUP = Object.freeze({
  "/tax-report": "insights",
  "/screener": "research",
});
export const DEFAULT_EDITION_GROUP = "system";

export function buildNavGroups(editionEntries, capabilities) {
  const enabled = new Set(capabilities || []);
  const groups = NAV_GROUPS.map((g) => ({ ...g, items: [...g.items] }));
  for (const entry of editionEntries || []) {
    if (!enabled.has(entry.capability)) continue;
    const groupId = EDITION_ENTRY_GROUP[entry.to] || DEFAULT_EDITION_GROUP;
    const group = groups.find((g) => g.id === groupId);
    if (group) group.items.push(entry);
  }
  return groups;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/layout/navigation.test.js`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/navigation.js frontend/src/components/layout/navigation.test.js
git commit -m "feat(nav): add single navigation-group data source"
```

---

### Task 2: Generic focus-trap hook, retrofit ConfirmDialog

**Files:**
- Create: `frontend/src/hooks/useFocusTrap.js`
- Test: `frontend/src/hooks/useFocusTrap.test.jsx`
- Modify: `frontend/src/components/ui/ConfirmDialog.jsx:60-93` (replace the hand-rolled 2-button trap with the hook)

**Interfaces:**
- Produces: `useFocusTrap({ active, onEscape, initialFocusRef }) → containerRef` (attach `containerRef` to the dialog/drawer's outer DOM node). While `active`, it: saves `document.activeElement`; focuses `initialFocusRef.current` or the first focusable descendant; traps Tab/Shift+Tab among focusable descendants; calls `onEscape()` on Escape; locks `document.body.style.overflow`; on cleanup (unmount or `active` becoming false) restores the previously-focused element and body overflow.
- Consumes (Task 3, 4): any later dialog/drawer imports `useFocusTrap` from `frontend/src/hooks/useFocusTrap.js` with this exact signature.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/hooks/useFocusTrap.test.jsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useRef, useState } from "react";
import { useFocusTrap } from "./useFocusTrap";

function Harness() {
  const [open, setOpen] = useState(false);
  const trapRef = useFocusTrap({ active: open, onEscape: () => setOpen(false) });
  return (
    <div>
      <button onClick={() => setOpen(true)}>Open</button>
      {open && (
        <div ref={trapRef} role="dialog" aria-modal="true">
          <button>First</button>
          <button>Last</button>
        </div>
      )}
    </div>
  );
}

describe("useFocusTrap", () => {
  it("focuses the first focusable element on open", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    expect(screen.getByText("First")).toHaveFocus();
  });

  it("wraps Tab from the last element back to the first", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    screen.getByText("Last").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByText("First")).toHaveFocus();
  });

  it("wraps Shift+Tab from the first element back to the last", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByText("Last")).toHaveFocus();
  });

  it("calls onEscape on Escape", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("restores focus to the trigger on close", () => {
    render(<Harness />);
    const opener = screen.getByText("Open");
    fireEvent.click(opener);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(opener).toHaveFocus();
  });

  it("locks and restores body scroll", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("Open"));
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.body.style.overflow).not.toBe("hidden");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useFocusTrap.test.jsx`
Expected: FAIL — `Cannot find module './useFocusTrap'`.

- [ ] **Step 3: Write minimal implementation**

```js
// frontend/src/hooks/useFocusTrap.js
import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useFocusTrap({ active, onEscape, initialFocusRef } = {}) {
  const containerRef = useRef(null);
  const previouslyFocusedRef = useRef(null);

  useEffect(() => {
    if (!active) return undefined;

    previouslyFocusedRef.current = document.activeElement;
    const container = containerRef.current;

    const focusables = () =>
      container
        ? Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
            (el) => el.offsetParent !== null
          )
        : [];

    const target = initialFocusRef?.current || focusables()[0];
    target?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        if (onEscape) {
          event.preventDefault();
          onEscape();
        }
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = prevOverflow;
      previouslyFocusedRef.current?.focus?.();
    };
  }, [active, onEscape, initialFocusRef]);

  return containerRef;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/hooks/useFocusTrap.test.jsx`
Expected: PASS (6 tests).

- [ ] **Step 5: Retrofit ConfirmDialog to use the hook**

Replace `frontend/src/components/ui/ConfirmDialog.jsx:60-93` (the `ConfirmDialog` function body's `useRef`/`useEffect` block) with:

```jsx
function ConfirmDialog({ title, message, confirmLabel, cancelLabel, danger, onResolve }) {
  const confirmBtnRef = useRef(null);
  const cancelBtnRef = useRef(null);
  const titleId = "confirm-dialog-title";
  const descId = "confirm-dialog-desc";

  const containerRef = useFocusTrap({
    active: true,
    onEscape: () => onResolve(false),
    // Destructive dialogs default focus to Cancel so an accidental Enter is safe.
    initialFocusRef: danger ? cancelBtnRef : confirmBtnRef,
  });

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4"
      style={{ backdropFilter: "blur(var(--blur-overlay))" }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onResolve(false);
      }}
    >
      <div
        ref={containerRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={message ? descId : undefined}
        className="card w-full max-w-sm space-y-4"
      >
```

Add `import { useFocusTrap } from "../../hooks/useFocusTrap";` and remove the now-unused `useEffect` import if nothing else in the file uses it (check remaining usages first). Keep the rest of the JSX (buttons, danger icon, etc.) unchanged — only the trap/Escape/scroll-lock wiring moves into the hook, and focus restoration is now free.

- [ ] **Step 6: Run existing ConfirmDialog tests plus the new hook test**

Run: `cd frontend && npx vitest run src/components/ui/ConfirmDialog.test.jsx src/hooks/useFocusTrap.test.jsx` (if no `ConfirmDialog.test.jsx` exists yet, grep `frontend/src -name "*ConfirmDialog*"` first and instead run `npx vitest run src/components/ui/primitives.test.jsx` if that's where its coverage lives, adjusting the command to the file the grep finds)
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useFocusTrap.js frontend/src/hooks/useFocusTrap.test.jsx frontend/src/components/ui/ConfirmDialog.jsx
git commit -m "feat(a11y): extract reusable focus-trap hook, add focus restoration to ConfirmDialog"
```

---

### Task 3: DesktopSidebar

**Files:**
- Create: `frontend/src/components/layout/DesktopSidebar.jsx`
- Test: `frontend/src/components/layout/DesktopSidebar.test.jsx`
- (Deletion of the old `frontend/src/components/Sidebar.jsx` happens in Task 6, once `AppShell` — Task 5 — is wired into `App.jsx` and nothing imports the old file.)

**Interfaces:**
- Consumes: `NAV_GROUPS`/`buildNavGroups` from Task 1 (`../layout/navigation`), `useCurrency`/`usePalette` from `../../App` (unchanged), `PortfolioSwitcher`, `AccountMenu`, `SegmentedControl` (unchanged imports from their current locations).
- Produces: `DesktopSidebar({ groups })` — a `<nav>`-grouped rendering of `groups` (the already-filtered array `buildNavGroups` returns), each group rendered under a visually-labelled `<h2>`/section, plus the unchanged bottom block (Account, Style, Appearance, Accent, Currency, attribution line) ported verbatim from the current `Sidebar.jsx`.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/components/layout/DesktopSidebar.test.jsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DesktopSidebar from "./DesktopSidebar";
import { NAV_GROUPS } from "./navigation";

vi.mock("../../App", () => ({
  useCurrency: () => ({ currency: "USD", setCurrency: vi.fn(), rate: 21, rateLoading: false }),
  usePalette: () => ({
    palette: "blue",
    setPalette: vi.fn(),
    theme: "light",
    setTheme: vi.fn(),
    themeStyle: "glass",
    setThemeStyle: vi.fn(),
  }),
  usePortfolio: () => ({ portfolios: [], current: null, currentId: null, setCurrentId: vi.fn() }),
}));

function renderSidebar(groups = NAV_GROUPS) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DesktopSidebar groups={groups} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DesktopSidebar", () => {
  it("renders every group label as a heading", () => {
    renderSidebar();
    for (const group of NAV_GROUPS) {
      expect(screen.getByText(group.label)).toBeInTheDocument();
    }
  });

  it("renders every item as an accessible nav link", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ai assistant/i })).toBeInTheDocument();
  });

  it("does not render an Overview link", () => {
    renderSidebar();
    expect(screen.queryByRole("link", { name: /^overview$/i })).not.toBeInTheDocument();
  });

  it("renders the nav landmark with an accessible name", () => {
    renderSidebar();
    expect(screen.getByRole("navigation", { name: /primary/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/layout/DesktopSidebar.test.jsx`
Expected: FAIL — `Cannot find module './DesktopSidebar'`.

- [ ] **Step 3: Write minimal implementation**

```jsx
// frontend/src/components/layout/DesktopSidebar.jsx
import { NavLink } from "react-router-dom";
import { Loader2, Sun, Moon, Monitor } from "lucide-react";
import { useCurrency, usePalette } from "../../App";
import PortfolioSwitcher from "../PortfolioSwitcher";
import AccountMenu from "../AccountMenu";
import SegmentedControl from "../ui/SegmentedControl";

const PALETTE_OPTIONS = [
  { key: "blue", label: "Arctic Blue" },
  { key: "green", label: "Mint Green" },
  { key: "purple", label: "Soft Iris" },
];

export default function DesktopSidebar({ groups }) {
  const { currency, setCurrency, rate, rateLoading } = useCurrency();
  const { palette, setPalette, theme, setTheme, themeStyle, setThemeStyle } = usePalette();
  const czk_unavailable = !rateLoading && rate === null;

  return (
    <aside
      className="w-[232px] shrink-0 bg-surface-card border-r border-surface-border flex flex-col"
      style={{ boxShadow: "1px 0 0 var(--glass-border-alpha)" }}
    >
      <div className="flex items-center gap-2.5 px-[18px] py-4 border-b border-hairline">
        <img src="/portfyl-mark.png" alt="Portfyl" className="w-11 h-11 object-contain" />
        <div className="flex flex-col leading-tight">
          <span className="font-display font-bold text-[17px] tracking-tight text-ink">Portfyl</span>
          <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-muted">Institutional Grade</span>
        </div>
      </div>

      <div className="px-3 pt-2">
        <PortfolioSwitcher />
      </div>

      <nav aria-label="Primary" className="flex-1 px-2.5 py-2 space-y-3 overflow-y-auto">
        {groups.map((group) => (
          <div key={group.id}>
            <h2 className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
              {group.label}
            </h2>
            <div className="space-y-0.5">
              {group.items.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-all ${
                      isActive
                        ? "font-semibold text-brand bg-[var(--sidebar-active)] shadow-[inset_0_0_0_1px_var(--glass-border-alpha)]"
                        : "text-muted hover:text-ink hover:bg-surface-hover"
                    }`
                  }
                >
                  <Icon size={16} />
                  {label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="mt-auto pb-3 space-y-3">
        <div className="px-3">
          <AccountMenu />
        </div>

        <div className="px-4">
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Style</p>
          <SegmentedControl
            block
            size="sm"
            aria-label="Theme style"
            value={themeStyle}
            onChange={setThemeStyle}
            options={[
              { value: "glass", label: "Classic", title: "Classic glass theme" },
              { value: "neu", label: "Premium", title: "Warm glass-hybrid theme" },
            ]}
          />
        </div>

        <div className={`px-4 ${themeStyle === "neu" ? "opacity-40 pointer-events-none" : ""}`}>
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Appearance</p>
          <SegmentedControl
            block
            size="sm"
            aria-label="Appearance"
            value={theme}
            onChange={setTheme}
            options={[
              { value: "light", label: <Sun size={13} />, title: "Light", disabled: themeStyle === "neu" },
              { value: "dark", label: <Moon size={13} />, title: "Dark", disabled: themeStyle === "neu" },
              { value: "system", label: <Monitor size={13} />, title: "System", disabled: themeStyle === "neu" },
            ]}
          />
        </div>

        <div className={`px-4 ${themeStyle === "neu" ? "opacity-40 pointer-events-none" : ""}`}>
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Accent</p>
          <div className="flex gap-1.5">
            {PALETTE_OPTIONS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setPalette(key)}
                disabled={themeStyle === "neu"}
                title={label}
                aria-label={`Theme: ${label}`}
                aria-pressed={palette === key}
                className={`w-5 h-5 rounded-full transition-all ${
                  palette === key ? "ring-2 ring-offset-1 ring-slate-400 scale-110" : "hover:scale-110"
                }`}
                style={{ backgroundColor: { blue: "#2563EB", green: "#059669", purple: "#7C3AED" }[key] }}
              />
            ))}
          </div>
        </div>

        <div className="px-4 space-y-2">
          <p className="text-[10px] text-muted pl-0.5">Display currency</p>
          <div className="flex items-center gap-0.5 bg-surface-hover rounded-lg p-0.5">
            {["USD", "CZK"].map((c) => (
              <button
                key={c}
                onClick={() => setCurrency(c)}
                disabled={c === "CZK" && czk_unavailable}
                title={c === "CZK" && czk_unavailable ? "Rate unavailable" : undefined}
                aria-label={`Display currency: ${c}`}
                aria-pressed={currency === c}
                className={`flex-1 text-xs py-1.5 rounded-md font-semibold transition-colors ${
                  currency === c
                    ? "bg-brand text-white"
                    : czk_unavailable && c === "CZK"
                    ? "text-muted cursor-not-allowed"
                    : "text-muted hover:text-ink"
                }`}
              >
                {c === "CZK" && rateLoading ? <Loader2 size={11} className="animate-spin mx-auto" /> : c}
              </button>
            ))}
          </div>
          {currency === "CZK" && rate && (
            <p className="text-[10px] text-muted text-center tabular-nums">1 USD = {rate.toFixed(2)} Kc</p>
          )}
          {czk_unavailable && <p className="text-[10px] text-loss text-center">Rate unavailable</p>}
        </div>

        <div className="px-5 text-[11px] text-muted" style={{ opacity: 0.7 }}>
          Live data via Yahoo Finance
        </div>
      </div>
    </aside>
  );
}
```

Note the removed `h-screen sticky top-0` from the `<aside>` (per Global Constraints) and the removed `usePlatform`/back-button block (Plan 2 already removed that concept).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/layout/DesktopSidebar.test.jsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/DesktopSidebar.jsx frontend/src/components/layout/DesktopSidebar.test.jsx
git commit -m "feat(nav): add grouped DesktopSidebar consuming the shared navigation source"
```

---

### Task 4: MobileTopBar and MobileNavDrawer

**Files:**
- Create: `frontend/src/components/layout/MobileTopBar.jsx`
- Create: `frontend/src/components/layout/MobileNavDrawer.jsx`
- Test: `frontend/src/components/layout/MobileNavDrawer.test.jsx`

**Interfaces:**
- Consumes: `useFocusTrap` (Task 2), `NAV_GROUPS`-shaped `groups` prop (Task 1).
- Produces: `MobileTopBar({ onOpenMenu })` — a `<header>` with a hamburger `<button aria-label="Open navigation menu" aria-expanded aria-controls="mobile-nav-drawer">` and the Portfyl mark. `MobileNavDrawer({ groups, open, onClose })` — modal drawer with `id="mobile-nav-drawer"`, `role="dialog"`, `aria-modal="true"`, `aria-label="Navigation"`; closes on Escape (via `useFocusTrap`'s `onEscape`), backdrop click, and route change (via `useLocation` inside, calling `onClose` in an effect keyed on `pathname`); respects `prefers-reduced-motion` by skipping the slide transition when the user prefers reduced motion.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/components/layout/MobileNavDrawer.test.jsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import MobileNavDrawer from "./MobileNavDrawer";
import { NAV_GROUPS } from "./navigation";

function renderDrawer(open = true, onClose = vi.fn()) {
  return render(
    <MemoryRouter>
      <button>Menu trigger</button>
      <MobileNavDrawer groups={NAV_GROUPS} open={open} onClose={onClose} />
    </MemoryRouter>
  );
}

describe("MobileNavDrawer", () => {
  it("renders nothing when closed", () => {
    renderDrawer(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders as a labelled modal dialog when open", () => {
    renderDrawer(true);
    const dialog = screen.getByRole("dialog", { name: /navigation/i });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    renderDrawer(true, onClose);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    renderDrawer(true, onClose);
    fireEvent.mouseDown(screen.getByTestId("mobile-nav-backdrop"));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders every nav item as a link", () => {
    renderDrawer(true);
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/layout/MobileNavDrawer.test.jsx`
Expected: FAIL — `Cannot find module './MobileNavDrawer'`.

- [ ] **Step 3: Write minimal implementation**

```jsx
// frontend/src/components/layout/MobileTopBar.jsx
import { Menu } from "lucide-react";

export default function MobileTopBar({ onOpenMenu }) {
  return (
    <header className="lg:hidden flex items-center justify-between px-4 py-3 bg-surface-card border-b border-hairline">
      <div className="flex items-center gap-2">
        <img src="/portfyl-mark.png" alt="Portfyl" className="w-8 h-8 object-contain" />
        <span className="font-display font-bold text-[15px] text-ink">Portfyl</span>
      </div>
      <button
        type="button"
        onClick={onOpenMenu}
        aria-label="Open navigation menu"
        aria-expanded="false"
        aria-controls="mobile-nav-drawer"
        className="p-2 rounded-lg text-muted hover:text-ink hover:bg-surface-hover"
      >
        <Menu size={22} />
      </button>
    </header>
  );
}
```

```jsx
// frontend/src/components/layout/MobileNavDrawer.jsx
import { useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { X } from "lucide-react";
import { useFocusTrap } from "../../hooks/useFocusTrap";

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

export default function MobileNavDrawer({ groups, open, onClose }) {
  const { pathname } = useLocation();
  const containerRef = useFocusTrap({ active: open, onEscape: onClose });

  // Route change closes the drawer (spec §7.1).
  useEffect(() => {
    if (open) onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  if (!open) return null;

  const transitionClass = prefersReducedMotion() ? "" : "transition-transform duration-200 ease-out";

  return (
    <div
      data-testid="mobile-nav-backdrop"
      className="lg:hidden fixed inset-0 z-[70] bg-black/30"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={containerRef}
        id="mobile-nav-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        className={`h-full w-[280px] max-w-[85vw] bg-surface-card border-r border-hairline overflow-y-auto ${transitionClass}`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-hairline">
          <span className="font-display font-bold text-[15px] text-ink">Navigation</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation menu"
            className="p-2 rounded-lg text-muted hover:text-ink hover:bg-surface-hover"
          >
            <X size={20} />
          </button>
        </div>
        <nav aria-label="Primary" className="px-2.5 py-2 space-y-3">
          {groups.map((group) => (
            <div key={group.id}>
              <h2 className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                {group.label}
              </h2>
              <div className="space-y-0.5">
                {group.items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === "/"}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] ${
                        isActive ? "font-semibold text-brand bg-[var(--sidebar-active)]" : "text-muted hover:text-ink hover:bg-surface-hover"
                      }`
                    }
                  >
                    <Icon size={16} />
                    {label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/layout/MobileNavDrawer.test.jsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/MobileTopBar.jsx frontend/src/components/layout/MobileNavDrawer.jsx frontend/src/components/layout/MobileNavDrawer.test.jsx
git commit -m "feat(nav): add mobile top bar and focus-trapped nav drawer"
```

---

### Task 5: Route-focus announcer hook

**Files:**
- Create: `frontend/src/hooks/useRouteFocusAnnouncer.js`
- Test: `frontend/src/hooks/useRouteFocusAnnouncer.test.jsx`

**Interfaces:**
- Produces: `useRouteFocusAnnouncer(mainRef)` — a hook (no return value) that, on every `pathname` change (via `useLocation`), finds the first `<h1>` inside `mainRef.current`, ensures it has `tabIndex={-1}` (sets the attribute if missing, without touching page source), and calls `.focus()` on it (falling back to focusing `mainRef.current` itself, which must carry `tabIndex={-1}`, if no `<h1>` is found). Skips the very first render (initial mount) so it doesn't steal focus from whatever the browser/user already focused on load.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/hooks/useRouteFocusAnnouncer.test.jsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";
import { useEffect, useRef } from "react";
import { useRouteFocusAnnouncer } from "./useRouteFocusAnnouncer";

function Shell({ children }) {
  const mainRef = useRef(null);
  useRouteFocusAnnouncer(mainRef);
  return (
    <main ref={mainRef} id="main-content" tabIndex={-1}>
      {children}
    </main>
  );
}

function PageA() {
  const navigate = useNavigate();
  return (
    <div>
      <h1>Page A</h1>
      <button onClick={() => navigate("/b")}>Go to B</button>
    </div>
  );
}
function PageB() {
  return <h1>Page B</h1>;
}

function Harness() {
  return (
    <Shell>
      <Routes>
        <Route path="/a" element={<PageA />} />
        <Route path="/b" element={<PageB />} />
      </Routes>
    </Shell>
  );
}

describe("useRouteFocusAnnouncer", () => {
  it("focuses the new page's h1 after a route change", async () => {
    render(
      <MemoryRouter initialEntries={["/a"]}>
        <Harness />
      </MemoryRouter>
    );
    screen.getByText("Go to B").click();
    const heading = await screen.findByText("Page B");
    expect(heading).toHaveFocus();
    expect(heading).toHaveAttribute("tabindex", "-1");
  });

  it("does not steal focus on the initial render", () => {
    render(
      <MemoryRouter initialEntries={["/a"]}>
        <Harness />
      </MemoryRouter>
    );
    expect(document.body).toHaveFocus();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useRouteFocusAnnouncer.test.jsx`
Expected: FAIL — `Cannot find module './useRouteFocusAnnouncer'`.

- [ ] **Step 3: Write minimal implementation**

```js
// frontend/src/hooks/useRouteFocusAnnouncer.js
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

export function useRouteFocusAnnouncer(mainRef) {
  const { pathname } = useLocation();
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    const main = mainRef.current;
    if (!main) return;
    const heading = main.querySelector("h1");
    const target = heading || main;
    if (heading && !heading.hasAttribute("tabindex")) {
      heading.setAttribute("tabindex", "-1");
    }
    target.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/hooks/useRouteFocusAnnouncer.test.jsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useRouteFocusAnnouncer.js frontend/src/hooks/useRouteFocusAnnouncer.test.jsx
git commit -m "feat(a11y): focus the new page heading after route changes"
```

---

### Task 6: AppShell composition, skip link, and wiring into App.jsx (incl. /overview retirement)

**Files:**
- Create: `frontend/src/components/layout/AppShell.jsx`
- Test: `frontend/src/components/layout/AppShell.test.jsx`
- Modify: `frontend/src/App.jsx` (`AppLayout`, lines ~411-484 in the pre-Plan-2 file — locate by function name, not line number, since Plan 2 already changed this file)
- Modify: `frontend/src/index.css` (add `.skip-link` utility)
- Delete: `frontend/src/components/Sidebar.jsx`, `frontend/src/pages/Overview.jsx`, `frontend/src/pages/Overview.test.jsx`
- Modify: `frontend/src/api.js` (remove `fetchOverview`, line 152 in the current file)

**Interfaces:**
- Consumes: `buildNavGroups` (Task 1), `DesktopSidebar` (Task 3), `MobileTopBar`/`MobileNavDrawer` (Task 4), `useRouteFocusAnnouncer` (Task 5).
- Produces: `AppShell({ groups, children })` — renders the skip link, `DesktopSidebar` (`hidden lg:flex`), `MobileTopBar` + `MobileNavDrawer` (visible below `lg`), and `<main id="main-content" tabIndex={-1} className="flex-1 min-w-0 p-4 sm:p-6">{children}</main>` inside a `min-h-dvh` wrapper — no `h-screen`/`max-h-screen`/`overflow-y-auto` anywhere in the tree.

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/components/layout/AppShell.test.jsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AppShell from "./AppShell";
import { NAV_GROUPS } from "./navigation";

vi.mock("../../App", () => ({
  useCurrency: () => ({ currency: "USD", setCurrency: vi.fn(), rate: 21, rateLoading: false }),
  usePalette: () => ({
    palette: "blue", setPalette: vi.fn(), theme: "light", setTheme: vi.fn(),
    themeStyle: "glass", setThemeStyle: vi.fn(),
  }),
  usePortfolio: () => ({ portfolios: [], current: null, currentId: null, setCurrentId: vi.fn() }),
}));

function renderShell() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AppShell groups={NAV_GROUPS}>
          <h1>Test Page</h1>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  it("renders a skip link targeting #main-content", () => {
    renderShell();
    const link = screen.getByRole("link", { name: /skip to main content/i });
    expect(link).toHaveAttribute("href", "#main-content");
  });

  it("renders exactly one main landmark with the shared id", () => {
    renderShell();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("renders the page content inside main", () => {
    renderShell();
    expect(screen.getByRole("heading", { name: "Test Page" })).toBeInTheDocument();
  });

  it("opens and closes the mobile drawer from the top bar button", () => {
    renderShell();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /open navigation menu/i }));
    expect(screen.getByRole("dialog", { name: /navigation/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close navigation menu/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not render h-screen or max-h-screen anywhere in the shell", () => {
    const { container } = renderShell();
    expect(container.innerHTML).not.toMatch(/\bh-screen\b/);
    expect(container.innerHTML).not.toMatch(/\bmax-h-screen\b/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/layout/AppShell.test.jsx`
Expected: FAIL — `Cannot find module './AppShell'`.

- [ ] **Step 3: Write minimal implementation**

```jsx
// frontend/src/components/layout/AppShell.jsx
import { useRef, useState } from "react";
import DesktopSidebar from "./DesktopSidebar";
import MobileTopBar from "./MobileTopBar";
import MobileNavDrawer from "./MobileNavDrawer";
import { useRouteFocusAnnouncer } from "../../hooks/useRouteFocusAnnouncer";

export default function AppShell({ groups, children }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const mainRef = useRef(null);
  useRouteFocusAnnouncer(mainRef);

  return (
    <div className="flex min-h-dvh">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <div className="hidden lg:flex">
        <DesktopSidebar groups={groups} />
      </div>

      <div className="flex-1 min-w-0 flex flex-col">
        <MobileTopBar onOpenMenu={() => setDrawerOpen(true)} />
        <MobileNavDrawer groups={groups} open={drawerOpen} onClose={() => setDrawerOpen(false)} />
        <main id="main-content" ref={mainRef} tabIndex={-1} className="flex-1 min-w-0 p-4 sm:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

Add to `frontend/src/index.css` (near other utility classes — check the file's existing structure and place alongside similar single-purpose utilities):

```css
.skip-link {
  position: absolute;
  left: 0.5rem;
  top: -3rem;
  z-index: 100;
  background: var(--surface-card);
  color: var(--ink);
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid var(--border);
  transition: top 0.15s ease-out;
}
.skip-link:focus {
  top: 0.5rem;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/layout/AppShell.test.jsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Wire AppShell into App.jsx, retire the old Sidebar and Overview**

In `frontend/src/App.jsx`, replace the `AppLayout` function's shell markup (post-Plan-2, this is the single non-branching return) so it becomes:

```jsx
import AppShell from "./components/layout/AppShell";
import { buildNavGroups } from "./components/layout/navigation";
// remove: import Sidebar from "./components/Sidebar";
// remove: import Overview from "./pages/Overview";

function AppLayout() {
  const { portfolios, isLoading: portfoliosLoading } = usePortfolio();
  const { data: capabilityState } = useQuery({
    queryKey: ["capabilities"],
    queryFn: fetchCapabilities,
    staleTime: Infinity,
    retry: false,
  });
  const runtimeCapabilities = capabilityState?.capabilities || [];
  const editionRoutes = enabledEditionEntries(EDITION_ROUTES, runtimeCapabilities);
  const navGroups = buildNavGroups(EDITION_NAVIGATION, runtimeCapabilities);

  if (portfoliosLoading) {
    return <AuthSplash />;
  }

  if (!portfolios.length) {
    return <Onboarding />;
  }

  return (
    <AppShell groups={navGroups}>
      <EditionShell />
      <AutoLoad />
      <Routes>
        <Route path={TRACKER_HOME} element={<Dashboard />} />
        <Route path="/overview" element={<Navigate to={TRACKER_HOME} replace />} />
        <Route path="/allocation" element={<Allocation />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/import" element={<Import />} />
        <Route path="/dividends" element={<Dividends />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/search" element={<Search />} />
        <Route path="/stock/:ticker" element={<Stock />} />
        <Route path="/watchlists" element={<Watchlists />} />
        <Route path="/assistant" element={<Assistant />} />
        {editionRoutes.map(({ path, Component }) => (
          <Route key={path} path={path} element={<Component />} />
        ))}
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to={TRACKER_HOME} replace />} />
      </Routes>
    </AppShell>
  );
}
```

Add `import { EDITION_NAVIGATION } from "@edition-manifest";` alongside the existing `EDITION_ROUTES` import if not already present. Reconcile this against whatever Plan 2 actually left in `AppLayout` (it removed the `!platform`/`platform` branch and the `<AutoLoad/>` conditional on `platform === "t212"`) — the route list above is the full previously-platform-gated set, now unconditional.

- [ ] **Step 6: Repository-wide reference scan before deleting Overview/Sidebar**

Run: `cd frontend && grep -rn "Overview" src --include="*.jsx" --include="*.js" | grep -v "src/pages/Overview" ; grep -rn "fetchOverview" src ; grep -rn "components/Sidebar\"" src`
Expected: no output beyond `App.jsx`'s now-removed import (already edited in Step 5) — confirming zero remaining consumers of `Overview.jsx`, `Overview.test.jsx`, `fetchOverview`, and the old `Sidebar.jsx`.

- [ ] **Step 7: Delete the retired files**

```bash
git rm frontend/src/components/Sidebar.jsx frontend/src/pages/Overview.jsx frontend/src/pages/Overview.test.jsx
```

Remove the `fetchOverview` export from `frontend/src/api.js` (currently line 152) — delete only that function, leaving surrounding exports untouched.

- [ ] **Step 8: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: PASS — including `App.routing.test.jsx` (already updated by Plan 2 for platform removal; if it still references `/overview` expecting `<Overview/>` content, update its assertion to expect a redirect to `TRACKER_HOME` instead, and add one new assertion: navigating to `/overview` results in `location.pathname === TRACKER_HOME`).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/layout/AppShell.jsx frontend/src/components/layout/AppShell.test.jsx frontend/src/index.css frontend/src/api.js frontend/src/App.routing.test.jsx
git commit -m "feat(shell): wire AppShell into App.jsx, redirect /overview, retire old Sidebar/Overview"
```

---

### Task 7: Phase verification and browser-matrix QA

**Files:** none (verification only).

- [ ] **Step 1: Run the full frontend test suite (local edition)**

Run: `cd frontend && npm test`
Expected: PASS, no regressions.

- [ ] **Step 2: Run the full frontend test suite (cloud edition)**

Run: `cd frontend && npm run test:cloud`
Expected: PASS — confirms `AppShell`/`navigation.js` work identically when `EDITION_NAVIGATION` is the cloud manifest (`/pricing` → System group per `DEFAULT_EDITION_GROUP`).

- [ ] **Step 3: Run both production builds**

Run: `cd frontend && npm run build && npm run build:cloud`
Expected: both PASS (the existing large-chunk warning from the spec's recorded baseline is expected and not a failure).

- [ ] **Step 4: Manual browser-matrix QA against the worktree dev server**

Start the worktree backend/frontend per spec §12.3 (`VITE_API_PROXY_TARGET` + a non-5173 port if the main checkout's `:5173` is already running a different branch). At each of 390×844, 768×1024, 1024×768, 1440×900:

- Sidebar is visible and the mobile top bar/drawer are absent at 1024×768 and 1440×900 (`lg` and above).
- Top bar + hamburger are visible and the sidebar is absent at 390×844 and 768×1024 (below `lg`).
- Opening the drawer traps Tab/Shift+Tab within it, Escape closes it, focus returns to the hamburger button, and background scroll is locked while it's open.
- The skip link is invisible until focused (Tab from the top of the page), then visibly jumps focus to `#main-content` on activation.
- Navigating between two pages moves focus to the new page's `<h1>` (verify via a screen reader or the browser's accessibility inspector — focus ring should land on the heading).
- `/overview` redirects to Dashboard; no page produces viewport-level horizontal scrolling at any of the four widths.
- A full keyboard-only walkthrough (Tab/Shift+Tab/Enter/Escape only, no mouse) can reach every primary nav destination and open/close the mobile drawer.

- [ ] **Step 5: Record results and finish**

Note the four verification commands' exit codes and the manual QA outcome in the pull request description. No commit needed for this task (verification only) unless QA surfaces a fix, in which case address it as a small follow-up commit before opening the PR.
