const PAGE_SIZES = [25, 50, 100];

export default function Pagination({ offset, limit, total, onOffsetChange, onLimitChange, ariaLabel }) {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + limit, total);

  const goTo = (page) => onOffsetChange(Math.max(0, (page - 1) * limit));

  return (
    <nav aria-label={ariaLabel} className="flex items-center justify-between gap-4 flex-wrap py-3">
      <span className="text-xs text-muted tabular-nums">
        {rangeStart}–{rangeEnd} of {total}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="btn-ghost text-xs px-2 py-1"
          onClick={() => goTo(currentPage - 1)}
          disabled={currentPage <= 1}
        >
          Previous
        </button>
        {totalPages <= 7 && (
          <div className="flex items-center gap-1">
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
              <button
                key={page}
                type="button"
                aria-current={page === currentPage ? "page" : undefined}
                className={`text-xs px-2 py-1 rounded ${
                  page === currentPage ? "bg-brand text-white" : "btn-ghost"
                }`}
                onClick={() => goTo(page)}
              >
                {page}
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          className="btn-ghost text-xs px-2 py-1"
          onClick={() => goTo(currentPage + 1)}
          disabled={currentPage >= totalPages}
        >
          Next
        </button>
      </div>
      {onLimitChange && (
        <label className="text-xs text-muted flex items-center gap-2">
          Rows per page
          <select
            className="input py-1"
            value={limit}
            onChange={(e) => onLimitChange(Number(e.target.value))}
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      )}
    </nav>
  );
}
