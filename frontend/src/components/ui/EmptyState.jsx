export function EmptyState({ icon: Icon, title, hint, action, className = "" }) {
  return (
    <div className={`flex flex-col items-center justify-center text-center py-10 px-4 ${className}`}>
      {Icon && (
        <span className="grid place-items-center w-11 h-11 rounded-2xl bg-surface-card-elevated text-muted mb-3">
          <Icon size={20} />
        </span>
      )}
      {title && <p className="font-display text-sm font-semibold text-ink">{title}</p>}
      {hint && <p className="text-xs text-muted mt-1 max-w-[34ch]">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
