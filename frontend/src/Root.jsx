import { lazy, Suspense, useEffect, useState } from "react";
import { HAS_PUBLIC_HOME, isDemoPath, isTrackerHost, legalPage } from "./lib/routes";
import RouteBoundary from "./components/layout/RouteBoundary";
import AnalyticsProvider, { useAnalytics } from "./analytics/AnalyticsProvider";
import ConsentBanner from "./analytics/ConsentBanner";
import AnalyticsPreferences from "./analytics/AnalyticsPreferences";

const Tracker = lazy(() => import("./TrackerBootstrap"));
const Welcome = HAS_PUBLIC_HOME ? lazy(() => import("./pages/Welcome")) : null;
const Demo = HAS_PUBLIC_HOME ? lazy(() => import("./demo/DemoBootstrap")) : null;
const Legal = HAS_PUBLIC_HOME ? lazy(() => import("./pages/Legal")) : null;

// Renders the pending-consent banner and a reopenable preferences panel.
// Lives inside AnalyticsProvider so both can call useAnalytics(); rendered
// as a sibling of the routed content so it survives route switches.
function AnalyticsOverlay() {
  const { preferencesOpen, closeAnalyticsPreferences } = useAnalytics();
  return (
    <>
      <ConsentBanner />
      {preferencesOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" role="presentation">
          <div className="w-full max-w-md">
            <AnalyticsPreferences onClose={closeAnalyticsPreferences} />
          </div>
        </div>
      )}
    </>
  );
}

export default function Root() {
  const [pathname, setPathname] = useState(() => window.location.pathname);
  useEffect(() => {
    const updatePath = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', updatePath);
    return () => window.removeEventListener('popstate', updatePath);
  }, []);
  const trackerHost = isTrackerHost(window.location.hostname);
  // Public visitors do not download the tracker or mount private data providers.
  const showDemo = isDemoPath(pathname) && !trackerHost;
  const showWelcome = HAS_PUBLIC_HOME && pathname === "/" && !trackerHost;
  // /terms and /privacy stay public on every host (see legalPage).
  const legal = legalPage(pathname);
  const routeKey = legal ? 'legal' : showDemo ? 'demo' : showWelcome ? 'welcome' : 'tracker';
  // AnalyticsProvider wraps everything, outside the demo/welcome/tracker
  // selection and outside AuthProvider (which lives inside the lazy
  // Tracker/App.jsx tree), so consent survives route switches and never
  // depends on an authenticated session.
  return <AnalyticsProvider>
    <RouteBoundary key={routeKey}><Suspense fallback={<div role="status" className="min-h-screen flex items-center justify-center">Loading Portfyl…</div>}>
      {legal ? <Legal page={legal} /> : showDemo ? <Demo /> : showWelcome ? <Welcome /> : <Tracker />}
    </Suspense></RouteBoundary>
    <AnalyticsOverlay />
  </AnalyticsProvider>;
}
