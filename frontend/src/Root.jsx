import { lazy, Suspense } from "react";
import { Navigate, useLocation } from "react-router-dom";
import Welcome from "./pages/Welcome";
import { HAS_PUBLIC_HOME, TRACKER_HOME } from "./lib/routes";

const Tracker = lazy(() => import("./App"));

export default function Root() {
  const { pathname } = useLocation();
  const trackerHost = window.location.hostname.toLowerCase() === "app.portfyl.com";
  // Public visitors do not download the tracker or mount private data providers.
  if (HAS_PUBLIC_HOME && pathname === "/" && !trackerHost) return <Welcome />;
  if (HAS_PUBLIC_HOME && pathname === "/" && trackerHost) {
    return <Navigate to={TRACKER_HOME} replace />;
  }
  return <Suspense fallback={<div role="status" className="min-h-screen flex items-center justify-center">Loading Portfyl…</div>}><Tracker /></Suspense>;
}
