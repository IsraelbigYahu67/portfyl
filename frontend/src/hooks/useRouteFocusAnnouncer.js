import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

export function useRouteFocusAnnouncer(mainRef) {
  const { pathname } = useLocation();
  const previousPathnameRef = useRef(pathname);

  useEffect(() => {
    if (previousPathnameRef.current === pathname) return;
    previousPathnameRef.current = pathname;

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
