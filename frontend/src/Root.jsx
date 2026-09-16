import { lazy, Suspense, useEffect, useState } from "react";
import { HAS_PUBLIC_HOME } from "./lib/routes";
import RouteBoundary from "./components/layout/RouteBoundary";

const Tracker = lazy(() => import("./TrackerBootstrap"));
const Welcome = HAS_PUBLIC_HOME ? lazy(() => import("./pages/Welcome")) : null;

export default function Root() {
  const [pathname, setPathname] = useState(() => window.location.pathname);
  useEffect(() => {
    const updatePath = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', updatePath);
    return () => window.removeEventListener('popstate', updatePath);
  }, []);
  const trackerHost = window.location.hostname.toLowerCase() === "app.portfyl.com";
  // Public visitors do not download the tracker or mount private data providers.
  return <RouteBoundary key={HAS_PUBLIC_HOME && pathname === "/" && !trackerHost ? 'welcome' : 'tracker'}><Suspense fallback={<div role="status" className="min-h-screen flex items-center justify-center">Loading Portfyl…</div>}>
    {HAS_PUBLIC_HOME && pathname === "/" && !trackerHost ? <Welcome /> : <Tracker />}
  </Suspense></RouteBoundary>;
}
