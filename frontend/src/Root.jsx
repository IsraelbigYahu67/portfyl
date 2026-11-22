import { lazy, Suspense, useEffect, useState } from "react";
import { HAS_PUBLIC_HOME, contentPageFor, isRetiredDemoPath, isTrackerHost, landingLanguage, legalPage } from "./lib/routes";
import { CONTENT_PAGES } from "./seo/pages";
import RouteBoundary from "./components/layout/RouteBoundary";
import AnalyticsProvider, { useAnalytics } from "./analytics/AnalyticsProvider";
import ConsentBanner from "./analytics/ConsentBanner";
import AnalyticsPreferences from "./analytics/AnalyticsPreferences";

const Tracker = lazy(() => import("./TrackerBootstrap"));
const Welcome = HAS_PUBLIC_HOME ? lazy(() => import("./pages/Welcome")) : null;
const Legal = lazy(() => import("./pages/Legal"));
const ContentRoute = HAS_PUBLIC_HOME ? lazy(() => import("./pages/content/ContentRoute")) : null;

const LOADING = <div role="status" className="min-h-screen flex items-center justify-center">Loading Portfyl…</div>;

// The public /demo is retired (the server answers it with a 301 to the home
// page). This is the safety net for in-app navigation and for hosts without
// the backend: it sends the visitor home and shows the same status text as
// the Suspense fallback until the browser has moved.
function RetiredDemo() {
  useEffect(() => { window.location.replace("/"); }, []);
  return LOADING;
}

// Renders the pending-consent banner and a reopenable preferences panel.
// Lives inside AnalyticsProvider so both can call useAnalytics(); rendered
// as a sibling of the routed content so it survives route switches.
//
// It renders nothing until mounted: consent lives in a cookie the build-time
// prerender cannot see, so the banner must not be part of the hydrated HTML.
function AnalyticsOverlay({ language }) {
  const { preferencesOpen, closeAnalyticsPreferences } = useAnalytics();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;
  return (
    <>
      <ConsentBanner language={language} />
      {preferencesOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" role="presentation">
          <div className="w-full max-w-md">
            <AnalyticsPreferences onClose={closeAnalyticsPreferences} language={language} />
          </div>
        </div>
      )}
    </>
  );
}

// `location` is only passed by the build-time prerender
// (src/entry-prerender.jsx), which has no window; the browser reads its own.
// `contentPages` replaces the content-page registry (src/seo/pages/index.js);
// only tests pass it, to render a fixture page.
export default function Root({ location, contentPages }) {
  const [pathname, setPathname] = useState(() => location?.pathname ?? window.location.pathname);
  useEffect(() => {
    const updatePath = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', updatePath);
    return () => window.removeEventListener('popstate', updatePath);
  }, []);
  const trackerHost = isTrackerHost(location?.hostname ?? window.location.hostname);
  // Public visitors do not download the tracker or mount private data providers,
  // and a retired /demo address never reaches the tracker either.
  const retiredDemo = isRetiredDemoPath(pathname) && !trackerHost;
  // "/", "/en/" and "/de/" are the public home in Czech, English and German.
  const welcomeLanguage = trackerHost ? null : landingLanguage(pathname);
  const showWelcome = Boolean(welcomeLanguage);
  // Registered content pages (guides, explainers) are public like the landing
  // pages, and never rendered on the tracker host.
  const contentPage = trackerHost || showWelcome ? null : contentPageFor(pathname, contentPages);
  // /terms and /privacy stay public on every host (see legalPage).
  const legal = legalPage(pathname);
  const routeKey = legal ? 'legal' : retiredDemo ? 'retired-demo' : showWelcome ? 'welcome' : contentPage ? `content:${contentPage.path}` : 'tracker';
  // AnalyticsProvider wraps everything, outside the welcome/tracker
  // selection and outside AuthProvider (which lives inside the lazy
  // Tracker/App.jsx tree), so consent survives route switches and never
  // depends on an authenticated session.
  return <AnalyticsProvider>
    <RouteBoundary key={routeKey}><Suspense fallback={LOADING}>
      {legal ? <Legal page={legal} /> : retiredDemo ? <RetiredDemo /> : showWelcome ? <Welcome language={welcomeLanguage} /> : contentPage && ContentRoute ? <ContentRoute page={contentPage} pages={contentPages ?? CONTENT_PAGES} /> : <Tracker />}
    </Suspense></RouteBoundary>
    {/* On a landing or content page the consent text follows the page language. */}
    <AnalyticsOverlay language={welcomeLanguage ?? contentPage?.language ?? null} />
  </AnalyticsProvider>;
}
