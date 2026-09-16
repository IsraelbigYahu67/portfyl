import { NavLink } from "react-router-dom";
import AccountMenu from "../AccountMenu";
import PortfolioSwitcher from "../PortfolioSwitcher";

export default function DesktopSidebar({ groups }) {
  return (
    <aside
      className="w-[232px] shrink-0 bg-surface-card border-r border-surface-border flex flex-col"
      style={{ boxShadow: "1px 0 0 var(--glass-border-alpha)" }}
    >
      <div className="flex items-center gap-2.5 px-[18px] py-4 border-b border-hairline">
        <img src="/portfyl-mark.png" alt="Portfyl" className="w-11 h-11 object-contain" />
        <div className="flex flex-col leading-tight">
          <span className="font-display font-bold text-[17px] tracking-tight text-ink">Portfyl</span>
          <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-muted">Institutional Grade</span>
        </div>
      </div>

      <div className="px-3 pt-2">
        <PortfolioSwitcher />
      </div>

      <nav aria-label="Primary" className="flex-1 px-2.5 py-2 space-y-3 overflow-y-auto">
        {groups.map((group) => {
          const headingId = `desktop-nav-${group.id}`;
          return (
            <section key={group.id} aria-labelledby={headingId}>
              <h2 id={headingId} className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                {group.label}
              </h2>
              <div className="space-y-0.5">
                {group.items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === "/"}
                    className={({ isActive }) => (
                      `flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-all ${
                        isActive
                          ? "font-semibold text-brand bg-[var(--sidebar-active)] shadow-[inset_0_0_0_1px_var(--glass-border-alpha)]"
                          : "text-muted hover:text-ink hover:bg-surface-hover"
                      }`
                    )}
                  >
                    <Icon size={16} aria-hidden="true" />
                    {label}
                  </NavLink>
                ))}
              </div>
            </section>
          );
        })}
      </nav>

      <div className="mt-auto pb-3 space-y-3">
        <div className="px-3">
          <AccountMenu />
        </div>

        <div className="px-5 text-[11px] text-muted" style={{ opacity: 0.7 }}>
          Live data via Yahoo Finance
        </div>
      </div>
    </aside>
  );
}
