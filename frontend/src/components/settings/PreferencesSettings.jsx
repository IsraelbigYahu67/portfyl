import { useId } from "react";
import { Link } from "react-router-dom";
import { Loader2, Monitor, Moon, PlayCircle, Sun } from "lucide-react";

import { EditionViewModeSetting } from "@edition-manifest";
import { useCurrency, usePalette } from "../../App";
import SegmentedControl from "../ui/SegmentedControl";
import Select from "../ui/Select";
import BottomNavSetting from "./BottomNavSetting";
import { ONBOARDING_PREVIEW_PATH } from "../../lib/routes";
import { useI18n } from "../../i18n/I18nProvider";
import { APP_LANGUAGES } from "../../i18n/languages";
import { DISPLAY_CURRENCIES, currencySymbol } from "../../lib/displayCurrency";

// Palette names are product names, so they are not translated.
const PALETTE_OPTIONS = [
  { key: "blue", label: "Arctic Blue", color: "#2563EB" },
  { key: "green", label: "Mint Green", color: "#059669" },
  { key: "purple", label: "Soft Iris", color: "#7C3AED" },
];

function LanguageSetting() {
  const { language, setLanguage, t } = useI18n();
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-semibold">{t("Language")}</label>
      <Select
        id={id}
        className="max-w-xs min-h-11 md:min-h-0 text-base md:text-sm"
        value={language}
        onChange={setLanguage}
        options={APP_LANGUAGES.map(({ code, name }) => ({ value: code, label: name, lang: code }))}
      />
    </div>
  );
}

export default function PreferencesSettings({ headingRef }) {
  const { t } = useI18n();
  const { currency, setCurrency, rate, rateLoading } = useCurrency();
  const { palette, setPalette, theme, setTheme, themeStyle, setThemeStyle } = usePalette();
  // Premium has one fixed light look, so Appearance and Accent palette stay
  // visible but disabled. Clay has its own palette, so they are not shown.
  const clay = themeStyle === "clay";
  const fixedLook = themeStyle === "neu";
  const rateUnavailable = currency !== "USD" && !rateLoading && rate === null;

  return (
    <section aria-labelledby="settings-preferences-heading" className="space-y-6">
      <div>
        <h2 id="settings-preferences-heading" ref={headingRef} tabIndex={-1} className="text-xl font-semibold outline-none">{t("Preferences")}</h2>
        <p className="mt-1 text-sm text-muted">{t("Choose the language, look and currency Portfyl uses on this device.")}</p>
      </div>

      <div className="rounded-xl border border-surface-border bg-surface-card p-6 space-y-6">
        <LanguageSetting />

        <div>
          <h3 className="mb-2 text-sm font-semibold">{t("Theme style")}</h3>
          <SegmentedControl
            aria-label={t("Theme style")}
            block
            value={themeStyle}
            onChange={setThemeStyle}
            options={[
              { value: "glass", label: "Classic", title: t("Classic glass theme") },
              { value: "neu", label: "Premium", title: t("Warm glass-hybrid theme") },
              { value: "clay", label: "Clay", title: t("Soft clay theme") },
            ]}
          />
        </div>

        {clay ? (
          <p className="text-sm text-muted">{t("Clay uses its own light palette.")}</p>
        ) : (
          <>
          <div className={fixedLook ? "opacity-50" : ""}>
            <h3 className="mb-2 text-sm font-semibold">{t("Appearance")}</h3>
            <SegmentedControl
              aria-label={t("Appearance")}
              block
              value={theme}
              onChange={setTheme}
              options={[
                { value: "light", label: <><Sun size={14} aria-hidden="true" /> <span>{t("Light")}</span></>, title: t("Light"), disabled: fixedLook },
                { value: "dark", label: <><Moon size={14} aria-hidden="true" /> <span>{t("Dark")}</span></>, title: t("Dark"), disabled: fixedLook },
                { value: "system", label: <><Monitor size={14} aria-hidden="true" /> <span>{t("System")}</span></>, title: t("System"), disabled: fixedLook },
              ]}
            />
            {fixedLook && <p className="mt-2 text-xs text-muted">{t("Premium uses its own fixed light appearance.")}</p>}
          </div>

          <div className={fixedLook ? "opacity-50" : ""}>
            <h3 className="mb-2 text-sm font-semibold">{t("Accent palette")}</h3>
            <div className="flex flex-wrap gap-2">
              {PALETTE_OPTIONS.map(({ key, label, color }) => (
                <button
                  key={key}
                  type="button"
                  aria-label={t("Theme: {name}", { name: label })}
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
          <h3 className="mb-2 text-sm font-semibold">{t("Display currency")}</h3>
          <SegmentedControl
            aria-label={t("Display currency")}
            value={currency}
            onChange={setCurrency}
            options={DISPLAY_CURRENCIES.map((code) => ({
              value: code,
              label: rateLoading && currency === code ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : code,
              title: t("Display currency: {currency}", { currency: code }),
            }))}
          />
          {currency !== "USD" && rate != null && <p className="mt-2 text-xs text-muted tabular-nums">1 USD = {rate.toFixed(2)} {currencySymbol(currency)}</p>}
          {rateUnavailable && <p className="mt-2 text-xs text-loss">{t("The {currency} rate is unavailable right now, so some amounts stay in USD.", { currency })}</p>}
        </div>

        <BottomNavSetting />

        <EditionViewModeSetting />
      </div>

      <div className="rounded-xl border border-surface-border bg-surface-card p-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t("Welcome tour")}</h3>
          <p className="mt-0.5 text-sm text-muted">{t("Replay the first-run onboarding. It is a preview only: no portfolio is created.")}</p>
        </div>
        <Link
          to={ONBOARDING_PREVIEW_PATH}
          className="btn-ghost inline-flex shrink-0 items-center justify-center gap-1.5 self-start min-h-11 md:min-h-0 text-sm font-medium sm:self-auto"
        >
          <PlayCircle size={14} aria-hidden="true" />
          {t("Replay onboarding")}
        </Link>
      </div>
    </section>
  );
}
