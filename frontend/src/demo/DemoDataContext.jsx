import { Component, createContext, useContext, useMemo } from "react";
import { demoPortfolio as defaultDemoPortfolio } from "./demoPortfolio";
import { assertDemoPortfolio } from "./validateDemoPortfolio";
import { DEMO_COPY, getDemoLanguage } from "./demoCopy";

const DemoDataContext = createContext(null);

function DemoUnavailable() {
  const t = DEMO_COPY[getDemoLanguage()];
  return (
    <div className="min-h-screen flex items-center justify-center text-center px-4">
      <div>
        <h1 className="text-xl font-bold">{t.unavailableTitle}</h1>
        <p className="financial-data text-muted mt-2">{t.unavailableHint}</p>
        <a href="/" className="btn-primary inline-block mt-4">{t.backHome}</a>
      </div>
    </div>
  );
}

// Catches a validation failure thrown during DemoDataProviderInner's render
// (a corrupted or hand-crafted invalid `value` prop) so a broken fixture
// shows the branded unavailable state instead of a blank screen.
class DemoUnavailableBoundary extends Component {
  state = { hasError: false };
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error) {
    // eslint-disable-next-line no-console
    console.error("Demo data unavailable:", error);
  }
  render() {
    return this.state.hasError ? <DemoUnavailable /> : this.props.children;
  }
}

function DemoDataProviderInner({ children, value }) {
  const validated = useMemo(() => assertDemoPortfolio(value), [value]);
  return <DemoDataContext.Provider value={validated}>{children}</DemoDataContext.Provider>;
}

export function DemoDataProvider({ children, value = defaultDemoPortfolio }) {
  return (
    <DemoUnavailableBoundary>
      <DemoDataProviderInner value={value}>{children}</DemoDataProviderInner>
    </DemoUnavailableBoundary>
  );
}

export function useDemoData() {
  const ctx = useContext(DemoDataContext);
  if (ctx == null) {
    throw new Error("useDemoData must be used inside DemoDataProvider");
  }
  return ctx;
}
