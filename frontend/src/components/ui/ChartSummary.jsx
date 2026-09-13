// A visible, non-visual counterpart to a chart. Color/geometry is never the
// only carrier of a value: every changed chart renders a ChartSummary whose
// disclosure holds the same data as a table.
export default function ChartSummary({ title, children }) {
  return (
    <details role="group" aria-label={title} className="mt-3">
      <summary className="text-xs text-muted cursor-pointer select-none">View data summary</summary>
      <div className="mt-2 text-xs overflow-x-auto">{children}</div>
    </details>
  );
}
