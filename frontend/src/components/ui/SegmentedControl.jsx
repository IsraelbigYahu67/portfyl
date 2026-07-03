/**
 * Segmented toggle — the grey pill-row pattern repeated across the app.
 *
 *   <SegmentedControl
 *     aria-label="Chart mode"
 *     value={mode}
 *     onChange={setMode}
 *     options={[{ value: "value", label: "Value" }, { value: "growth", label: "Growth %" }]}
 *   />
 */
const SIZES = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-2.5 py-1 text-xs",
};

export default function SegmentedControl({
  options,
  value,
  onChange,
  size = "md",
  block = false,
  className = "",
  "aria-label": ariaLabel,
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`${block ? "flex w-full" : "inline-flex"} gap-0.5 rounded-lg bg-slate-100 p-0.5 ${className}`}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            aria-pressed={active}
            aria-label={opt.title}
            disabled={opt.disabled}
            title={opt.title}
            onClick={() => onChange(opt.value)}
            className={`rounded-md font-medium transition-colors ${block ? "flex-1 flex items-center justify-center" : ""} ${SIZES[size]} ${
              active
                ? "bg-white font-semibold text-brand shadow-sm"
                : "text-slate-500 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-slate-500"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
