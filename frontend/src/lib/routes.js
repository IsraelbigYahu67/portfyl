import { CONTENT_PAGES } from "../seo/pages";

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

// The registered content page at `pathname`, or null. Pages live in
// src/seo/pages/index.js; their canonical path ends in "/", and like the
// landing pages the form without the slash is the same page (the server 301s
// it). Cloud only by default; `pages` is the override tests inject fixtures
// through.
export const contentPageFor = (pathname, pages = HAS_PUBLIC_HOME ? CONTENT_PAGES : []) => {
  const path = pathname.endsWith("/") ? pathname : `${pathname}/`;
  return pages.find((page) => page.path === path) ?? null;
};

// The public read-only demo (portfyl.com/demo/*) is retired: the landing page
// shows live mini examples instead. The server answers /demo and /demo/* with a
// 301 to the home page; Root.jsx sends a client-side navigation there the same
// way. Cloud edition only, and isTrackerHost() callers gate the marketing host
// separately so app.portfyl.com is never redirected.
export const isRetiredDemoPath = (pathname) =>
  HAS_PUBLIC_HOME && (pathname === "/demo" || pathname.startsWith("/demo/"));

// Legal pages (both editions; Settings -> Data & Privacy links them). They
// render on every host, including app.portfyl.com, because Stripe Checkout and
// signed-out visitors link to them. /security is the security page, rendered
// by the same component. Returns "terms", "privacy", "security" or null.
export const legalPage = (pathname) => {
  const match = /^\/(terms|privacy|security)\/?$/.exec(pathname);
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
