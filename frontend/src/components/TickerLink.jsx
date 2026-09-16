import { Link } from 'react-router-dom';
import { useStockIntentPrefetch } from '../hooks/useStockIntentPrefetch';

export function TickerLink({ ticker, className = '', children, onClick, onMouseEnter, onMouseLeave, onFocus, onBlur, ...props }) {
  const intent = useStockIntentPrefetch(ticker);
  if (!ticker) return <span className={className}>{children ?? '—'}</span>;
  const combine = (name, handler) => event => { intent[name](event); handler?.(event); };
  return <Link {...props} to={`/stock/${encodeURIComponent(String(ticker).toUpperCase())}`}
    onClick={event => { event.stopPropagation(); onClick?.(event); }}
    onMouseEnter={combine('onMouseEnter', onMouseEnter)} onMouseLeave={combine('onMouseLeave', onMouseLeave)}
    onFocus={combine('onFocus', onFocus)} onBlur={combine('onBlur', onBlur)}
    className={`hover:text-brand hover:underline underline-offset-2 transition-colors ${className}`}>
    {children ?? ticker}
  </Link>;
}
