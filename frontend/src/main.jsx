import React from "react";
import ReactDOM from "react-dom/client";
import Root from "./Root";
import { initErrorMonitoring } from "./errorMonitoring";
import "./index.css";

initErrorMonitoring();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
