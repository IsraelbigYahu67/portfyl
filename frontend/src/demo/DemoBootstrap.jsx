import { BrowserRouter } from "react-router-dom";
import { DemoDataProvider } from "./DemoDataContext";
import DemoApp from "./DemoApp";

// Mounted by Root.jsx for cloud-only, non-tracker-host /demo/* routes. Owns
// its own BrowserRouter, isolated from the authenticated tracker's routing
// and providers -- no Firebase, no portfolio API, no shared query client.
export default function DemoBootstrap() {
  return (
    <BrowserRouter>
      <DemoDataProvider>
        <DemoApp />
      </DemoDataProvider>
    </BrowserRouter>
  );
}
