// Sections the Activity Flex Query needs for the stock/ETF/dividend/cash
// import (backend/importers/formats/ibkr_flex.py). Options only need Trades.
// Shared by the Settings connection card and the Import page guide.
export const IBKR_FLEX_SECTIONS = [
  ["Trades", "Execution level"],
  ["Cash Transactions", "Detail level"],
  ["Corporate Actions", null],
  ["Transfers", null],
  ["Open Positions", null],
  ["Account Information", null],
];
