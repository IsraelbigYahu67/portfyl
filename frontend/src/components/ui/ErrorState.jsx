import { AlertCircle, RefreshCw } from "lucide-react";
import { useT } from "../../i18n/I18nProvider";

/**
 * Consistent inline error + retry block for failed data fetches.
 */
export default function ErrorState({
  message,
  onRetry,
  className = "",
}) {
  const t = useT();
  return (
    <div
      className={`flex flex-col items-center justify-center gap-2 py-6 text-center ${className}`}
    >
      <AlertCircle size={20} className="text-loss" />
      <p className="text-sm text-muted">{message ?? t("Couldn't load this data.")}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="btn-ghost mt-1 flex items-center gap-1.5 text-xs"
        >
          <RefreshCw size={12} />
          {t("Retry")}
        </button>
      )}
    </div>
  );
}
