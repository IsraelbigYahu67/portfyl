import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement ResizeObserver, but recharts' <ResponsiveContainer>
// requires it (used in a useEffect to size the chart). Stub it so components
// that render recharts charts don't crash during tests.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
