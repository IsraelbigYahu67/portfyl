import { Suspense, lazy } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import DemoShell from "./DemoShell";
import { DEMO_COPY, getDemoLanguage } from "./demoCopy";
import { useDemoAnalytics } from "../analytics/useDemoAnalytics";

const DemoOverview = lazy(() => import("./pages/DemoOverview"));
const DemoAllocation = lazy(() => import("./pages/DemoAllocation"));
const DemoAnalytics = lazy(() => import("./pages/DemoAnalytics"));
const DemoDividends = lazy(() => import("./pages/DemoDividends"));
const DemoStock = lazy(() => import("./pages/DemoStock"));

function DemoNotFound() {
  const t = DEMO_COPY[getDemoLanguage()];
  return (
    <div className="text-center py-16">
      <h1 className="text-xl font-bold">{t.notFoundTitle}</h1>
      <p className="financial-data text-muted mt-2">{t.notFoundHint}</p>
      <a href="/demo" className="btn-primary inline-block mt-4">{t.backToDemo}</a>
    </div>
  );
}

function routeToPage(pathname) {
  if (pathname === "/demo") return "overview";
  if (pathname === "/demo/allocation") return "allocation";
  if (pathname === "/demo/analytics") return "analytics";
  if (pathname === "/demo/dividends") return "dividends";
  if (pathname.startsWith("/demo/stock/")) return "stock";
  return null;
}

// Route tree for the cloud-only public demo. Unknown /demo/* paths render
// the branded not-found state above, never the authenticated tracker or a
// blank page.
export default function DemoApp() {
  const location = useLocation();
  const page = routeToPage(location.pathname);
  const symbol = page === "stock"
    ? decodeURIComponent(location.pathname.slice("/demo/stock/".length)).trim().toUpperCase()
    : undefined;
  useDemoAnalytics({ page, symbol, language: getDemoLanguage() });

  return (
    <DemoShell>
      <Suspense fallback={<div role="status">Loading…</div>}>
        <Routes>
          <Route path="/demo" element={<DemoOverview />} />
          <Route path="/demo/allocation" element={<DemoAllocation />} />
          <Route path="/demo/analytics" element={<DemoAnalytics />} />
          <Route path="/demo/dividends" element={<DemoDividends />} />
          <Route path="/demo/stock/:ticker" element={<DemoStock />} />
          <Route path="/demo/*" element={<DemoNotFound />} />
        </Routes>
      </Suspense>
    </DemoShell>
  );
}
