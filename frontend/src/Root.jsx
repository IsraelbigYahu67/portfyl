import { lazy, Suspense, useEffect, useState } from "react";
import { HAS_PUBLIC_HOME, isDemoPath, isTrackerHost } from "./lib/routes";
import RouteBoundary from "./components/layout/RouteBoundary";

const Tracker = lazy(() => import("./TrackerBootstrap"));
const Welcome = HAS_PUBLIC_HOME ? lazy(() => import("./pages/Welcome")) : null;
const Demo = HAS_PUBLIC_HOME ? lazy(() => import("./demo/DemoBootstrap")) : null;

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
  const routeKey = showDemo ? 'demo' : showWelcome ? 'welcome' : 'tracker';
  return <RouteBoundary key={routeKey}><Suspense fallback={<div role="status" className="min-h-screen flex items-center justify-center">Loading Portfyl…</div>}>
    {showDemo ? <Demo /> : showWelcome ? <Welcome /> : <Tracker />}
  </Suspense></RouteBoundary>;
}
