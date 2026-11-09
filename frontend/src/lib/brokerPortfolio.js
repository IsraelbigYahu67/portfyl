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

// Sentences are English source text marked for translation and run through
// `t` (the i18n translate function); without `t` they read in English.
const msg = (text) => text;
const english = (text, vars) => text.replace(/\{(\w+)\}/g, (m, key) => (vars && key in vars ? String(vars[key]) : m));

const SOURCE_PHRASES = { own: msg("your own transactions"), demo: msg("sample data") };

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

function joinWords(words, t) {
  if (words.length < 2) return words.join("");
  return t("{list} and {last}", { list: words.slice(0, -1).join(", "), last: words.at(-1) });
}

export function describeSplit(previous, created, broker, t = english) {
  const brokers = (previous.brokers ?? []).filter((existing) => existing !== broker);
  const named = brokers.filter((existing) => !SOURCE_PHRASES[existing]).map(brokerLabel);
  const parts = [
    ...(named.length ? [t("{brokers} data", { brokers: joinWords(named, t) })] : []),
    ...brokers.filter((existing) => SOURCE_PHRASES[existing]).map((existing) => t(SOURCE_PHRASES[existing])),
  ];
  return t("“{previous}” already holds {contents}, so {broker} goes into its own portfolio “{created}”.", {
    previous: previous.name,
    contents: joinWords(parts, t),
    broker: brokerLabel(broker),
    created: created.name,
  });
}

// Sentence appended to a "connected" message after useBrokerPortfolio.open().
export function splitNote(session, broker, t = english) {
  if (session?.created) return ` ${describeSplit(session.previous, session.created, broker, t)}`;
  if (session?.blocked) {
    return ` ${t("“{previous}” already holds other data, but a separate {broker} portfolio could not be created ({reason}), so it was connected there.", {
      previous: session.previous.name,
      broker: brokerLabel(broker),
      reason: session.blocked,
    })}`;
  }
  return "";
}
