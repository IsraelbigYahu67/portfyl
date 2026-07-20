import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import PlatformLanding from "./pages/PlatformLanding";
import Dashboard from "./pages/Dashboard";
import Allocation from "./pages/Allocation";
import Transactions from "./pages/Transactions";
import Cash from "./pages/Cash";
import Options from "./pages/Options";
import Polymarket from "./pages/Polymarket";
import Import from "./pages/Import";
import Dividends from "./pages/Dividends";
import DividendCalendar from "./pages/DividendCalendar";
import Analytics from "./pages/Analytics";
import TaxReport from "./pages/TaxReport";
import Settings from "./pages/Settings";
import Assistant from "./pages/Assistant";
import Search from "./pages/Search";
import Stock from "./pages/Stock";
import Watchlists from "./pages/Watchlists";
import Screener from "./pages/Screener";
import { fetchFxRate, fetchPortfolios, setActivePortfolioId, getActivePortfolioId } from "./api";
import { ToastProvider } from "./components/ui/Toast";
import { ConfirmProvider } from "./components/ui/ConfirmDialog";
import AutoLoad from "./components/AutoLoad";

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

function applyAppearance(name, isDark) {
  const p = PALETTES[name] || PALETTES.green;
  const s = document.documentElement.style;
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
  s.setProperty("--shadow-ambient", isDark ? "0px 4px 20px rgba(0,0,0,0.5)" : "0px 4px 20px rgba(16,22,43,0.10)");
  s.setProperty("--gain", isDark ? "#34D399" : "#10B981");
  s.setProperty("--loss", isDark ? "#F87171" : "#EF4444");
  if (isDark) {
    s.setProperty("--bg", DARK_SURFACES.bg);
    s.setProperty("--bg-subtle", DARK_SURFACES.bgSubtle);
    s.setProperty("--sidebar-active", p.brandLightDark);
  } else {
    s.setProperty("--bg", p.bg);
    s.setProperty("--bg-subtle", p.bgSubtle);
    s.setProperty("--sidebar-active", p.sidebarActive);
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

function PortfolioProvider({ children }) {
  const queryClient = useQueryClient();

  // Hydrate the axios interceptor synchronously from localStorage so the very first
  // API requests (issued on mount before /portfolios resolves) still carry an id.
  // We may overwrite this once the server confirms the portfolio exists.
  const [currentId, setCurrentIdState] = useState(() => {
    const stored = localStorage.getItem("sb_portfolio_id");
    const parsed = stored ? Number(stored) : null;
    if (parsed && !Number.isNaN(parsed)) {
      setActivePortfolioId(parsed);
      return parsed;
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
      const next = Number(id);
      if (Number.isNaN(next) || next === currentId) return;
      // Drop ALL cached data before switching so no other portfolio's holdings,
      // transactions, T212 status, etc. can briefly flash on screen.
      queryClient.removeQueries();
      setActivePortfolioId(next);
      setCurrentIdState(next);
      localStorage.setItem("sb_portfolio_id", String(next));
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

  const setPalette = (p) => {
    localStorage.setItem("sb_palette", p);
    setPaletteState(p);
  };

  const setTheme = (t) => {
    localStorage.setItem("sb_theme", t);
    setThemeState(t);
  };

  useEffect(() => {
    const apply = () => applyAppearance(palette, resolveDark(theme));
    apply();
    // Follow OS changes only while on "system".
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
  }, [palette, theme]);

  return (
    <PaletteContext.Provider value={{ palette, setPalette, theme, setTheme, palettes: PALETTES }}>
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
    <PaletteProvider>
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
    </PaletteProvider>
  );
}

function AppLayout() {
  const { platform } = usePlatform();

  if (!platform) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 p-6 overflow-y-auto min-w-0 max-h-screen">
          <PlatformLanding />
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      {/* Background prefetcher — warms the React Query cache for every T212 page
          in priority order so navigation is instant. Renders nothing. */}
      {platform === "t212" && <AutoLoad />}
      <Sidebar />
      <main className="flex-1 p-6 overflow-y-auto min-w-0 max-h-screen">
        <Routes>
          {platform === "t212" && (
            <>
              <Route path="/" element={<Dashboard />} />
              <Route path="/allocation" element={<Allocation />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/cash" element={<Cash />} />
              <Route path="/import" element={<Import />} />
              <Route path="/dividends" element={<Dividends />} />
              <Route path="/dividend-calendar" element={<DividendCalendar />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/tax-report" element={<TaxReport />} />
              <Route path="/search" element={<Search />} />
              <Route path="/stock/:ticker" element={<Stock />} />
              <Route path="/watchlists" element={<Watchlists />} />
              <Route path="/screener" element={<Screener />} />
              <Route path="/assistant" element={<Assistant />} />
            </>
          )}
          {platform === "ibkr" && (
            <>
              <Route path="/" element={<Options />} />
              <Route path="/options" element={<Options />} />
            </>
          )}
          {platform === "polymarket" && (
            <>
              <Route path="/" element={<Polymarket />} />
            </>
          )}
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
