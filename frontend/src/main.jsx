import React from "react";
import ReactDOM from "react-dom/client";
import Root from "./Root";
import { isTrackerHost, landingLanguage } from "./lib/routes";
import { initErrorMonitoring } from "./errorMonitoring";
import "./index.css";

initErrorMonitoring();

const container = document.getElementById("root");
const app = (
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
// Public pages arrive prerendered (scripts/prerender.mjs): adopt that HTML
// instead of replacing it. Anything else ships the empty shell; should a
// prerendered page ever reach a route that renders something different (a
// stale cache, the tracker host), start clean rather than hydrate a mismatch.
const prerendered = container.hasChildNodes()
  && Boolean(landingLanguage(window.location.pathname))
  && !isTrackerHost(window.location.hostname);
if (prerendered) {
  ReactDOM.hydrateRoot(container, app);
} else {
  container.replaceChildren();
  ReactDOM.createRoot(container).render(app);
}
