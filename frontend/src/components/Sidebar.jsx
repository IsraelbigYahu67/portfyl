import { NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, PieChart, ArrowLeftRight, Upload, Loader2, CalendarDays, Activity, FileText, Settings, Search, Star, Target, ArrowLeft, Hexagon, Bot, Sun, Moon, Monitor, Filter, Wallet, Layers } from "lucide-react";
import { useCurrency, usePalette, usePlatform } from "../App";
import PortfolioSwitcher from "./PortfolioSwitcher";
import SegmentedControl from "./ui/SegmentedControl";

const T212_LINKS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/overview", label: "Overview", icon: Layers },
  { to: "/allocation", label: "Allocation", icon: PieChart },
  { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/cash", label: "Cash", icon: Wallet },
  { to: "/search", label: "Search", icon: Search },
  { to: "/watchlists", label: "Watchlists", icon: Star },
  { to: "/import", label: "Import CSV", icon: Upload },
  { to: "/dividends", label: "Dividends", icon: CalendarDays },
  { to: "/analytics", label: "Analytics", icon: Activity },
  { to: "/tax-report", label: "Tax Report", icon: FileText },
  { to: "/screener", label: "Screener", icon: Filter },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/assistant", label: "AI Assistant", icon: Bot },
];

const IBKR_LINKS = [
  { to: "/", label: "Options", icon: Target },
  { to: "/settings", label: "Settings", icon: Settings },
];

const POLYMARKET_LINKS = [
  { to: "/", label: "Positions", icon: Hexagon },
  { to: "/settings", label: "Settings", icon: Settings },
];

const PALETTE_OPTIONS = [
  { key: "blue", label: "Arctic Blue" },
  { key: "green", label: "Mint Green" },
  { key: "purple", label: "Soft Iris" },
];

export default function Sidebar() {
  const { currency, setCurrency, rate, rateLoading } = useCurrency();
  const { palette, setPalette, theme, setTheme, themeStyle, setThemeStyle } = usePalette();
  const { platform, setPlatform } = usePlatform();
  const navigate = useNavigate();
  const czk_unavailable = !rateLoading && rate === null;

  const links = platform === "ibkr" ? IBKR_LINKS : platform === "t212" ? T212_LINKS : platform === "polymarket" ? POLYMARKET_LINKS : [];

  const platformLabel = platform === "t212" ? "Trading 212" : platform === "ibkr" ? "Interactive Brokers" : platform === "polymarket" ? "Polymarket" : null;

  return (
    <aside className="w-[232px] shrink-0 bg-surface-card border-r border-surface-border flex flex-col h-screen sticky top-0"
      style={{ boxShadow: "1px 0 0 var(--glass-border-alpha)" }}>
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

      {platform && (
        <div className="px-3 pt-2">
          <button
            onClick={() => { setPlatform(null); navigate("/"); }}
            className="w-full flex items-center gap-2 text-xs text-muted hover:text-brand px-2 py-1.5 rounded-lg hover:bg-surface-hover transition-colors"
          >
            <ArrowLeft size={12} />
            <span className="font-medium">{platformLabel}</span>
          </button>
        </div>
      )}

      <nav className="flex-1 px-2.5 py-2 space-y-0.5 overflow-y-auto">
        {links.map(({ to, label, icon: Icon }) => (
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
      </nav>

      <div className="mt-auto pb-3 space-y-3">
        {/* Theme style (Classic glass vs Premium warm glass-hybrid) */}
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

        {/* Appearance (light / dark / system) -- inert while Premium is
            active, which ships as one fixed light appearance. */}
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

        {/* Palette switcher -- same rationale as Appearance above. */}
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

        {/* Currency toggle */}
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
                {c === "CZK" && rateLoading ? (
                  <Loader2 size={11} className="animate-spin mx-auto" />
                ) : c}
              </button>
            ))}
          </div>
          {currency === "CZK" && rate && (
            <p className="text-[10px] text-muted text-center tabular-nums">
              1 USD = {rate.toFixed(2)} Kc
            </p>
          )}
          {czk_unavailable && (
            <p className="text-[10px] text-loss text-center">Rate unavailable</p>
          )}
        </div>

        <div className="px-5 text-[11px] text-muted" style={{ opacity: 0.7 }}>
          Live data via Yahoo Finance
        </div>
      </div>
    </aside>
  );
}
