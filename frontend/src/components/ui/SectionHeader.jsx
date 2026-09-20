export function SectionHeader({ icon: Icon, action, className = "", children }) {
  return (
    <div className={`flex flex-col items-stretch gap-3 mb-4 sm:flex-row sm:items-center sm:justify-between ${className}`}>
      <div className="flex items-center gap-2 min-w-0">
        {Icon && (
          <span className="grid place-items-center w-6 h-6 rounded-lg bg-brand/10 text-brand shrink-0">
            <Icon size={13} />
          </span>
        )}
        <span className="eyebrow data-label truncate">{children}</span>
      </div>
      {action && <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">{action}</div>}
    </div>
  );
}
