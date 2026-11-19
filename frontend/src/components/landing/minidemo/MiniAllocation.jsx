import { useCallback, useMemo, useState } from "react";
import AllocationPanel from "../../showcase/AllocationPanel";
import { showcaseHoldings } from "../../showcase/showcaseData";
import AppScope from "./AppScope";
import { allocationGroupings, allocationLabels, defaultCurrency } from "./miniDemoLabels";

// Allocation mini demo: the app's own donut and breakdown list on the sample
// portfolios, in the currency of the page's language. Opens grouped by
// position; every change of the switch reports a use.
export default function MiniAllocation({ language, copy, onUse }) {
  const [grouping, setGrouping] = useState("holdings");
  const currency = defaultCurrency(language);
  const holdings = useMemo(() => showcaseHoldings(currency), [currency]);
  const labels = useMemo(() => allocationLabels(copy), [copy]);
  const groupings = useMemo(() => allocationGroupings(copy), [copy]);
  const change = useCallback((value) => {
    setGrouping(value);
    onUse?.();
  }, [onUse]);

  return (
    <AppScope language={language}>
      <AllocationPanel
        holdings={holdings}
        currency={currency}
        grouping={grouping}
        groupings={groupings}
        onGroupingChange={change}
        labels={labels}
      />
    </AppScope>
  );
}
