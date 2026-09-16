import { Loader2, Monitor, Moon, Sun } from "lucide-react";

import { useCurrency, usePalette } from "../../App";
import SegmentedControl from "../ui/SegmentedControl";

const PALETTE_OPTIONS = [
  { key: "blue", label: "Arctic Blue", color: "#2563EB" },
  { key: "green", label: "Mint Green", color: "#059669" },
  { key: "purple", label: "Soft Iris", color: "#7C3AED" },
];

export default function PreferencesSettings({ headingRef }) {
  const { currency, setCurrency, rate, rateLoading } = useCurrency();
  const { palette, setPalette, theme, setTheme, themeStyle, setThemeStyle } = usePalette();
  const premium = themeStyle === "neu";
  const czkUnavailable = !rateLoading && rate === null;

  return (
    <section aria-labelledby="settings-preferences-heading" className="space-y-6">
      <div>
        <h2 id="settings-preferences-heading" ref={headingRef} tabIndex={-1} className="text-xl font-semibold outline-none">Preferences</h2>
        <p className="mt-1 text-sm text-muted">Choose how Portfyl looks and displays portfolio values on this device.</p>
      </div>

      <div className="rounded-xl border border-surface-border bg-surface-card p-6 space-y-6">
        <div>
          <h3 className="mb-2 text-sm font-semibold">Theme style</h3>
          <SegmentedControl
            aria-label="Theme style"
            block
            value={themeStyle}
            onChange={setThemeStyle}
            options={[
              { value: "glass", label: "Classic", title: "Classic glass theme" },
              { value: "neu", label: "Premium", title: "Warm glass-hybrid theme" },
            ]}
          />
        </div>

        <div className={premium ? "opacity-50" : ""}>
          <h3 className="mb-2 text-sm font-semibold">Appearance</h3>
          <SegmentedControl
            aria-label="Appearance"
            block
            value={theme}
            onChange={setTheme}
            options={[
              { value: "light", label: <><Sun size={14} aria-hidden="true" /> <span>Light</span></>, title: "Light", disabled: premium },
              { value: "dark", label: <><Moon size={14} aria-hidden="true" /> <span>Dark</span></>, title: "Dark", disabled: premium },
              { value: "system", label: <><Monitor size={14} aria-hidden="true" /> <span>System</span></>, title: "System", disabled: premium },
            ]}
          />
          {premium && <p className="mt-2 text-xs text-muted">Premium uses its own fixed light appearance.</p>}
        </div>

        <div className={premium ? "opacity-50" : ""}>
          <h3 className="mb-2 text-sm font-semibold">Accent palette</h3>
          <div className="flex flex-wrap gap-2">
            {PALETTE_OPTIONS.map(({ key, label, color }) => (
              <button
                key={key}
                type="button"
                aria-label={`Theme: ${label}`}
                aria-pressed={palette === key}
                disabled={premium}
                onClick={() => setPalette(key)}
                className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm disabled:cursor-not-allowed ${
                  palette === key ? "border-brand text-ink" : "border-surface-border text-muted"
                }`}
              >
                <span aria-hidden="true" className="h-4 w-4 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold">Display currency</h3>
          <SegmentedControl
            aria-label="Display currency"
            value={currency}
            onChange={setCurrency}
            options={[
              { value: "USD", label: "USD", title: "Display currency: USD" },
              { value: "CZK", label: rateLoading ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : "CZK", title: czkUnavailable ? "Rate unavailable" : "Display currency: CZK", disabled: czkUnavailable },
            ]}
          />
          {currency === "CZK" && rate != null && <p className="mt-2 text-xs text-muted tabular-nums">1 USD = {rate.toFixed(2)} Kc</p>}
          {czkUnavailable && <p className="mt-2 text-xs text-loss">CZK rate unavailable. USD remains available.</p>}
        </div>
      </div>
    </section>
  );
}

