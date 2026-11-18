import { useState } from "react";
import AllocationPanel from "../../components/showcase/AllocationPanel";
import KpiBox from "../../components/ui/KpiBox";
import { formatMoney, formatPercent } from "../../lib/format";
import { useDemoData } from "../DemoDataContext";

const GROUPINGS = [
  { value: "holdings", label: "Holdings" },
  { value: "sectors", label: "Sectors" },
  { value: "countries", label: "Countries" },
  { value: "currencies", label: "Currencies" },
  { value: "assetTypes", label: "Asset types" },
];

const LABELS = {
  title: "Position allocation",
  groupingAria: "Allocation grouping",
  tableCaption: "Allocation details",
  columns: { name: "Name", value: "Value", weight: "Weight" },
};

export default function DemoAllocation() {
  const data = useDemoData();
  const [grouping, setGrouping] = useState("holdings");
  const positionTotal = data.holdings.reduce((sum, holding) => sum + holding.marketValue, 0);
  const totalWeight = data.holdings.reduce((sum, holding) => sum + holding.weight, 0);

  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow data-label">Synthetic portfolio</p>
        <h1 className="text-2xl font-display font-bold mt-1">Allocation</h1>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <KpiBox label="Positions" value={formatMoney(positionTotal, "USD")} />
        <KpiBox label="Portfolio weight" value={formatPercent(totalWeight, { sign: false })} />
        <KpiBox label="Diversification" value="10 sectors" />
      </div>

      <AllocationPanel
        holdings={data.holdings}
        currency="USD"
        grouping={grouping}
        groupings={GROUPINGS}
        onGroupingChange={setGrouping}
        labels={LABELS}
      />
    </div>
  );
}
