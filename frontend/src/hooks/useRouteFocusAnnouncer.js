import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

// The last pathname seen by ANY caller of this hook. It lives at module level,
// not in a ref, so it survives remounts: the full-screen onboarding preview
// renders its own <main> outside AppShell, and leaving it remounts AppShell at
// the new path. A per-instance ref would start at that new path and skip the
// navigation. It stays null until the first caller mounts, so the app's very
// first render never moves focus.
let lastSeenPathname = null;

// Module state outlives a test's render tree; call this in beforeEach so one
// test's last path does not decide whether the next test's mount moves focus.
export function resetRouteFocusAnnouncerForTests() {
  lastSeenPathname = null;
}

export function useRouteFocusAnnouncer(mainRef) {
  const { pathname } = useLocation();
  // The pathname this instance moves focus for. StrictMode re-runs a mount
  // effect after its cleanup, when lastSeenPathname already equals pathname;
  // this ref lets that re-run restore the observer the cleanup disconnected.
  const announcedPathnameRef = useRef(null);

  useEffect(() => {
    if (lastSeenPathname !== pathname) {
      announcedPathnameRef.current = lastSeenPathname === null ? null : pathname;
      lastSeenPathname = pathname;
    }
    if (announcedPathnameRef.current !== pathname) return;

    const main = mainRef.current;
    if (!main) return;
    const focusHeading = () => {
      const heading = [...main.querySelectorAll('h1')].find(element => {
        for (let parent = element; parent && parent !== main; parent = parent.parentElement) {
          if (parent.hidden || parent.style.display === 'none') return false;
        }
        return true;
      });
      if (!heading) return false;
      if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
      heading.focus();
      return true;
    };
    if (focusHeading()) return;
    main.focus();
    const observer = new MutationObserver(() => {
      if (focusHeading()) observer.disconnect();
    });
    observer.observe(main, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'hidden'] });
    return () => observer.disconnect();
  }, [mainRef, pathname]);
}
