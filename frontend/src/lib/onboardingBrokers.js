// Brokers offered on the first-run onboarding (pages/Onboarding.jsx).
// Keys are the backend broker keys (lib/brokerPortfolio.js BROKER_LABELS):
// API sync = backend/routers/broker.py (T212), ibkr.py, etoro.py; file
// import = backend/importers/formats/ plus the native T212 CSV path.
import { msg, translate } from "../i18n/I18nProvider";
import { BROKER_LABELS } from "./brokerPortfolio";
import trading212Icon from "../assets/brokers/trading212.png";
import ibkrIcon from "../assets/brokers/ibkr.png";
import etoroIcon from "../assets/brokers/etoro.png";
import degiroIcon from "../assets/brokers/degiro.png";
import xtbIcon from "../assets/brokers/xtb.png";
import schwabIcon from "../assets/brokers/schwab.png";
import fidelityIcon from "../assets/brokers/fidelity.png";

export const SUPPORTED_BROKERS = Object.freeze([
  {
    key: "trading212",
    icon: trading212Icon,
    api: true,
    credential: msg("API key and secret"),
    syncDescription: "history, positions and dividends",
    fileKind: "CSV",
    hint: msg("In Trading 212 open History and choose Export history (CSV)."),
  },
  {
    key: "ibkr",
    icon: ibkrIcon,
    api: true,
    credential: msg("Flex Web Service token"),
    syncDescription: "trades, dividends and cash from a Flex Query",
    fileKind: "Flex XML",
    hint: msg("In IBKR open Performance & Reports → Flex Queries and run an Activity Flex Query as XML."),
  },
  {
    key: "etoro",
    icon: etoroIcon,
    api: true,
    credential: msg("eToro API key"),
    syncDescription: "trades and dividends",
    fileKind: null,
    hint: null,
  },
  {
    key: "degiro",
    icon: degiroIcon,
    api: false,
    fileKind: "CSV",
    hint: msg("In DEGIRO export Inbox → Transactions and Inbox → Account Statement as CSV, then upload both files."),
  },
  {
    key: "xtb",
    icon: xtbIcon,
    api: false,
    fileKind: "XLSX",
    hint: msg("In xStation 5 open Account history → Cash operations and export the whole period to Excel."),
  },
  {
    key: "schwab",
    icon: schwabIcon,
    api: false,
    fileKind: "CSV",
    hint: msg("On schwab.com open Accounts → History → Transactions, select All and Export."),
  },
  {
    key: "fidelity",
    icon: fidelityIcon,
    api: false,
    fileKind: "CSV",
    hint: msg("On fidelity.com open Activity & Orders, choose the period and Download."),
  },
].map((broker) => Object.freeze({ ...broker, name: BROKER_LABELS[broker.key] })));

// Popular brokers Portfyl cannot read yet. Picking one tells the user up front
// instead of letting them sign up for nothing.
export const UNSUPPORTED_BROKERS = Object.freeze([
  "Robinhood", "Revolut", "Coinbase", "Webull", "Trade Republic", "Freetrade", "Moomoo", "E*TRADE",
]);

export function findSupportedBroker(key) {
  return SUPPORTED_BROKERS.find((broker) => broker.key === key) ?? null;
}

// Which brokers a visitor most likely uses, by app language: the local
// favourites first (Czech/Polish investors lean on Trading 212 / XTB), the
// rest of Europe next, English speakers get the international platforms.
export const BROKER_ORDER_BY_LANGUAGE = Object.freeze({
  cs: Object.freeze(["trading212", "xtb", "degiro", "ibkr", "etoro", "schwab", "fidelity"]),
  pl: Object.freeze(["xtb", "trading212", "degiro", "ibkr", "etoro", "schwab", "fidelity"]),
  de: Object.freeze(["trading212", "degiro", "ibkr", "xtb", "etoro", "schwab", "fidelity"]),
  fr: Object.freeze(["trading212", "degiro", "ibkr", "xtb", "etoro", "schwab", "fidelity"]),
  es: Object.freeze(["trading212", "degiro", "ibkr", "xtb", "etoro", "schwab", "fidelity"]),
  it: Object.freeze(["trading212", "degiro", "ibkr", "xtb", "etoro", "schwab", "fidelity"]),
  pt: Object.freeze(["trading212", "degiro", "ibkr", "xtb", "etoro", "schwab", "fidelity"]),
  nl: Object.freeze(["trading212", "degiro", "ibkr", "xtb", "etoro", "schwab", "fidelity"]),
  en: Object.freeze(["trading212", "ibkr", "etoro", "degiro", "xtb", "schwab", "fidelity"]),
});

// Supported brokers in the order suited to `language`; an unknown language
// gets the English order, and a broker missing from the list goes last.
export function brokersForLanguage(language) {
  const order = Object.hasOwn(BROKER_ORDER_BY_LANGUAGE, language)
    ? BROKER_ORDER_BY_LANGUAGE[language]
    : BROKER_ORDER_BY_LANGUAGE.en;
  const rank = (broker) => {
    const index = order.indexOf(broker.key);
    return index === -1 ? order.length : index;
  };
  // Array.prototype.sort is stable, so ties keep SUPPORTED_BROKERS order.
  return [...SUPPORTED_BROKERS].sort((a, b) => rank(a) - rank(b));
}

// Case-insensitive name filter for the broker search box.
export function filterBrokers(query, language = "en") {
  const needle = query.trim().toLowerCase();
  return {
    supported: brokersForLanguage(language).filter((broker) => broker.name.toLowerCase().includes(needle)),
    unsupported: UNSUPPORTED_BROKERS.filter((name) => name.toLowerCase().includes(needle)),
  };
}

// `t` translates; it defaults to English for callers outside React.
export function brokerMethods(broker, t = (text, vars) => translate(null, text, vars)) {
  return [
    broker.api ? t("API sync") : null,
    broker.fileKind ? t("{fileKind} import", { fileKind: broker.fileKind }) : null,
  ].filter(Boolean).join(" · ");
}
