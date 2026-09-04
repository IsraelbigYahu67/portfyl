import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Routes, Route, Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import Sidebar from "./components/Sidebar";
import PlatformLanding from "./pages/PlatformLanding";
import Dashboard from "./pages/Dashboard";
import Overview from "./pages/Overview";
import Allocation from "./pages/Allocation";
import Transactions from "./pages/Transactions";
import Cash from "./pages/Cash";
import Import from "./pages/Import";
import Dividends from "./pages/Dividends";
import Analytics from "./pages/Analytics";
import Settings from "./pages/Settings";
import Assistant from "./pages/Assistant";
import Search from "./pages/Search";
import Stock from "./pages/Stock";
import Watchlists from "./pages/Watchlists";
import Login from "./pages/Login";
import Register from "./pages/Register";
import VerifyEmail from "./pages/VerifyEmail";
import ForgotPassword from "./pages/ForgotPassword";
import { fetchCapabilities, fetchFxRate, fetchPortfolios, setActivePortfolioId, getActivePortfolioId } from "./api";
import { ToastProvider } from "./components/ui/Toast";
import { ConfirmProvider } from "./components/ui/ConfirmDialog";
import AutoLoad from "./components/AutoLoad";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { EDITION_ROUTES, EditionShell } from "@edition-manifest";
import { enabledEditionEntries } from "./editions/filter";

const CurrencyContext = createContext(null);
const PortfolioContext = createContext(null);
const PaletteContext = createContext(null);
const PlatformContext = createContext(null);

const PALETTES = {
  blue: {
    brand: "#3B82F6", brandHover: "#2563EB", brandLight: "#DBEAFE", brandLightDark: "#1E3A5F",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(59,130,246,0.16)",
  },
  green: {
    brand: "#34D399", brandHover: "#10B981", brandLight: "#D1FAE5", brandLightDark: "#0F3D30",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(52,211,153,0.16)",
  },
  purple: {
    brand: "#A78BFA", brandHover: "#8B5CF6", brandLight: "#EDE9FE", brandLightDark: "#2E2555",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(167,139,250,0.16)",
  },
};

// Neutral dark surfaces shared across all hues (the brand stays vivid in dark mode).
// bgSubtle sits a step above the card so hover states / progress tracks stay visible.
const DARK_SURFACES = {
  bg: "#020617", bgSubtle: "#0B1326", surfaceCard: "#131B2E", surfaceCardElevated: "#1F2435",
  border: "#2A3245", ink: "#DAE2FD", muted: "#8A93B3", hairline: "#2A3245",
};
const LIGHT_TOKENS = {
  surfaceCard: "#FFFFFF", surfaceCardElevated: "#F7F9FD", border: "#DDE3F0",
  ink: "#10162B", muted: "#6B7592", hairline: "#DDE3F0",
};

// "Premium" — warm glassmorphism/neumorphism hybrid: soft dual shadows (the
// neumorphic half) layered on translucent, blurred surfaces (the glass half)
// over a warm mesh-gradient background (.theme-premium body in index.css).
// One fixed light appearance — ignores Light/Dark/System entirely, same as
// the historical Neumorphism style this replaces.
// See docs/superpowers/specs/2026-08-30-portfyl-premium-redesign-design.md.
export const NEU_TOKENS = {
  bg: "#F3E8DA", bgSubtle: "#ECE0CF",
  surfaceCard: "rgba(250,245,237,0.78)", surfaceCardElevated: "rgba(253,249,243,0.92)",
  border: "rgba(120,105,84,0.14)", hairline: "rgba(120,105,84,0.14)",
  ink: "#3A352C", muted: "#6B6353",
  brand: "#6D7048", brandHover: "#5C5F3C", brandLight: "#E4E5D3",
  gain: "#5B7A4C", loss: "#B8543A",
  glassBorderAlpha: "rgba(120,105,84,0.16)", glassOverlayAlpha: "rgba(255,252,247,0.55)",
  blurCard: "14px", blurOverlay: "22px",
  shadowAmbient: "7px 7px 18px rgba(190,172,146,0.5), -7px -7px 18px rgba(255,253,248,0.9)",
  shadowInset: "inset 3px 3px 8px rgba(190,172,146,0.45), inset -3px -3px 8px rgba(255,253,248,0.85)",
  radiusCard: "1.25rem",
  chart: ["#A9AB88", "#DBAA89", "#D4C3A1", "#B7AFA3", "#7C8A5A", "#C08457", "#9E8E6E", "#8A8478"],
};
// Classic's chart series previously lived only in index.css's :root block
// (--chart-1..8); pulled into this constant so applyAppearance() can reset
// them inline the same way both branches reset every other token, since an
// inline style always outranks a :root declaration.
const GLASS_CHART = ["var(--brand)", "#4EDEA3", "#FFB95F", "#A78BFA", "#38BDF8", "#FB7185", "#FACC15", "#64748B"];

export function usePalette() {
  return useContext(PaletteContext);
}

export function usePlatform() {
  return useContext(PlatformContext);
}

export function resolveDark(theme) {
  if (theme === "dark") return true;
  if (theme === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyAppearance(name, isDark, themeStyle) {
  const s = document.documentElement.style;

  if (themeStyle === "neu") {
    s.setProperty("--brand", NEU_TOKENS.brand);
    s.setProperty("--brand-hover", NEU_TOKENS.brandHover);
    s.setProperty("--brand-light", NEU_TOKENS.brandLight);
    s.setProperty("--bg", NEU_TOKENS.bg);
    s.setProperty("--bg-subtle", NEU_TOKENS.bgSubtle);
    s.setProperty("--sidebar-active", NEU_TOKENS.brandLight);
    s.setProperty("--surface-card", NEU_TOKENS.surfaceCard);
    s.setProperty("--surface-card-elevated", NEU_TOKENS.surfaceCardElevated);
    s.setProperty("--border", NEU_TOKENS.border);
    s.setProperty("--hairline", NEU_TOKENS.hairline);
    s.setProperty("--ink", NEU_TOKENS.ink);
    s.setProperty("--muted", NEU_TOKENS.muted);
    s.setProperty("--gain", NEU_TOKENS.gain);
    s.setProperty("--loss", NEU_TOKENS.loss);
    s.setProperty("--glass-border-alpha", NEU_TOKENS.glassBorderAlpha);
    s.setProperty("--glass-overlay-alpha", NEU_TOKENS.glassOverlayAlpha);
    s.setProperty("--blur-card", NEU_TOKENS.blurCard);
    s.setProperty("--blur-overlay", NEU_TOKENS.blurOverlay);
    s.setProperty("--shadow-ambient", NEU_TOKENS.shadowAmbient);
    s.setProperty("--shadow-inset", NEU_TOKENS.shadowInset);
    s.setProperty("--radius-card", NEU_TOKENS.radiusCard);
    NEU_TOKENS.chart.forEach((color, i) => s.setProperty(`--chart-${i + 1}`, color));
    document.documentElement.classList.toggle("dark", false);
    document.documentElement.classList.toggle("theme-premium", true);
    return;
  }

  document.documentElement.classList.toggle("theme-premium", false);
  const p = PALETTES[name] || PALETTES.green;
  s.setProperty("--brand", p.brand);
  s.setProperty("--brand-hover", p.brandHover);
  s.setProperty("--brand-light", isDark ? p.brandLightDark : p.brandLight);
  const t = isDark ? DARK_SURFACES : LIGHT_TOKENS;
  s.setProperty("--surface-card", t.surfaceCard);
  s.setProperty("--surface-card-elevated", isDark ? DARK_SURFACES.surfaceCardElevated : LIGHT_TOKENS.surfaceCardElevated);
  s.setProperty("--border", t.border);
  s.setProperty("--ink", t.ink);
  s.setProperty("--muted", t.muted);
  s.setProperty("--hairline", t.hairline);
  s.setProperty("--glass-border-alpha", isDark ? "rgba(255,255,255,0.06)" : "rgba(16,22,43,0.06)");
  s.setProperty("--glass-overlay-alpha", isDark ? "rgba(255,255,255,0.03)" : "rgba(255,255,255,0.5)");
  s.setProperty("--blur-card", "12px");
  s.setProperty("--blur-overlay", "20px");
  s.setProperty("--shadow-ambient", isDark ? "0px 4px 20px rgba(0,0,0,0.5)" : "0px 4px 20px rgba(16,22,43,0.10)");
  s.setProperty("--shadow-inset", "none");
  s.setProperty("--radius-card", "0.5rem");
  s.setProperty("--gain", isDark ? "#34D399" : "#10B981");
  s.setProperty("--loss", isDark ? "#F87171" : "#EF4444");
  GLASS_CHART.forEach((color, i) => s.setProperty(`--chart-${i + 1}`, color));
  if (isDark) {
    s.setProperty("--bg", DARK_SURFACES.bg);
    s.setProperty("--bg-subtle", DARK_SURFACES.bgSubtle);
    s.setProperty("--sidebar-active", p.sidebarActive);
  } else {
    s.setProperty("--bg", p.bg);
    s.setProperty("--bg-subtle", p.bgSubtle);
    s.setProperty("--sidebar-active", p.brandLight);
  }
  document.documentElement.classList.toggle("dark", isDark);
}

export function useCurrency() {
  return useContext(CurrencyContext);
}

export function usePortfolio() {
  return useContext(PortfolioContext);
}

function CurrencyProvider({ children }) {
  // CZK default: the broker account settles in CZK, so the headline numbers are
  // directly comparable to Trading 212. USD stays available in the switcher.
  const [currency, setCurrencyState] = useState(
    () => localStorage.getItem("sb_currency") || "CZK"
  );

  const setCurrency = (c) => {
    localStorage.setItem("sb_currency", c);
    setCurrencyState(c);
  };

  const { data: fxData, isLoading: rateLoading } = useQuery({
    queryKey: ["fx", "USDCZK"],
    queryFn: () => fetchFxRate("USDCZK"),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const rate = fxData?.rate ?? null;

  return (
    <CurrencyContext.Provider value={{ currency, setCurrency, rate, rateLoading }}>
      {children}
    </CurrencyContext.Provider>
  );
}

// Portfolio ids are UUID strings end-to-end (backend Tasks 5-8). A pre-migration
// install may still have a plain numeric id cached under this key; it can never
// match a server portfolio under the new scheme, so it's dropped on sight below
// rather than sent as a doomed portfolio_id on the very first request.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function PortfolioProvider({ children }) {
  const queryClient = useQueryClient();

  // Hydrate the axios interceptor synchronously from localStorage so the very first
  // API requests (issued on mount before /portfolios resolves) still carry an id.
  // We may overwrite this once the server confirms the portfolio exists.
  const [currentId, setCurrentIdState] = useState(() => {
    const stored = localStorage.getItem("sb_portfolio_id");
    if (stored && UUID_RE.test(stored)) {
      setActivePortfolioId(stored);
      return stored;
    }
    if (stored) {
      localStorage.removeItem("sb_portfolio_id");
    }
    return null;
  });

  const { data: portfolios = [], isLoading, refetch } = useQuery({
    queryKey: ["portfolios"],
    queryFn: fetchPortfolios,
    staleTime: 60_000,
  });

  // Once we know the server-side list, validate the stored id and fall back to the
  // default portfolio if it's gone (e.g. deleted on the server).
  useEffect(() => {
    if (!portfolios.length) return;
    const exists = currentId != null && portfolios.some((p) => p.id === currentId);
    if (exists) {
      setActivePortfolioId(currentId);
      return;
    }
    const fallback = portfolios.find((p) => p.is_default) || portfolios[0];
    if (fallback) {
      setActivePortfolioId(fallback.id);
      setCurrentIdState(fallback.id);
      localStorage.setItem("sb_portfolio_id", String(fallback.id));
    }
  }, [portfolios, currentId]);

  const setCurrentId = useCallback(
    (id) => {
      const next = id == null ? null : String(id);
      if (next == null || next === currentId) return;
      // Drop ALL cached data before switching so no other portfolio's holdings,
      // transactions, T212 status, etc. can briefly flash on screen.
      queryClient.removeQueries();
      setActivePortfolioId(next);
      setCurrentIdState(next);
      localStorage.setItem("sb_portfolio_id", next);
      // Re-fetch the portfolios list immediately so the picker reflects fresh counts.
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
    },
    [currentId, queryClient]
  );

  const value = {
    portfolios,
    currentId,
    current: portfolios.find((p) => p.id === currentId) || null,
    setCurrentId,
    refetchPortfolios: refetch,
    isLoading,
    ready: currentId != null && getActivePortfolioId() === currentId,
  };

  return <PortfolioContext.Provider value={value}>{children}</PortfolioContext.Provider>;
}

function PaletteProvider({ children }) {
  const [palette, setPaletteState] = useState(
    () => localStorage.getItem("sb_palette") || "green"
  );
  const [theme, setThemeState] = useState(
    () => localStorage.getItem("sb_theme") || "system"
  );
  // Premium (the warm glass-hybrid look) is the default; Classic glass stays
  // available in the switcher. This is the style's first release in this
  // repo, so no installs have sb_theme_style set yet -- no migration needed.
  const [themeStyle, setThemeStyleState] = useState(
    () => localStorage.getItem("sb_theme_style") || "neu"
  );

  const setPalette = (p) => {
    localStorage.setItem("sb_palette", p);
    setPaletteState(p);
  };

  const setTheme = (t) => {
    localStorage.setItem("sb_theme", t);
    setThemeState(t);
  };

  const setThemeStyle = (style) => {
    localStorage.setItem("sb_theme_style", style);
    setThemeStyleState(style);
  };

  useEffect(() => {
    const apply = () => applyAppearance(palette, resolveDark(theme), themeStyle);
    apply();
    // Follow OS changes only while on "system" AND on Classic glass --
    // Premium ignores Light/Dark/System entirely.
    if (theme === "system" && themeStyle === "glass") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
  }, [palette, theme, themeStyle]);

  return (
    <PaletteContext.Provider
      value={{ palette, setPalette, theme, setTheme, themeStyle, setThemeStyle, palettes: PALETTES }}
    >
      {children}
    </PaletteContext.Provider>
  );
}

function PlatformProvider({ children }) {
  const [platform, setPlatformState] = useState(
    () => localStorage.getItem("sb_platform") || null
  );

  const setPlatform = useCallback((p) => {
    if (p) {
      localStorage.setItem("sb_platform", p);
    } else {
      localStorage.removeItem("sb_platform");
    }
    setPlatformState(p);
  }, []);

  return (
    <PlatformContext.Provider value={{ platform, setPlatform }}>
      {children}
    </PlatformContext.Provider>
  );
}

export default function App() {
  return (
    // Appearance is a device-level preference, independent of auth state --
    // it stays above the auth gate so the login/register/etc. pages render
    // with the visitor's chosen theme instead of the light-mode fallback.
    <PaletteProvider>
      <AuthProvider>
        <AuthGate />
      </AuthProvider>
    </PaletteProvider>
  );
}

function AuthSplash() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg" role="status">
      <Loader2 className="animate-spin text-brand" size={28} aria-hidden="true" />
      <span className="sr-only">Loading your account…</span>
    </div>
  );
}

// Public auth routes are mounted outside every protected provider (portfolio,
// currency, toast, confirm, platform) -- none of that state exists yet for a
// visitor who hasn't authenticated. The full application only mounts once
// AuthProvider has resolved a session with both a user and a workspace.
function AuthGate() {
  const { ready, user, currentWorkspace } = useAuth();

  if (!ready) {
    return <AuthSplash />;
  }

  if (!user || !currentWorkspace) {
    return (
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    <PortfolioProvider>
      <CurrencyProvider>
        <ToastProvider>
          <ConfirmProvider>
            <PlatformProvider>
              <AppLayout />
            </PlatformProvider>
          </ConfirmProvider>
        </ToastProvider>
      </CurrencyProvider>
    </PortfolioProvider>
  );
}

function AppLayout() {
  const { platform } = usePlatform();
  const { data: capabilityState } = useQuery({
    queryKey: ["capabilities"],
    queryFn: fetchCapabilities,
    staleTime: Infinity,
    retry: false,
  });
  const runtimeCapabilities = capabilityState?.capabilities || [];
  const editionRoutes = enabledEditionEntries(EDITION_ROUTES, runtimeCapabilities);

  if (!platform) {
    return (
      <div className="flex min-h-screen">
        <EditionShell />
        <Sidebar capabilities={runtimeCapabilities} />
        <main className="flex-1 p-6 overflow-y-auto min-w-0 max-h-screen">
          <Routes>
            {editionRoutes.map(({ path, Component }) => (
              <Route key={path} path={path} element={<Component />} />
            ))}
            <Route path="*" element={<PlatformLanding />} />
          </Routes>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <EditionShell />
      {/* Background prefetcher — warms the React Query cache for every T212 page
          in priority order so navigation is instant. Renders nothing. */}
      {platform === "t212" && <AutoLoad />}
      <Sidebar capabilities={runtimeCapabilities} />
      <main className="flex-1 p-6 overflow-y-auto min-w-0 max-h-screen">
        <Routes>
          {platform === "t212" && (
            <>
              <Route path="/" element={<Dashboard />} />
              <Route path="/overview" element={<Overview />} />
              <Route path="/allocation" element={<Allocation />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/cash" element={<Cash />} />
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
            </>
          )}
          <Route path="/settings" element={<Settings />} />
          {/* An authenticated visitor landing on a public auth URL (stale tab,
              browser back button after login, etc.) gets sent home instead of
              a blank route. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
