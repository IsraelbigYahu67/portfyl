import { StockDataTab } from "./StockDataTab";

const SECTIONS = [
  "ownership",
  "insiderVolume",
  "insiderTx",
  "shibuiOwnershipFilings",
  "politicalTrades",
];

export function StockOwnershipTab(props) {
  return <StockDataTab {...props} view="ownership" sectionIds={SECTIONS} />;
}
