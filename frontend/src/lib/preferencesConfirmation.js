// Whether the visitor has confirmed their language/currency on the first-run
// onboarding. Device-level like the language preference, so it lives in
// localStorage under the product prefix. Storage may be unavailable (private
// browsing, blocked cookies): reads then report "not confirmed" and writes
// are ignored, but a failed write is remembered for this page visit.
export const PREFERENCES_CONFIRMED_KEY = "portfyl_preferences_confirmed";

let confirmedInMemory = false;

export function preferencesConfirmed() {
  try {
    return localStorage.getItem(PREFERENCES_CONFIRMED_KEY) === "1" || confirmedInMemory;
  } catch {
    return confirmedInMemory;
  }
}

export function confirmPreferences() {
  try {
    localStorage.setItem(PREFERENCES_CONFIRMED_KEY, "1");
  } catch {
    confirmedInMemory = true; // Storage unavailable; the choice lasts for this visit.
  }
}
