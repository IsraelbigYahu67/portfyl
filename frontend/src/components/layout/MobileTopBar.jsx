import { Menu } from "lucide-react";

export default function MobileTopBar({ open = false, onOpenMenu }) {
  return (
    <header className="lg:hidden flex items-center justify-between px-4 py-2 bg-surface-card border-b border-hairline">
      <div className="flex items-center gap-2">
        <img src="/portfyl-mark.png" alt="Portfyl" className="w-8 h-8 object-contain" />
        <span className="font-display font-bold text-[15px] text-ink">Portfyl</span>
      </div>
      <button
        type="button"
        onClick={onOpenMenu}
        aria-label="Open navigation menu"
        aria-expanded={open}
        aria-controls="mobile-nav-drawer"
        className="w-11 h-11 inline-flex items-center justify-center rounded-lg text-muted hover:text-ink hover:bg-surface-hover"
      >
        <Menu size={22} aria-hidden="true" />
      </button>
    </header>
  );
}
