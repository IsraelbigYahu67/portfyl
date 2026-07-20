import { AlertCircle, RefreshCw } from "lucide-react";

/**
 * Consistent inline error + retry block for failed data fetches.
 */
export default function ErrorState({
  message = "Couldn't load this data.",
  onRetry,
  className = "",
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-2 py-6 text-center ${className}`}
    >
      <AlertCircle size={20} className="text-loss" />
      <p className="text-sm text-muted">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="btn-ghost mt-1 flex items-center gap-1.5 text-xs"
        >
          <RefreshCw size={12} />
          Retry
        </button>
      )}
    </div>
  );
}
