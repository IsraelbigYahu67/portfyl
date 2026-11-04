import { StockDataTab } from "./StockDataTab";

const SECTIONS = ["ratiosAnalyst", "valuationHistory"];

export function StockValuationTab(props) {
  return <StockDataTab {...props} view="valuation" sectionIds={SECTIONS} />;
}
