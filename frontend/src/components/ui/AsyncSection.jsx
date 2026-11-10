import { getApiErrorMessage } from "../../lib/apiError";
import { useT } from "../../i18n/I18nProvider";
import ErrorState from "./ErrorState";

export default function AsyncSection({
  isLoading = false,
  error,
  onRetry,
  loading,
  isEmpty = false,
  empty,
  children,
}) {
  const t = useT();
  if (isLoading) {
    return (
      <div role="status" aria-label={t("Loading")}>
        {loading}
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert">
        <ErrorState message={getApiErrorMessage(error, undefined, t)} onRetry={onRetry} />
      </div>
    );
  }

  if (isEmpty) return empty;
  return children;
}
