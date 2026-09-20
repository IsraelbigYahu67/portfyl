// Localized strings for the public demo shell. Selected from browser
// localStorage only (LANGUAGE_KEY, shared with the landing page) -- no
// network localization, no IP geolocation.
import { LANGUAGE_KEY } from "../pages/welcomeCopy";

export { LANGUAGE_KEY };

export const DEMO_COPY = {
  cs: {
    overview: "Přehled", allocation: "Složení", analytics: "Analytika", dividends: "Dividendy",
    disclosure: "Syntetická ukázka", asOfLabel: "Data k", createAccount: "Vytvořit účet", backHome: "Zpět na web",
    navigation: "Navigace ukázky", notFoundTitle: "Stránka ukázky nenalezena", notFoundHint: "Tato stránka ukázky neexistuje.",
    backToDemo: "Zpět na ukázku", unavailableTitle: "Ukázka je dočasně nedostupná",
    unavailableHint: "Zkuste to prosím znovu, nebo se vraťte na web.",
  },
  en: {
    overview: "Overview", allocation: "Allocation", analytics: "Analytics", dividends: "Dividends",
    disclosure: "Synthetic demo", asOfLabel: "Data as of", createAccount: "Create account", backHome: "Back home",
    navigation: "Demo navigation", notFoundTitle: "Demo page not found", notFoundHint: "This demo page does not exist.",
    backToDemo: "Back to demo", unavailableTitle: "Demo is temporarily unavailable",
    unavailableHint: "Please try again, or return to the site.",
  },
  de: {
    overview: "Übersicht", allocation: "Aufteilung", analytics: "Analyse", dividends: "Dividenden",
    disclosure: "Synthetische Demo", asOfLabel: "Stand vom", createAccount: "Konto erstellen", backHome: "Zur Startseite",
    navigation: "Demo-Navigation", notFoundTitle: "Demo-Seite nicht gefunden", notFoundHint: "Diese Demo-Seite existiert nicht.",
    backToDemo: "Zurück zur Demo", unavailableTitle: "Demo vorübergehend nicht verfügbar",
    unavailableHint: "Bitte versuchen Sie es erneut oder kehren Sie zur Website zurück.",
  },
};

export function getDemoLanguage() {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved && DEMO_COPY[saved]) return saved;
  } catch {
    /* Storage may be unavailable (private browsing, blocked cookies). */
  }
  return "en";
}
