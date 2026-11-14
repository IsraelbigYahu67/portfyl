import { msg } from "../i18n/I18nProvider";

// Sections the Activity Flex Query needs to import stocks, ETFs, dividends and
// cash (parsed by backend/importers/formats/ibkr_flex.py). Options only need
// Trades.
// Shared by the Settings connection card and the Import page guide.
// Section names are IBKR's own menu labels and stay English; the level hint
// is a Portfyl phrase, translated where shown with t(level).
export const IBKR_FLEX_SECTIONS = [
  ["Trades", msg("Execution level")],
  ["Cash Transactions", msg("Detail level")],
  ["Corporate Actions", null],
  ["Transfers", null],
  ["Open Positions", null],
  ["Account Information", null],
];
