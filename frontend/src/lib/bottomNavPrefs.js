import { useCallback, useSyncExternalStore } from "react";
import { BOTTOM_NAV_ITEMS } from "../components/layout/navigation";

// Which pages the phone bottom bar shows. Per device, like the theme and the
// display currency (the Preferences card says "on this device"), so it lives in
// localStorage under the same `sb_` prefix as the other preferences.
export const BOTTOM_NAV_KEY = "sb_bottom_nav_items";
export const BOTTOM_NAV_MIN = 2;
export const BOTTOM_NAV_MAX = 5;

export const DEFAULT_BOTTOM_NAV_PATHS = Object.freeze(BOTTOM_NAV_ITEMS.map(({ to }) => to));

const listeners = new Set();
let cachedRaw;
let cachedPaths = DEFAULT_BOTTOM_NAV_PATHS;

function readRaw() {
  try {
    return localStorage.getItem(BOTTOM_NAV_KEY);
  } catch {
    return null;
  }
}

function parse(raw) {
  if (!raw) return DEFAULT_BOTTOM_NAV_PATHS;
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value)) return DEFAULT_BOTTOM_NAV_PATHS;
    return value.filter((path) => typeof path === "string").slice(0, BOTTOM_NAV_MAX);
  } catch {
    return DEFAULT_BOTTOM_NAV_PATHS;
  }
}

// useSyncExternalStore needs a referentially stable snapshot, so the parsed
// list is cached per raw string.
function getSnapshot() {
  const raw = readRaw();
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedPaths = parse(raw);
  }
  return cachedPaths;
}

function subscribe(listener) {
  listeners.add(listener);
  const onStorage = (event) => {
    if (event.key === null || event.key === BOTTOM_NAV_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function write(paths) {
  try {
    if (paths == null) localStorage.removeItem(BOTTOM_NAV_KEY);
    else localStorage.setItem(BOTTOM_NAV_KEY, JSON.stringify(paths));
  } catch {
    // Storage blocked (private window): the bar keeps the default.
  }
  listeners.forEach((listener) => listener());
}

/** The stored paths plus setters. The paths are NOT yet checked against the
 *  edition's navigation; pass them through `resolveBottomNavItems` for that. */
export function useBottomNavPaths() {
  const paths = useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_BOTTOM_NAV_PATHS);
  const setPaths = useCallback((next) => write(next), []);
  const reset = useCallback(() => write(null), []);
  return { paths, setPaths, reset, isDefault: readRaw() === null };
}
