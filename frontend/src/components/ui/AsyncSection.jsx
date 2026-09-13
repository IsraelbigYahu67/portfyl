import { getApiErrorMessage } from "../../lib/apiError";
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
  if (isLoading) {
    return (
      <div role="status" aria-label="Loading">
        {loading}
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert">
        <ErrorState message={getApiErrorMessage(error)} onRetry={onRetry} />
      </div>
    );
  }

  if (isEmpty) return empty;
  return children;
}
