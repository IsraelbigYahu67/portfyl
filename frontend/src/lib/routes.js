export const HAS_PUBLIC_HOME = import.meta.env.VITE_PORTFYL_EDITION === "cloud";
export const TRACKER_HOME = HAS_PUBLIC_HOME ? "/dashboard" : "/";

// True only for the authenticated app host; the marketing/demo host (and
// local dev) never counts as the tracker.
export const isTrackerHost = (hostname) => hostname.toLowerCase() === "app.portfyl.com";

// Public landing URLs, one per language (cloud only). Czech, the primary
// market, owns the root; English and German live in subdirectories. Each URL
// always serves the same language -- never redirect by a guessed language
// (docs/superpowers/plans/2026-11-09-portfyl-seo.md, decision O1).
export const LANDING_PATHS = Object.freeze({ cs: "/", en: "/en/", de: "/de/" });

// Language of the landing page at `pathname`, or null when it is not one.
// "/en" and "/en/" are the same page; the canonical form has the slash.
export const landingLanguage = (pathname) => {
  if (!HAS_PUBLIC_HOME) return null;
  if (pathname === "/") return "cs";
  const match = /^\/(en|de)\/?$/.exec(pathname);
  return match ? match[1] : null;
};

// The public read-only demo (portfyl.com/demo/*) only exists in the cloud
// edition, and only on the marketing host -- isTrackerHost() callers gate
// that separately so a visitor can never reach it from app.portfyl.com.
export const isDemoPath = (pathname) =>
  HAS_PUBLIC_HOME && (pathname === "/demo" || pathname.startsWith("/demo/"));

// Legal pages (both editions; Settings -> Data & Privacy links them). They
// render on every host, including app.portfyl.com, because Stripe Checkout and
// signed-out visitors link to them. Returns "terms", "privacy" or null.
export const legalPage = (pathname) => {
  const match = /^\/(terms|privacy)\/?$/.exec(pathname);
  return match ? match[1] : null;
};

// Read-only replay of onboarding for signed-in users (Settings -> Preferences).
// Rendered full-screen by App.jsx's AppLayout, outside the shell. It is pure
// frontend: no API, no analytics. Lives here, not in routes/authenticatedRoutes,
// so components inside lazily loaded pages can link to it without importing
// the lazy route registry that loads them.
export const ONBOARDING_PREVIEW_PATH = "/onboarding/preview";
// Like React Router and legalPage(), accept one trailing slash.
export const isOnboardingPreviewPath = (pathname) => /^\/onboarding\/preview\/?$/.test(pathname);
