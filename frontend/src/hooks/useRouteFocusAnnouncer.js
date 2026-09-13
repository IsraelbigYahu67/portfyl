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
    const heading = main.querySelector("h1");
    const target = heading || main;
    if (heading && !heading.hasAttribute("tabindex")) {
      heading.setAttribute("tabindex", "-1");
    }
    target.focus();
  }, [mainRef, pathname]);
}
