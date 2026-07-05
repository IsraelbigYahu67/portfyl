export function SectionHeader({ icon: Icon, action, className = "", children }) {
  return (
    <div className={`flex items-center justify-between mb-4 ${className}`}>
      <div className="flex items-center gap-2 min-w-0">
        {Icon && (
          <span className="grid place-items-center w-6 h-6 rounded-lg bg-brand/10 text-brand shrink-0">
            <Icon size={13} />
          </span>
        )}
        <span className="eyebrow truncate">{children}</span>
      </div>
      {action && <div className="flex items-center gap-2 shrink-0">{action}</div>}
    </div>
  );
}
