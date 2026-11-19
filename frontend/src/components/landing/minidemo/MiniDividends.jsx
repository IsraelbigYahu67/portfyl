import { useCallback, useMemo, useState } from "react";
import DividendsPanel from "../../showcase/DividendsPanel";
import { demoPortfolio } from "../../../demo/demoPortfolio";
import AppScope from "./AppScope";
import { dividendsLabels, dividendsViews } from "./miniDemoLabels";

// Dividends mini demo: the app's own monthly bars for what the sample
// portfolio received so far, and for the next twelve months (an estimate).
export default function MiniDividends({ language, copy, onUse }) {
  const [view, setView] = useState("received");
  const labels = useMemo(() => dividendsLabels(copy), [copy]);
  const views = useMemo(() => dividendsViews(copy), [copy]);
  const change = useCallback((value) => {
    setView(value);
    onUse?.();
  }, [onUse]);

  return (
    <AppScope language={language}>
      <DividendsPanel
        dividends={demoPortfolio.dividends}
        asOf={demoPortfolio.asOf}
        currency={demoPortfolio.currency}
        view={view}
        onViewChange={change}
        views={views}
        labels={labels}
      />
    </AppScope>
  );
}
