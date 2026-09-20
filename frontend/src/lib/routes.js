export const HAS_PUBLIC_HOME = import.meta.env.VITE_PORTFYL_EDITION === "cloud";
export const TRACKER_HOME = HAS_PUBLIC_HOME ? "/dashboard" : "/";

// True only for the authenticated app host; the marketing/demo host (and
// local dev) never counts as the tracker.
export const isTrackerHost = (hostname) => hostname.toLowerCase() === "app.portfyl.com";

// The public read-only demo (portfyl.com/demo/*) only exists in the cloud
// edition, and only on the marketing host -- isTrackerHost() callers gate
// that separately so a visitor can never reach it from app.portfyl.com.
export const isDemoPath = (pathname) =>
  HAS_PUBLIC_HOME && (pathname === "/demo" || pathname.startsWith("/demo/"));
