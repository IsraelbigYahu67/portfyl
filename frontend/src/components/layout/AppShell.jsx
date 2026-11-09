import { useCallback, useRef, useState } from "react";
import DesktopSidebar from "./DesktopSidebar";
import MobileNavDrawer from "./MobileNavDrawer";
import MobileBottomNav from "./MobileBottomNav";
import MobileTopBar from "./MobileTopBar";
import { useRouteFocusAnnouncer } from "../../hooks/useRouteFocusAnnouncer";
import { NavGroupsContext } from "./NavGroupsContext";
import { useT } from "../../i18n/I18nProvider";

export default function AppShell({ groups, children }) {
  const t = useT();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const mainRef = useRef(null);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  useRouteFocusAnnouncer(mainRef);

  return (
    <NavGroupsContext.Provider value={groups}>
    <div className="flex min-h-dvh bg-bg">
      <a href="#main-content" className="skip-link">
        {t("Skip to main content")}
      </a>

      <div className="hidden lg:flex shrink-0 sticky top-0 h-dvh self-start">
        <DesktopSidebar groups={groups} />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileTopBar />
        <MobileNavDrawer groups={groups} open={drawerOpen} onClose={closeDrawer} />
        <main
          id="main-content"
          ref={mainRef}
          tabIndex={-1}
          className="min-w-0 flex-1 p-3 sm:p-6"
        >
          {children}
        </main>
        {/* Keeps the last line of the page clear of the fixed bottom bar. */}
        <div aria-hidden="true" className="h-[calc(4.75rem+env(safe-area-inset-bottom))] shrink-0 lg:hidden" />
        {/* "More" toggles the drawer; tapping a bar page closes it even when that
            page is already the open route (no route change to close it). */}
        <MobileBottomNav
          open={drawerOpen}
          onOpenMenu={() => setDrawerOpen((open) => !open)}
          onNavigate={closeDrawer}
        />
      </div>
    </div>
    </NavGroupsContext.Provider>
  );
}
