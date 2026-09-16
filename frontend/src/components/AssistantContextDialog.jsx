import { useFocusTrap } from '../hooks/useFocusTrap';

export default function AssistantContextDialog({ open, provider = 'DeepSeek', model, onWithoutContext, onShare }) {
  const ref = useFocusTrap({ active: open, onEscape: onWithoutContext });
  if (!open) return null;
  return (
    <div data-testid="assistant-context-backdrop" className="fixed inset-0 z-[80] bg-black/40 flex items-center justify-center p-4" onMouseDown={event => {
      if (event.target === event.currentTarget) onWithoutContext();
    }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="assistant-consent-title" aria-describedby="assistant-consent-description" className="card w-full max-w-lg max-h-[90dvh] overflow-y-auto space-y-4">
        <h2 id="assistant-consent-title" className="text-lg font-semibold">Share a portfolio summary?</h2>
        <div id="assistant-consent-description" className="text-sm text-muted space-y-2">
          <p>Your server will send the active portfolio summary to {provider} ({model}).</p>
          <p>It includes tickers and names, quantities, cost/prices and approximate values, recorded dividend income, and recent trade details (dates, buy/sell type, quantities, prices and currencies).</p>
          <p>Market data may be delayed. The summary uses recorded transactions and cost basis, without current market valuation. Sharing lasts only for this conversation.</p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <button type="button" className="btn-secondary min-h-11 px-3" onClick={onWithoutContext}>Ask without portfolio data</button>
          <button type="button" className="btn-primary min-h-11 px-3" onClick={onShare}>Share for this conversation</button>
        </div>
      </div>
    </div>
  );
}
