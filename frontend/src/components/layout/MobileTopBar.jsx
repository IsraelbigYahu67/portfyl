import AccountMenu from "../AccountMenu";
import PortfolioSwitcher from "../PortfolioSwitcher";

// Phone header. Sticky, so the portfolio switcher and the account menu (the
// only place to log out) stay in reach however far the page is scrolled. The
// page links live in MobileBottomNav and the drawer behind its "More" button.
export default function MobileTopBar() {
  return (
    <header className="app-topbar lg:hidden sticky top-0 z-30 flex items-center gap-2 px-3 py-1.5 border-b border-hairline">
      <img src="/portfyl-mark.svg" alt="Portfyl" className="h-8 w-8 shrink-0 object-contain" />
      <div className="min-w-0 flex-1">
        <PortfolioSwitcher compact />
      </div>
      <AccountMenu compact />
    </header>
  );
}
