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

// Case-insensitive name filter for the broker search box.
export function filterBrokers(query) {
  const needle = query.trim().toLowerCase();
  return {
    supported: SUPPORTED_BROKERS.filter((broker) => broker.name.toLowerCase().includes(needle)),
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
