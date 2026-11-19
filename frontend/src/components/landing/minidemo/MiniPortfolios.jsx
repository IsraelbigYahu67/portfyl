import { useCallback, useMemo, useState } from "react";
import PortfoliosPanel from "../../showcase/PortfoliosPanel";
import { SHOWCASE_PORTFOLIOS } from "../../showcase/showcaseData";
import AppScope from "./AppScope";
import { CURRENCY_OPTIONS, defaultCurrency, portfoliosLabels } from "./miniDemoLabels";

const HOLDINGS_COUNT = SHOWCASE_PORTFOLIOS.reduce((sum, portfolio) => sum + portfolio.holdings.length, 0);

// Several-portfolios mini demo: three sample portfolios in EUR, USD and CZK,
// summed in one display currency at a fixed, stated sample rate.
export default function MiniPortfolios({ language, copy, onUse }) {
  const [currency, setCurrency] = useState(() => defaultCurrency(language));
  const labels = useMemo(() => portfoliosLabels(copy), [copy]);
  const change = useCallback((value) => {
    setCurrency(value);
    onUse?.();
  }, [onUse]);

  return (
    <AppScope language={language}>
      <PortfoliosPanel
        portfolios={SHOWCASE_PORTFOLIOS}
        displayCurrency={currency}
        onCurrencyChange={change}
        currencies={CURRENCY_OPTIONS}
        labels={labels}
        holdingsCount={HOLDINGS_COUNT}
      />
    </AppScope>
  );
}
