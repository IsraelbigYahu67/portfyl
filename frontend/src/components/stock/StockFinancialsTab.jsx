import { StockDataTab } from "./StockDataTab";

const SECTIONS = ["financials", "earningsRecap", "dividendGrowth"];

export function StockFinancialsTab(props) {
  return <StockDataTab {...props} view="financials" sectionIds={SECTIONS} />;
}
