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
  green: {
    brand: "#059669", brandHover: "#047857", brandLight: "#D1FAE5", brandLightDark: "#064E3B",
    bg: "#F6F8F7", bgSubtle: "#F0FDF4", sidebarActive: "#ECFDF5",
  },
  blue: {
    brand: "#2563EB", brandHover: "#1D4ED8", brandLight: "#DBEAFE", brandLightDark: "#1E3A8A",
    bg: "#F5F7FA", bgSubtle: "#F1F5F9", sidebarActive: "#EFF6FF",
  },
  purple: {
    brand: "#7C3AED", brandHover: "#6D28D9", brandLight: "#EDE9FE", brandLightDark: "#4C1D95",
    bg: "#F7F6FB", bgSubtle: "#F5F3FF", sidebarActive: "#F5F3FF",
  },
};

// Neutral dark surfaces shared across all hues (the brand stays vivid in dark mode).
// bgSubtle sits a step above the card so hover states / progress tracks stay visible.
const DARK_SURFACES = {
  bg: "#0F172A", bgSubtle: "#334155", surfaceCard: "#1E293B", border: "#334155",
  ink: "#E2E8F0", muted: "#94A3B8", hairline: "#334155",
};
const LIGHT_TOKENS = {
  surfaceCard: "#FFFFFF", border: "#E6EAF0",
  ink: "#0B1220", muted: "#64748B", hairline: "#E6EAF0",
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
  s.setProperty("--border", t.border);
  s.setProperty("--ink", t.ink);
  s.setProperty("--muted", t.muted);
  s.setProperty("--hairline", t.hairline);
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
  const [currency, setCurrencyState] = useState(
    () => localStorage.getItem("sb_currency") || "USD"
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
