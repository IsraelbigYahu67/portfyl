// Clay switch: a pressed well (off track) with a raised knob. The --clay-*
// shadows only exist under .theme-clay, so each one falls back to the older
// token or a plain shadow and Premium/Classic keep a flat, readable switch.
export default function Toggle({
  checked,
  onChange,
  disabled = false,
  activeClassName = "bg-brand",
  "aria-label": ariaLabel,
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className={`w-9 h-5 rounded-full transition-colors relative ${checked ? activeClassName : ""}`}
      style={{
        boxShadow: "var(--clay-inset-sm, var(--shadow-inset, none))",
        ...(checked ? null : { background: "var(--bg-subtle)" }),
      }}
    >
      <span
        className={`absolute top-0.5 w-4 h-4 rounded-full bg-surface-card-elevated transition-transform ${checked ? "left-[18px]" : "left-0.5"}`}
        style={{ boxShadow: "var(--clay-raise-sm, 0 1px 2px rgba(16, 22, 43, 0.25))" }}
      />
    </button>
  );
}
