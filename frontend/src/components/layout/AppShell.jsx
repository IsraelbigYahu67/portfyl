import { useCallback, useRef, useState } from "react";
import DesktopSidebar from "./DesktopSidebar";
import MobileNavDrawer from "./MobileNavDrawer";
import MobileBottomNav from "./MobileBottomNav";
import MobileTopBar from "./MobileTopBar";
import { useRouteFocusAnnouncer } from "../../hooks/useRouteFocusAnnouncer";

export default function AppShell({ groups, children }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const mainRef = useRef(null);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  useRouteFocusAnnouncer(mainRef);

  return (
    <div className="flex min-h-dvh bg-bg">
      <a href="#main-content" className="skip-link">
        Skip to main content
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
          className="min-w-0 flex-1 p-4 sm:p-6"
        >
          {children}
        </main>
        {/* Keeps the last line of the page clear of the fixed bottom bar. */}
        <div aria-hidden="true" className="h-[calc(4.75rem+env(safe-area-inset-bottom))] shrink-0 lg:hidden" />
        <MobileBottomNav open={drawerOpen} onOpenMenu={() => setDrawerOpen(true)} />
      </div>
    </div>
  );
}
