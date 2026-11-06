import { Link } from "react-router-dom";
import { Loader2, Monitor, Moon, PlayCircle, Sun } from "lucide-react";

import { EditionViewModeSetting } from "@edition-manifest";
import { useCurrency, usePalette } from "../../App";
import SegmentedControl from "../ui/SegmentedControl";
import BottomNavSetting from "./BottomNavSetting";
import { ONBOARDING_PREVIEW_PATH } from "../../lib/routes";

const PALETTE_OPTIONS = [
  { key: "blue", label: "Arctic Blue", color: "#2563EB" },
  { key: "green", label: "Mint Green", color: "#059669" },
  { key: "purple", label: "Soft Iris", color: "#7C3AED" },
];

export default function PreferencesSettings({ headingRef }) {
  const { currency, setCurrency, rate, rateLoading } = useCurrency();
  const { palette, setPalette, theme, setTheme, themeStyle, setThemeStyle } = usePalette();
  // Premium has one fixed light look, so Appearance and Accent palette stay
  // visible but disabled. Clay has its own palette, so they are not shown.
  const clay = themeStyle === "clay";
  const fixedLook = themeStyle === "neu";
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
              { value: "clay", label: "Clay", title: "Soft clay theme" },
            ]}
          />
        </div>

        {clay ? (
          <p className="text-sm text-muted">Clay uses its own light palette.</p>
        ) : (
          <>
          <div className={fixedLook ? "opacity-50" : ""}>
            <h3 className="mb-2 text-sm font-semibold">Appearance</h3>
            <SegmentedControl
              aria-label="Appearance"
              block
              value={theme}
              onChange={setTheme}
              options={[
                { value: "light", label: <><Sun size={14} aria-hidden="true" /> <span>Light</span></>, title: "Light", disabled: fixedLook },
                { value: "dark", label: <><Moon size={14} aria-hidden="true" /> <span>Dark</span></>, title: "Dark", disabled: fixedLook },
                { value: "system", label: <><Monitor size={14} aria-hidden="true" /> <span>System</span></>, title: "System", disabled: fixedLook },
              ]}
            />
            {fixedLook && <p className="mt-2 text-xs text-muted">Premium uses its own fixed light appearance.</p>}
          </div>

          <div className={fixedLook ? "opacity-50" : ""}>
            <h3 className="mb-2 text-sm font-semibold">Accent palette</h3>
            <div className="flex flex-wrap gap-2">
              {PALETTE_OPTIONS.map(({ key, label, color }) => (
                <button
                  key={key}
                  type="button"
                  aria-label={`Theme: ${label}`}
                  aria-pressed={palette === key}
                  disabled={fixedLook}
                  onClick={() => setPalette(key)}
                  className={`flex items-center gap-2 rounded-full border px-4 py-2 min-h-11 md:min-h-0 text-sm disabled:cursor-not-allowed ${
                    palette === key ? "border-brand text-ink" : "border-surface-border text-muted"
                  }`}
                >
                  <span aria-hidden="true" className="h-4 w-4 rounded-full" style={{ backgroundColor: color }} />
                  {label}
                </button>
              ))}
            </div>
          </div>
          </>
        )}

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

        <BottomNavSetting />

        <EditionViewModeSetting />
      </div>

      <div className="rounded-xl border border-surface-border bg-surface-card p-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold">Welcome tour</h3>
          <p className="mt-0.5 text-sm text-muted">Replay the first-run onboarding. It is a preview only: no portfolio is created and nothing is saved.</p>
        </div>
        <Link
          to={ONBOARDING_PREVIEW_PATH}
          className="btn-ghost inline-flex shrink-0 items-center justify-center gap-1.5 self-start min-h-11 md:min-h-0 text-sm font-medium sm:self-auto"
        >
          <PlayCircle size={14} aria-hidden="true" />
          Replay onboarding
        </Link>
      </div>
    </section>
  );
}
