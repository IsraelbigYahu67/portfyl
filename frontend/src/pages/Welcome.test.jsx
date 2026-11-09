import { readFile } from "node:fs/promises";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import Welcome, { suggestedLanguage } from "./Welcome";
import { COPY, LANGUAGES, LANGUAGE_KEY } from "./welcomeCopy";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";
import { sourcePath } from "../test/sourcePath";

function renderWelcome({ initialConsent = "pending", language = "cs" } = {}) {
  const adapter = createMemoryAdapter();
  const result = render(
    <AnalyticsProvider initialConsent={initialConsent} adapterFactory={() => adapter}>
      <Welcome language={language} />
    </AnalyticsProvider>
  );
  return { ...result, adapter };
}

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });
afterEach(() => vi.restoreAllMocks());

it("keeps every declared font-size in Welcome.css at or above the 12px readability floor", async () => {
  const assetUrl = new URL("./Welcome.css", import.meta.url);
  const cssPath = sourcePath(assetUrl);
  const css = await readFile(cssPath, "utf-8");
  const subFloor = [...css.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].filter(([, n]) => Number(n) < 12);
  expect(subFloor.map((m) => m[0])).toEqual([]);
});

const LANGUAGE_HREFS = ["/", "/en/", "/de/"];

it("keeps navigation links on-page while exposing the demo, legal pages and language URLs as normal links", () => {
  renderWelcome({ language: "cs" });
  for (const link of screen.getAllByRole("link")) {
    const href = link.getAttribute("href");
    if (href === "/demo" || href === "/terms?lang=cs" || href === "/privacy?lang=cs" || LANGUAGE_HREFS.includes(href)) continue;
    expect(href).toMatch(/^#/);
    expect(document.getElementById(href.slice(1))).not.toBeNull();
  }
  const demoLinks = screen.getAllByRole("link", { name: COPY.cs.demoCta });
  expect(demoLinks).toHaveLength(2);
  demoLinks.forEach((link) => expect(link).toHaveAttribute("href", "/demo"));
});

it("switches between portfolio and stock previews", () => {
  renderWelcome({ language: "cs" });
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

it.each(LANGUAGES)("renders the full $name page straight from its URL, with no language gate", ({ code }) => {
  renderWelcome({ language: code });
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(COPY[code].heading[0]);
  expect(screen.getByText(COPY[code].questions[0][0])).toBeInTheDocument();
  expect(screen.getByText(COPY[code].footer)).toBeInTheDocument();
  const legal = screen.getByRole("navigation", { name: COPY[code].legalNavigation });
  expect(within(legal).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
    `/terms?lang=${COPY[code].legalLanguage}`, `/privacy?lang=${COPY[code].legalLanguage}`,
  ]);
  expect(screen.getAllByRole("link", { name: COPY[code].demoCta })).toHaveLength(2);
  expect(document.documentElement.lang).toBe(code);
  expect(document.title).toBe(COPY[code].title);
  // Landing on a URL is not a choice: nothing is saved until the visitor acts.
  expect(localStorage.getItem(LANGUAGE_KEY)).toBeNull();
});

it("offers the other languages as crawlable links and remembers an explicit switch", () => {
  renderWelcome({ language: "en" });
  const switcher = screen.getByRole("group", { name: COPY.en.language });
  expect(within(switcher).getAllByRole("link").map((link) => [link.getAttribute("href"), link.getAttribute("hreflang")])).toEqual([
    ["/", "cs"], ["/en/", "en"], ["/de/", "de"],
  ]);
  expect(within(switcher).getByRole("link", { name: "English" })).toHaveAttribute("aria-current", "page");
  expect(within(switcher).getByRole("link", { name: "Deutsch" })).not.toHaveAttribute("aria-current");
  fireEvent.click(within(switcher).getByRole("link", { name: "Deutsch" }));
  expect(localStorage.getItem(LANGUAGE_KEY)).toBe("de");
});

it("still works if browser storage is blocked", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Blocked"); });
  renderWelcome({ language: "cs" });
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Vaše investice.");
  fireEvent.click(screen.getByRole("link", { name: "English" }));
});

describe("suggestedLanguage", () => {
  it.each([
    ["cs", { saved: null, browserLanguages: ["de-DE"] }, "de"],
    ["cs", { saved: null, browserLanguages: ["sk-SK"] }, null],
    ["cs", { saved: null, browserLanguages: ["fr-FR"] }, "en"],
    ["en", { saved: null, browserLanguages: ["en-US"] }, null],
    ["de", { saved: "cs", browserLanguages: ["de-DE"] }, "cs"],
    ["cs", { saved: "cs", browserLanguages: ["en-US"] }, null],
    ["cs", { saved: null, browserLanguages: [] }, null],
  ])("on a %s page with %o suggests %s", (page, options, expected) => {
    expect(suggestedLanguage(page, options)).toBe(expected);
  });
});

it("offers a German visitor the German page from the Czech root, and stays dismissed", async () => {
  vi.spyOn(window.navigator, "languages", "get").mockReturnValue(["de-DE", "de"]);
  const { unmount } = renderWelcome({ language: "cs" });
  const offer = await screen.findByRole("complementary", { name: "Diese Seite gibt es auch auf Deutsch." });
  expect(within(offer).getByRole("link", { name: /Auf Deutsch fortfahren/ })).toHaveAttribute("href", "/de/");
  fireEvent.click(within(offer).getByRole("button", { name: "Schließen" }));
  expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  unmount();
  renderWelcome({ language: "cs" });
  await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument());
  expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
});

it("captures landing_viewed once analytics is ready, never before, in the page's language", async () => {
  const { adapter } = renderWelcome({ initialConsent: "accepted", language: "en" });
  await waitFor(() => expect(adapter.events).toHaveLength(1));
  expect(adapter.events[0]).toEqual([
    "landing_viewed",
    { language: "en", referrer_class: "direct", utm_source: "none", utm_medium: "none", utm_campaign: "none" },
  ]);
});

it("captures demo_started with entry_point=landing_hero on an unmodified hero CTA click, without a full navigation", async () => {
  const { adapter } = renderWelcome({ initialConsent: "accepted", language: "cs" });
  await waitFor(() => expect(adapter.events).toHaveLength(1)); // landing_viewed

  const heroCta = screen.getAllByRole("link", { name: COPY.cs.demoCta })[0];
  fireEvent.click(heroCta, { button: 0 });

  await waitFor(() =>
    expect(adapter.events).toContainEqual(["demo_started", { language: "cs", entry_point: "landing_hero" }])
  );
  expect(window.location.pathname).toBe("/demo");
  // The demo reads the saved language, so entering it keeps the page's language.
  expect(localStorage.getItem(LANGUAGE_KEY)).toBe("cs");
});
