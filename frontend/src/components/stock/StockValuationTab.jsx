import { StockDataTab } from "./StockDataTab";

const SECTIONS = ["ratiosAnalyst", "valuation", "valuationHistory"];

export function StockValuationTab(props) {
  return <StockDataTab {...props} view="valuation" sectionIds={SECTIONS} />;
}
