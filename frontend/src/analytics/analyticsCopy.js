// Localized strings for the consent banner and analytics preferences panel.
// Language is read from the same localStorage key the landing page and demo
// use -- no network localization, no IP geolocation.
import { LANGUAGE_KEY } from "../pages/welcomeCopy";

export { LANGUAGE_KEY };

export const ANALYTICS_COPY = {
  cs: {
    bannerTitle: "Používáme volitelnou analytiku",
    essential: "Nezbytné pro chod Portfylu vždy zůstává aktivní — přihlášení, workspace a bezpečnost.",
    optional: "Volitelná analytika nám pomáhá měřit anonymní použití produktu. Odmítnutí nijak neomezí funkčnost.",
    changeLater: "Volbu můžete kdykoliv později změnit.",
    accept: "Přijmout analytiku",
    reject: "Odmítnout",
    manage: "Nastavení analytiky",
    close: "Zavřít",
    statusAccepted: "Analytika: přijato",
    statusRejected: "Analytika: odmítnuto",
    statusPending: "Analytika: čeká na rozhodnutí",
  },
  en: {
    bannerTitle: "We use optional analytics",
    essential: "Essential storage that keeps Portfyl working — sign-in, workspace, and security — always stays on.",
    optional: "Optional analytics helps us measure anonymous product use. Rejecting it does not reduce functionality.",
    changeLater: "You can change this choice later.",
    accept: "Accept analytics",
    reject: "Reject",
    manage: "Analytics preferences",
    close: "Close",
    statusAccepted: "Analytics: accepted",
    statusRejected: "Analytics: rejected",
    statusPending: "Analytics: awaiting your decision",
  },
  de: {
    bannerTitle: "Wir verwenden optionale Analyse",
    essential: "Essenzieller Speicher, der Portfyl am Laufen hält — Anmeldung, Arbeitsbereich und Sicherheit — bleibt immer aktiv.",
    optional: "Optionale Analyse hilft uns, die anonyme Produktnutzung zu messen. Eine Ablehnung schränkt die Funktionalität nicht ein.",
    changeLater: "Sie können diese Wahl später jederzeit ändern.",
    accept: "Analyse akzeptieren",
    reject: "Ablehnen",
    manage: "Analyse-Einstellungen",
    close: "Schließen",
    statusAccepted: "Analyse: akzeptiert",
    statusRejected: "Analyse: abgelehnt",
    statusPending: "Analyse: Entscheidung ausstehend",
  },
};

export function getAnalyticsLanguage() {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved && ANALYTICS_COPY[saved]) return saved;
  } catch {
    /* Storage may be unavailable (private browsing, blocked cookies). */
  }
  return "en";
}
