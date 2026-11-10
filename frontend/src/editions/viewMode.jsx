import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { Smartphone } from "lucide-react";

import SegmentedControl from "../components/ui/SegmentedControl";
import { useT } from "../i18n/I18nProvider";

// Local-edition only (imported solely by editions/local.jsx): lets the owner
// preview the mobile layout on a desktop browser. Layout reacts to the window
// width via CSS breakpoints, so the preview is the same app in an iframe that
// is phone-sized. Same origin, so the session cookie and this preference are
// shared with the framed copy.
const STORAGE_KEY = "sb_view_mode";
const CHANGE_EVENT = "portfyl:view-mode";
const DESKTOP_QUERY = "(min-width: 640px)";
const PHONE_WIDTH = 390;
const PHONE_HEIGHT = 844;

function readMode() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "mobile" ? "mobile" : "desktop";
  } catch {
    return "desktop";
  }
}

function subscribe(onChange) {
  const onStorage = (event) => {
    if (event.key === null || event.key === STORAGE_KEY) onChange();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

export function useViewMode() {
  const mode = useSyncExternalStore(subscribe, readMode, () => "desktop");
  const setMode = useCallback((next) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, next === "mobile" ? "mobile" : "desktop");
    } catch {
      /* storage blocked: the preference just does not stick */
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);
  return [mode, setMode];
}

function isFramed() {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
}

function useIsDesktopWindow() {
  const [wide, setWide] = useState(() => !window.matchMedia || window.matchMedia(DESKTOP_QUERY).matches);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const query = window.matchMedia(DESKTOP_QUERY);
    const update = () => setWide(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return wide;
}

// Wraps the whole private app. Passes children through unless the mobile
// preview is on, the window is actually desktop-sized, and this is the
// top-level document (the framed copy renders the app normally).
export function MobilePreviewFrame({ children }) {
  const t = useT();
  const [mode, setMode] = useViewMode();
  const wide = useIsDesktopWindow();
  if (mode !== "mobile" || !wide || isFramed()) return children;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-surface-hover p-6">
      <div className="flex w-full items-center justify-between" style={{ maxWidth: PHONE_WIDTH }}>
        <span className="flex items-center gap-2 text-sm text-muted">
          <Smartphone size={14} aria-hidden="true" /> {t("Mobile preview")}
        </span>
        <button
          type="button"
          onClick={() => setMode("desktop")}
          className="rounded-full border border-surface-border bg-surface-card-elevated px-3 py-1 text-sm font-medium text-ink"
        >
          {t("Back to desktop")}
        </button>
      </div>
      <iframe
        title={t("Mobile preview")}
        src={window.location.href}
        className="rounded-[28px] border border-surface-border bg-surface-card shadow-xl"
        style={{ width: PHONE_WIDTH, height: `min(${PHONE_HEIGHT}px, calc(100vh - 6rem))` }}
      />
    </div>
  );
}

export function ViewModeSetting() {
  const t = useT();
  const [mode, setMode] = useViewMode();
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{t("View mode")}</h3>
      <SegmentedControl
        aria-label={t("View mode")}
        value={mode}
        onChange={setMode}
        options={[
          { value: "desktop", label: t("Desktop"), title: t("View mode: Desktop") },
          { value: "mobile", label: t("Mobile"), title: t("View mode: Mobile") },
        ]}
      />
      <p className="mt-2 text-xs text-muted">{t("Preview the mobile layout inside a phone-sized frame on this computer.")}</p>
    </div>
  );
}
