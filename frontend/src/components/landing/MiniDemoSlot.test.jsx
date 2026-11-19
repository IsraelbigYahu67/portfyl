import { act, render, screen, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { lazy } from "react";
import AnalyticsProvider from "../../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../../analytics/analyticsClient";
import { COPY } from "../../pages/welcomeCopy";
import MiniDemoSlot from "./MiniDemoSlot";

// The real registry would pull the live demo chunks; the slot is tested with a
// light stand-in. `registry` is rebuilt per test through vi.hoisted.
const registry = vi.hoisted(() => ({ current: {} }));
vi.mock("./miniDemoRegistry", () => ({
  get MINI_DEMOS() { return registry.current; },
}));

function LiveStub({ language, copy, onUse }) {
  return (
    <div data-testid="live" lang={language}>
      <button type="button" onClick={onUse}>change</button>
      <span>{copy.allocation.title}</span>
    </div>
  );
}

const copy = COPY.cs.miniDemo;
const pictures = [{ key: "allocation", image: { src: "/landing/allocation.png", width: 1047, height: 365 }, alt: "Obrazek rozlozeni" }];
const slot = (props = {}) => <MiniDemoSlot kind="allocation" language="cs" copy={copy} pictures={pictures} {...props} />;

let observers;
function stubIntersectionObserver() {
  observers = [];
  class FakeObserver {
    constructor(callback, options) { this.callback = callback; this.options = options; this.disconnect = vi.fn(); this.observe = vi.fn(); observers.push(this); }
    unobserve() {}
    takeRecords() { return []; }
  }
  vi.stubGlobal("IntersectionObserver", FakeObserver);
}
const intersect = (observer = observers.at(-1)) => act(() => observer.callback([{ isIntersecting: true }], observer));

beforeEach(() => {
  registry.current = { allocation: LiveStub };
  stubIntersectionObserver();
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); });

// React rethrows a render error to the window in development; the boundary has
// handled it, so keep jsdom from printing it as an uncaught error.
function silenceWindowErrors() {
  const swallow = (event) => event.preventDefault();
  window.addEventListener("error", swallow);
  vi.spyOn(console, "error").mockImplementation(() => {});
  return () => window.removeEventListener("error", swallow);
}

describe("MiniDemoSlot, static render", () => {
  it("prints the badge, the disclaimer and the screenshot, with no digit in its text and no chart", () => {
    const spy = vi.fn();
    vi.stubGlobal("IntersectionObserver", spy);
    const html = renderToString(slot());
    expect(html).toContain(copy.badge);
    expect(html).toContain(copy.disclaimer);
    expect(html).toContain('src="/landing/allocation.png"');
    expect(html).not.toContain('<a ');
    expect(html).not.toMatch(/\/demo/);
    expect(html).toMatch(/^<figure class="welcome-minidemo" data-minidemo="allocation"/);
    expect(html.replace(/<[^>]*>/g, " ").replace(/&#?\w+;/g, "")).not.toMatch(/\d/);
    expect(html).not.toMatch(/recharts/i);
    expect(html).not.toContain('data-testid="live"');
    expect(spy).not.toHaveBeenCalled();
  });

  it("holds the same text when there is no screenshot, and says the example is loading", () => {
    const html = renderToString(slot({ pictures: [] }));
    expect(html).not.toContain("<img");
    expect(html).toContain(copy.loading);
  });

  it("uses no nested figure, so a frame is one balanced block", () => {
    const html = renderToString(slot());
    expect(html.match(/<figure/g)).toHaveLength(1);
    expect(html.match(/<\/figure>/g)).toHaveLength(1);
  });
});

describe("MiniDemoSlot, in the browser", () => {
  it("hydrates the server markup without a mismatch warning", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const container = document.createElement("div");
    document.body.appendChild(container);
    container.innerHTML = renderToString(slot());
    let root;
    await act(async () => { root = hydrateRoot(container, slot()); });
    expect(error).not.toHaveBeenCalled();
    act(() => root.unmount());
    container.remove();
  });

  it("shows the placeholder until the frame is near the screen, then the demo, and then stops observing", async () => {
    const { container } = render(slot());
    expect(screen.queryByTestId("live")).not.toBeInTheDocument();
    expect(container.querySelector("img")).toHaveAttribute("src", "/landing/allocation.png");
    expect(observers).toHaveLength(1);
    expect(observers[0].options).toEqual(expect.objectContaining({ rootMargin: "200px 0px" }));
    expect(observers[0].observe).toHaveBeenCalledWith(container.querySelector("figure"));

    await intersect();
    expect(await screen.findByTestId("live")).toBeInTheDocument();
    expect(observers[0].disconnect).toHaveBeenCalled();
    expect(screen.getByTestId("live")).toHaveAttribute("lang", "cs");
  });

  it("keeps the label while the demo is shown, and never adds a link under it", async () => {
    render(slot());
    await intersect();
    await screen.findByTestId("live");
    expect(screen.getByText(copy.badge)).toBeInTheDocument();
    expect(screen.getByText(copy.disclaimer)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("starts the demo after mount where IntersectionObserver does not exist", async () => {
    vi.unstubAllGlobals();
    delete globalThis.IntersectionObserver;
    render(slot());
    expect(await screen.findByTestId("live")).toBeInTheDocument();
  });

  it("falls back to the placeholder and a notice when the demo throws", async () => {
    const restore = silenceWindowErrors();
    const error = console.error;
    registry.current = { allocation: () => { throw new Error("boom"); } };
    const { container } = render(slot());
    await intersect();
    expect(await screen.findByText(copy.unavailable)).toBeInTheDocument();
    expect(container.querySelector("img")).toHaveAttribute("src", "/landing/allocation.png");
    expect(screen.getByText(copy.badge)).toBeInTheDocument();
    expect(error).toHaveBeenCalled();
    restore();
  });

  it("falls back the same way when the chunk fails to import", async () => {
    const restore = silenceWindowErrors();
    registry.current = { allocation: lazy(() => Promise.reject(new Error("chunk failed"))) };
    render(slot());
    await intersect();
    expect(await screen.findByText(copy.unavailable)).toBeInTheDocument();
    restore();
  });

  it("reports the first change of the demo's controls once, after consent", async () => {
    const adapter = createMemoryAdapter();
    render(
      <AnalyticsProvider initialConsent="accepted" adapterFactory={() => adapter}>
        {slot()}
      </AnalyticsProvider>
    );
    await intersect();
    const button = await screen.findByRole("button", { name: "change" });
    await waitFor(() => expect(adapter.events).toEqual([])); // adapter ready, nothing sent yet
    act(() => button.click());
    act(() => button.click());
    await waitFor(() => expect(adapter.events).toEqual([["landing_minidemo_used", { minidemo: "allocation", language: "cs" }]]));
  });

  it("sends nothing without consent", async () => {
    const adapter = createMemoryAdapter();
    render(
      <AnalyticsProvider initialConsent="pending" adapterFactory={() => adapter}>
        {slot()}
      </AnalyticsProvider>
    );
    await intersect();
    act(() => screen.getByRole("button", { name: "change" }).click());
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(adapter.events).toEqual([]);
  });
});
