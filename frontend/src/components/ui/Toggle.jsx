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
      className={`w-9 h-5 rounded-full transition-colors relative ${checked ? activeClassName : "bg-slate-300"}`}
      style={{ boxShadow: "var(--shadow-inset)" }}
    >
      <span
        className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow-sm ${checked ? "left-[18px]" : "left-0.5"}`}
      />
    </button>
  );
}
