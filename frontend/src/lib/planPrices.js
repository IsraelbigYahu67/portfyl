// Monthly plan prices in euro cents, VAT included. One source for the pricing
// page (pages/Pricing.jsx, test mode) and the public landing's price list.
// In billing mode the backend's /billing/status prices still win in the app.
export const PLAN_PRICES_CENTS = Object.freeze({ investor: 599, pro: 999 });

const NBSP = " ";

// "5,99 €" for Czech and German, "€5.99" for English. Built by hand rather
// than with Intl so the prerendered HTML and the browser agree on every
// engine; the no-break space keeps the euro sign on the number's line.
export function formatPlanPrice(cents, language) {
  const euros = cents / 100;
  const text = Number.isInteger(euros) ? String(euros) : euros.toFixed(2);
  return language === "en" ? `€${text}` : `${text.replace(".", ",")}${NBSP}€`;
}
