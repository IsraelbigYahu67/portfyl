// One broker per portfolio: a new import or connection goes into its own
// portfolio when the selected one already holds other data. `brokers` comes
// from GET /portfolios (backend/broker_sources.py).

export const BROKER_LABELS = {
  trading212: "Trading 212",
  ibkr: "Interactive Brokers",
  etoro: "eToro",
  degiro: "Degiro",
  xtb: "XTB",
  schwab: "Charles Schwab",
  fidelity: "Fidelity",
};

const SOURCE_PHRASES = { own: "your own transactions", demo: "sample data" };

export function brokerLabel(broker) {
  return BROKER_LABELS[broker] ?? broker;
}

// True when `broker`'s data must not be mixed into `portfolio`. Native CSV
// (broker null) and an empty portfolio never split.
export function needsOwnPortfolio(portfolio, broker) {
  if (!broker || !portfolio) return false;
  return (portfolio.brokers ?? []).some((existing) => existing !== broker);
}

export function uniquePortfolioName(portfolios, broker) {
  const base = brokerLabel(broker);
  const taken = new Set((portfolios ?? []).map((portfolio) => portfolio.name.toLowerCase()));
  if (!taken.has(base.toLowerCase())) return base;
  let suffix = 2;
  while (taken.has(`${base} ${suffix}`.toLowerCase())) suffix += 1;
  return `${base} ${suffix}`;
}

function joinWords(words) {
  if (words.length < 2) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words.at(-1)}`;
}

export function describeSplit(previous, created, broker) {
  const brokers = (previous.brokers ?? []).filter((existing) => existing !== broker);
  const named = brokers.filter((existing) => !SOURCE_PHRASES[existing]).map(brokerLabel);
  const parts = [
    ...(named.length ? [`${joinWords(named)} data`] : []),
    ...brokers.filter((existing) => SOURCE_PHRASES[existing]).map((existing) => SOURCE_PHRASES[existing]),
  ];
  return `“${previous.name}” already holds ${joinWords(parts)}, so ${brokerLabel(broker)} goes into its own portfolio “${created.name}”.`;
}

// Sentence appended to a "connected" message after useBrokerPortfolio.open().
export function splitNote(session, broker) {
  if (session?.created) return ` ${describeSplit(session.previous, session.created, broker)}`;
  if (session?.blocked) {
    return ` “${session.previous.name}” already holds other data, but a separate ${brokerLabel(broker)} portfolio could not be created (${session.blocked}), so it was connected there.`;
  }
  return "";
}
