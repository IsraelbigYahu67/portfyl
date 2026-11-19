// Pure mappers from the page copy (COPY[language].miniDemo, written in
// pages/welcomeCopy.js) onto the `labels` objects the shared panels in
// components/showcase take. A panel translates nothing: every string it shows
// arrives from here, so the demos never hold a text of their own.

export function allocationLabels(copy) {
  const { title, groupingAria, tableCaption, columns } = copy.allocation;
  return { title, groupingAria, tableCaption, columns: { name: columns.name, value: columns.value, weight: columns.weight } };
}

export function allocationGroupings(copy) {
  const { groupings } = copy.allocation;
  return [
    { value: "holdings", label: groupings.holdings },
    { value: "sectors", label: groupings.sectors },
    { value: "currencies", label: groupings.currencies },
  ];
}

export function stockLabels(copy) {
  const { pe, fivePe, forwardPe, vsAverage, historyTitle, tableCaption, disclaimer } = copy.stock;
  return { pe, fivePe, forwardPe, vsAverage, historyTitle, tableCaption, disclaimer };
}

// The accessible name of the row of stock buttons (the buttons are tickers).
export function stockPickAria(copy) {
  return copy.stock.pickAria;
}

export function performanceLabels(copy) {
  const { title, modeAria, totalReturn, benchmarkReturn, tableCaption, columns } = copy.performance;
  return {
    title, modeAria, totalReturn, benchmarkReturn, tableCaption,
    columns: { date: columns.date, value: columns.value, benchmark: columns.benchmark },
  };
}

export function performanceModes(copy) {
  const { modes } = copy.performance;
  return [
    { value: "value", label: modes.value },
    { value: "growth", label: modes.growth },
  ];
}

export function dividendsLabels(copy) {
  const { received, upcoming, receivedTotal, upcomingTotal, viewAria, tableCaption, columns } = copy.dividends;
  return {
    received, upcoming, receivedTotal, upcomingTotal, viewAria, tableCaption,
    columns: { month: columns.month, amount: columns.amount },
  };
}

export function dividendsViews(copy) {
  return [
    { value: "received", label: copy.dividends.received },
    { value: "upcoming", label: copy.dividends.upcoming },
  ];
}

export function portfoliosLabels(copy) {
  const { currencyAria, portfolioNames, ratesNote, tableCaption, columns } = copy.portfolios;
  return {
    currencyAria,
    portfolioNames: { long: portfolioNames.long, dividend: portfolioNames.dividend, growth: portfolioNames.growth },
    ratesNote,
    tableCaption,
    columns: { name: columns.name, value: columns.value, weight: columns.weight },
  };
}

// Which display currency a demo opens in: the currency of the page's language,
// so a Czech visitor starts in koruna. Not a text, but a default every demo
// that converts money shares.
const DEFAULT_CURRENCY = Object.freeze({ cs: "CZK", de: "EUR", en: "USD" });

export function defaultCurrency(language) {
  return DEFAULT_CURRENCY[language] ?? DEFAULT_CURRENCY.en;
}

// The three sample currencies as switch options (the codes are the labels).
export const CURRENCY_OPTIONS = Object.freeze([
  { value: "CZK", label: "CZK" },
  { value: "EUR", label: "EUR" },
  { value: "USD", label: "USD" },
]);
