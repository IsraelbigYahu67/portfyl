import { useId, useRef, useState } from "react";
import { ChevronDown, Globe } from "lucide-react";

import Select from "../ui/Select";
import { useI18n } from "../../i18n/I18nProvider";
import { APP_LANGUAGES } from "../../i18n/languages";
import { confirmPreferences } from "../../lib/preferencesConfirmation";
import { DISPLAY_CURRENCIES, currencySymbol, localCurrencyForLanguage } from "../../lib/displayCurrency";

// The app language and display currency during first-run onboarding. Both are
// already guessed (browser language, local currency), so this is a quiet chip
// ("Čeština · CZK") that expands to change them or to confirm with "Looks
// good". It never blocks the flow: nothing has to be clicked to continue.
const LANGUAGE_OPTIONS = APP_LANGUAGES.map(({ code, name }) => ({ value: code, label: name, lang: code }));

export default function PreferencesChip({ currency, onCurrencyChange }) {
  const { language, setLanguage, t } = useI18n();
  const [open, setOpen] = useState(false);
  const chipRef = useRef(null);
  const panelId = useId();
  const languageId = useId();
  const currencyId = useId();

  const languageName = APP_LANGUAGES.find(({ code }) => code === language)?.name ?? language;
  const currencyOptions = DISPLAY_CURRENCIES.map((code) => ({
    value: code,
    label: `${currencySymbol(code)} · ${code}`,
  }));

  // Picking a language also preselects its local currency, as the old
  // language step did; the currency can still be changed on its own.
  const pickLanguage = (code) => {
    setLanguage(code);
    onCurrencyChange(localCurrencyForLanguage(code));
  };
  // Closing unmounts the focused control, so focus goes back to the chip.
  const close = () => {
    setOpen(false);
    chipRef.current?.focus({ preventScroll: true });
  };
  const confirm = () => {
    confirmPreferences();
    close();
  };

  return (
    <div className="relative">
      <button
        ref={chipRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        className="btn-ghost inline-flex min-h-[44px] items-center gap-2 text-sm font-medium"
      >
        <Globe size={16} aria-hidden="true" />
        <span lang={language}>{languageName} · {currency}</span>
        <ChevronDown size={16} aria-hidden="true" className={open ? "rotate-180" : ""} />
      </button>

      {open && (
        <div
          id={panelId}
          // An open Select menu handles (and stops) its own Escape first.
          onKeyDown={(event) => { if (event.key === "Escape") close(); }}
          className="card animate-fade-up absolute right-0 top-full z-20 mt-2 w-[min(20rem,calc(100vw-3rem))] space-y-4 text-left"
        >
          <div>
            <label htmlFor={languageId} className="mb-2 block text-sm font-semibold">{t("Language")}</label>
            <Select
              id={languageId}
              aria-label={t("Language")}
              className="min-h-11 text-base md:text-sm"
              value={language}
              onChange={pickLanguage}
              options={LANGUAGE_OPTIONS}
            />
          </div>
          <div>
            <label htmlFor={currencyId} className="mb-2 block text-sm font-semibold">{t("Display currency")}</label>
            <Select
              id={currencyId}
              aria-label={t("Display currency")}
              className="min-h-11 text-base md:text-sm"
              value={currency}
              onChange={onCurrencyChange}
              options={currencyOptions}
            />
          </div>
          <p className="text-xs leading-5 text-muted">{t("You can change both later in Settings → Preferences.")}</p>
          <button type="button" onClick={confirm} className="btn-primary min-h-[44px] w-full">
            {t("Looks good")}
          </button>
        </div>
      )}
    </div>
  );
}
