import { useCallback, useMemo, useState } from "react";
import StockValuationPanel from "../../showcase/StockValuationPanel";
import { SHOWCASE_PE_HISTORY } from "../../showcase/showcaseData";
import SegmentedControl from "../../ui/SegmentedControl";
import { demoPortfolio } from "../../../demo/demoPortfolio";
import AppScope from "./AppScope";
import { stockLabels, stockPickAria } from "./miniDemoLabels";

// The stocks that have a sample P/E history; the buttons are their tickers.
const SYMBOLS = Object.freeze(Object.keys(SHOWCASE_PE_HISTORY));
const OPTIONS = Object.freeze(SYMBOLS.map((symbol) => ({ value: symbol, label: symbol })));

// Stock detail mini demo: the app's stock header, the P/E against its
// five-year average and the P/E history, for one of three sample stocks.
export default function MiniStock({ language, copy, onUse }) {
  const [symbol, setSymbol] = useState(SYMBOLS[0]);
  const holding = useMemo(() => demoPortfolio.holdings.find((candidate) => candidate.symbol === symbol), [symbol]);
  const labels = useMemo(() => stockLabels(copy), [copy]);
  const change = useCallback((value) => {
    setSymbol(value);
    onUse?.();
  }, [onUse]);

  return (
    <AppScope language={language}>
      <div className="space-y-4 min-w-0">
        <SegmentedControl aria-label={stockPickAria(copy)} value={symbol} onChange={change} options={OPTIONS} />
        <StockValuationPanel
          holding={holding}
          peHistory={SHOWCASE_PE_HISTORY[symbol] ?? []}
          currency={demoPortfolio.currency}
          labels={labels}
        />
      </div>
    </AppScope>
  );
}
