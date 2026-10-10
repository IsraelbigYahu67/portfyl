import { readFile } from "node:fs/promises";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Welcome from "./Welcome";
import { COPY, LANGUAGES, LANGUAGE_KEY } from "./welcomeCopy";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";
import { sourcePath } from "../test/sourcePath";

function renderWelcome({ initialConsent = "pending" } = {}) {
  const adapter = createMemoryAdapter();
  const result = render(
    <AnalyticsProvider initialConsent={initialConsent} adapterFactory={() => adapter}>
      <Welcome />
    </AnalyticsProvider>
  );
  return { ...result, adapter };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

it("keeps every declared font-size in Welcome.css at or above the 12px readability floor", async () => {
  const assetUrl = new URL("./Welcome.css", import.meta.url);
  const cssPath = sourcePath(assetUrl);
  const css = await readFile(cssPath, "utf-8");
  const subFloor = [...css.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].filter(([, n]) => Number(n) < 12);
  expect(subFloor.map((m) => m[0])).toEqual([]);
});

function chooseCzech() {
  fireEvent.click(screen.getByRole("button", { name: /Pokračovat česky/ }));
}

it("keeps navigation links on-page while exposing the public demo as a normal link", () => {
  renderWelcome();
  chooseCzech();
  for (const link of screen.getAllByRole("link")) {
    const href = link.getAttribute("href");
    if (href === "/demo") continue;
    expect(href).toMatch(/^#/);
    expect(document.getElementById(href.slice(1))).not.toBeNull();
  }
  const demoLinks = screen.getAllByRole("link", { name: COPY.cs.demoCta });
  expect(demoLinks).toHaveLength(2);
  demoLinks.forEach((link) => expect(link).toHaveAttribute("href", "/demo"));
});

it("switches between portfolio and stock previews", () => {
  renderWelcome();
  chooseCzech();
  fireEvent.click(screen.getByRole("button", { name: "Detail akcie" }));
  expect(screen.getByRole("button", { name: "Detail akcie" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("img", { name: /Screenshot detailu akcie/ })).toHaveAttribute("src", "/landing/stock-live-20260911.png");
  fireEvent.click(screen.getByRole("button", { name: "Složení portfolia" }));
  expect(screen.getByRole("img", { name: /Screenshot Portfylu s rozložením/ })).toHaveAttribute("src", "/landing/allocation-live-20260911.png");
  fireEvent.click(screen.getByRole("button", { name: "Přehled portfolia" }));
  expect(screen.getByRole("img", { name: /Screenshot přehledu hodnoty/ })).toHaveAttribute("src", "/landing/dashboard-live-20260911.png");
  fireEvent.click(screen.getByRole("button", { name: "Výkonnost" }));
  expect(screen.getByRole("img", { name: /Screenshot grafu výkonnosti/ })).toHaveAttribute("src", "/landing/performance-live-20260911.png");
});

it("asks new visitors to choose one of three languages before showing the landing page", () => {
  renderWelcome();
  expect(screen.getAllByRole("button")).toHaveLength(3);
  for (const language of LANGUAGES) expect(screen.getByRole("button", { name: new RegExp(language.action) })).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

it.each(LANGUAGES)("shows the full $name page and remembers the selection", ({ code, action }) => {
  const { unmount } = renderWelcome();
  fireEvent.click(screen.getByRole("button", { name: new RegExp(action) }));
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(COPY[code].heading[0]);
  expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
  expect(screen.getByText(COPY[code].questions[0][0])).toBeInTheDocument();
  expect(screen.getByText(COPY[code].footer)).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: COPY[code].demoCta })).toHaveLength(2);
  expect(document.documentElement.lang).toBe(code);
  expect(document.title).toBe(COPY[code].title);
  expect(localStorage.getItem(LANGUAGE_KEY)).toBe(code);
  unmount();
  renderWelcome();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(COPY[code].heading[0]);
});

it("lets a returning visitor change language from the header", () => {
  localStorage.setItem(LANGUAGE_KEY, "en");
  renderWelcome();
  fireEvent.click(screen.getByRole("button", { name: "Deutsch" }));
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Deine Investments.");
  expect(screen.getByRole("button", { name: "Deutsch" })).toHaveAttribute("aria-pressed", "true");
  expect(localStorage.getItem(LANGUAGE_KEY)).toBe("de");
});

it("asks again when the stored language is unsupported", () => {
  localStorage.setItem(LANGUAGE_KEY, "fr");
  renderWelcome();
  expect(screen.getByRole("button", { name: /Continue in English/ })).toBeInTheDocument();
});

it("still works if browser storage is blocked", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Blocked"); });
  renderWelcome();
  chooseCzech();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Vaše investice.");
});

it("captures landing_viewed once analytics is ready, never before", async () => {
  const { adapter } = renderWelcome({ initialConsent: "accepted" });
  await waitFor(() => expect(adapter.events).toHaveLength(1));
  expect(adapter.events[0]).toEqual([
    "landing_viewed",
    { language: "en", referrer_class: "direct", utm_source: "none", utm_medium: "none", utm_campaign: "none" },
  ]);
});

it("captures demo_started with entry_point=landing_hero on an unmodified hero CTA click, without a full navigation", async () => {
  const { adapter } = renderWelcome({ initialConsent: "accepted" });
  await waitFor(() => expect(adapter.events).toHaveLength(1)); // landing_viewed
  chooseCzech();

  const heroCta = screen.getAllByRole("link", { name: COPY.cs.demoCta })[0];
  fireEvent.click(heroCta, { button: 0 });

  await waitFor(() =>
    expect(adapter.events).toContainEqual(["demo_started", { language: "cs", entry_point: "landing_hero" }])
  );
  expect(window.location.pathname).toBe("/demo");
});
