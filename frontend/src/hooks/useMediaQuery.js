import { useEffect, useState } from "react";

// Tailwind's `md` breakpoint (768px) and below. Dense tables become card lists
// here (DESIGN.md section 8), so only one of the two layouts is in the DOM.
export const PHONE_QUERY = "(max-width: 767px)";

function read(query, fallback) {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return fallback;
  return window.matchMedia(query).matches;
}

// Subscribes to a CSS media query. Without `matchMedia` (jsdom, old browsers)
// it reports `fallback`, so tests and unknown environments get the desktop UI.
export function useMediaQuery(query, fallback = false) {
  const [matches, setMatches] = useState(() => read(query, fallback));

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return undefined;
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, [query]);

  return matches;
}

export function useIsPhone() {
  return useMediaQuery(PHONE_QUERY, false);
}
