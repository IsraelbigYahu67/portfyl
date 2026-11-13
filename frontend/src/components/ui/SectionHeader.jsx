import { createContext, useContext } from "react";

// A phone dashboard widget already shows its own title (with this same icon) on
// the collapsible row above its content. Inside it, a second small title would
// say the same thing twice, so PhoneWidget turns this on and the header keeps
// only its action controls (period toggles, expand button, ...).
export const MergedTitleContext = createContext(false);

export function SectionHeader({ icon: Icon, action, className = "", children }) {
  const titleMerged = useContext(MergedTitleContext);
  if (titleMerged) {
    return action ? (
      <div className={`flex min-w-0 flex-wrap items-center justify-end gap-2 mb-4 ${className}`}>{action}</div>
    ) : null;
  }
  return (
    <div className={`flex flex-col items-stretch gap-3 mb-4 sm:flex-row sm:items-center sm:justify-between ${className}`}>
      <div className="flex items-center gap-2.5 min-w-0">
        {Icon && (
          <span className="card-title-chip grid place-items-center w-[30px] h-[30px] rounded-[10px] shrink-0">
            <Icon size={15} />
          </span>
        )}
        <div className="flex min-w-0 flex-col gap-[5px]">
          <span className="card-title">{children}</span>
          <span className="card-title-bar" aria-hidden="true" />
        </div>
      </div>
      {action && <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">{action}</div>}
    </div>
  );
}
