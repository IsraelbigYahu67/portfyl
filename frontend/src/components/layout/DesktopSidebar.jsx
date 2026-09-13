import { Loader2, Monitor, Moon, Sun } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useCurrency, usePalette } from "../../App";
import AccountMenu from "../AccountMenu";
import PortfolioSwitcher from "../PortfolioSwitcher";
import SegmentedControl from "../ui/SegmentedControl";

const PALETTE_OPTIONS = [
  { key: "blue", label: "Arctic Blue" },
  { key: "green", label: "Mint Green" },
  { key: "purple", label: "Soft Iris" },
];

const PALETTE_COLORS = {
  blue: "#2563EB",
  green: "#059669",
  purple: "#7C3AED",
};

export default function DesktopSidebar({ groups }) {
  const { currency, setCurrency, rate, rateLoading } = useCurrency();
  const { palette, setPalette, theme, setTheme, themeStyle, setThemeStyle } = usePalette();
  const czkUnavailable = !rateLoading && rate === null;

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
        {groups.map((group) => {
          const headingId = `desktop-nav-${group.id}`;
          return (
            <section key={group.id} aria-labelledby={headingId}>
              <h2 id={headingId} className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                {group.label}
              </h2>
              <div className="space-y-0.5">
                {group.items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === "/"}
                    className={({ isActive }) => (
                      `flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-all ${
                        isActive
                          ? "font-semibold text-brand bg-[var(--sidebar-active)] shadow-[inset_0_0_0_1px_var(--glass-border-alpha)]"
                          : "text-muted hover:text-ink hover:bg-surface-hover"
                      }`
                    )}
                  >
                    <Icon size={16} aria-hidden="true" />
                    {label}
                  </NavLink>
                ))}
              </div>
            </section>
          );
        })}
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
                style={{ backgroundColor: PALETTE_COLORS[key] }}
              />
            ))}
          </div>
        </div>

        <div className="px-4 space-y-2">
          <p className="text-[10px] text-muted pl-0.5">Display currency</p>
          <div className="flex items-center gap-0.5 bg-surface-hover rounded-lg p-0.5">
            {["USD", "CZK"].map((currencyCode) => (
              <button
                key={currencyCode}
                onClick={() => setCurrency(currencyCode)}
                disabled={currencyCode === "CZK" && czkUnavailable}
                title={currencyCode === "CZK" && czkUnavailable ? "Rate unavailable" : undefined}
                aria-label={`Display currency: ${currencyCode}`}
                aria-pressed={currency === currencyCode}
                className={`flex-1 text-xs py-1.5 rounded-md font-semibold transition-colors ${
                  currency === currencyCode
                    ? "bg-brand text-white"
                    : czkUnavailable && currencyCode === "CZK"
                      ? "text-muted cursor-not-allowed"
                      : "text-muted hover:text-ink"
                }`}
              >
                {currencyCode === "CZK" && rateLoading
                  ? <Loader2 size={11} className="animate-spin mx-auto" aria-hidden="true" />
                  : currencyCode}
              </button>
            ))}
          </div>
          {currency === "CZK" && rate && (
            <p className="text-[10px] text-muted text-center tabular-nums">1 USD = {rate.toFixed(2)} Kc</p>
          )}
          {czkUnavailable && <p className="text-[10px] text-loss text-center">Rate unavailable</p>}
        </div>

        <div className="px-5 text-[11px] text-muted" style={{ opacity: 0.7 }}>
          Live data via Yahoo Finance
        </div>
      </div>
    </aside>
  );
}
