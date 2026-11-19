import { useCallback, useMemo, useState } from "react";
import PerformancePanel from "../../showcase/PerformancePanel";
import { demoPortfolio } from "../../../demo/demoPortfolio";
import AppScope from "./AppScope";
import { performanceLabels, performanceModes } from "./miniDemoLabels";

// Performance mini demo: the sample portfolio against the S&P 500 in the
// app's own chart, as growth in percent first, or as value.
export default function MiniPerformance({ language, copy, onUse }) {
  const [mode, setMode] = useState("growth");
  const labels = useMemo(() => performanceLabels(copy), [copy]);
  const modes = useMemo(() => performanceModes(copy), [copy]);
  const change = useCallback((value) => {
    setMode(value);
    onUse?.();
  }, [onUse]);

  return (
    <AppScope language={language}>
      <PerformancePanel
        performance={demoPortfolio.performance}
        benchmarks={demoPortfolio.benchmarks}
        benchmarkMeta={demoPortfolio.benchmarkMeta}
        currency={demoPortfolio.currency}
        mode={mode}
        onModeChange={change}
        modes={modes}
        labels={labels}
      />
    </AppScope>
  );
}
