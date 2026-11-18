import { readFile } from "node:fs/promises";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import Welcome, { suggestedLanguage } from "./Welcome";
import { COPY, LANGUAGES, LANGUAGE_KEY } from "./welcomeCopy";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";
import { sourcePath } from "../test/sourcePath";
import { APP_ORIGIN, registerUrl } from "../lib/signupIntent";
import { PLAN_PRICES_CENTS, formatPlanPrice } from "../lib/planPrices";
import { LANDING_IMAGES } from "../components/landing/landingImages";

function renderWelcome({ initialConsent = "pending", language = "cs", signupOpen = false } = {}) {
  const adapter = createMemoryAdapter();
  const result = render(
    <AnalyticsProvider initialConsent={initialConsent} adapterFactory={() => adapter}>
      <Welcome language={language} signupOpen={signupOpen} />
    </AnalyticsProvider>
  );
  return { ...result, adapter };
}

// The mini demos load when their frame nears the screen; a crossing never
// happens in these tests, so every frame stays on its placeholder.
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} takeRecords() { return []; } });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("keeps every declared font-size in Welcome.css at or above the 12px readability floor", async () => {
  const assetUrl = new URL("./Welcome.css", import.meta.url);
  const cssPath = sourcePath(assetUrl);
  const css = await readFile(cssPath, "utf-8");
  const subFloor = [...css.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].filter(([, n]) => Number(n) < 12);
  expect(subFloor.map((m) => m[0])).toEqual([]);
});

it("holds no hex color in Welcome.css: colors come from the Clay tokens", async () => {
  const css = await readFile(sourcePath(new URL("./Welcome.css", import.meta.url)), "utf-8");
  expect(css.match(/#[0-9a-fA-F]{3,8}\b/g)).toBeNull();
});

it("does not let the landing's heading, paragraph and link rules reach into a mini demo", async () => {
  const css = await readFile(sourcePath(new URL("./Welcome.css", import.meta.url)), "utf-8");
  const guard = ":where(:not(.welcome-minidemo-app *))";
  for (const selector of [".welcome :is(h1,h2,h3,h4)", ".welcome p", ":where(.welcome) a"]) {
    expect(css, selector).toContain(`${selector}${guard}`);
  }
  // Any other rule that styles a bare heading or paragraph of .welcome must carry the guard too.
  const bare = css.split(/\r?\n/).filter((line) => /^(\.welcome|:where\(\.welcome\)) (:is\(h1|h[1-4]\b|p\b|a\b)/.test(line));
  expect(bare.length).toBeGreaterThanOrEqual(6);
  for (const line of bare) expect(line, line).toContain(guard);
});

const IN_PAGE_TARGETS = ["#funkce", "#brokeri", "#cenik", "#otazky"];

describe.each(LANGUAGES)("$name landing page", ({ code }) => {
  const copy = COPY[code];

  it("has one h1 and a header navigation with exactly four in-page links whose targets exist", () => {
    renderWelcome({ language: code });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const nav = screen.getByRole("navigation", { name: copy.navigation });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(IN_PAGE_TARGETS);
    expect(links.map((link) => link.textContent)).toEqual(copy.nav);
    for (const target of IN_PAGE_TARGETS) expect(document.getElementById(target.slice(1))).not.toBeNull();
  });

  it("links Log in to the app's login page, in the header and in the phone menu", () => {
    renderWelcome({ language: code });
    const logins = screen.getAllByRole("link", { name: copy.login });
    expect(logins.length).toBeGreaterThanOrEqual(2);
    logins.forEach((link) => expect(link).toHaveAttribute("href", `${APP_ORIGIN}/login`));
  });

  it("keeps the phone menu in step with the header navigation", () => {
    const { container } = renderWelcome({ language: code });
    const menu = container.querySelector("details.welcome-menu");
    expect(menu).not.toBeNull();
    const hrefs = within(menu).getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(hrefs.slice(0, 4)).toEqual(IN_PAGE_TARGETS);
  });

  it("while signup is closed: demo is the primary action, a beta line shows and no register link exists", () => {
    const { container } = renderWelcome({ language: code, signupOpen: false });
    expect(container.querySelector('a[href*="/register"]')).toBeNull();
    expect(screen.getAllByRole("link", { name: copy.demoCta })[0]).toHaveAttribute("href", "/demo");
    expect(screen.getByText(copy.status[0])).toBeInTheDocument();
    expect(container.textContent).not.toContain(copy.trialCta);
  });

  it("while signup is open: the primary action registers with the trial and the demo is secondary", () => {
    renderWelcome({ language: code, signupOpen: true });
    const primary = screen.getByRole("link", { name: copy.trialCta });
    expect(primary).toHaveAttribute("href", registerUrl({ source: "landing_hero", lang: code }));
    expect(primary.textContent).toContain("10");
    expect(screen.getByText(copy.trialNote)).toBeInTheDocument();
    expect(screen.queryByText(copy.status[0])).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: copy.demoLink })[0]).toHaveAttribute("href", "/demo");
  });

  it("shows three plans with prices from the shared constant", () => {
    renderWelcome({ language: code });
    const pricing = document.getElementById("cenik");
    expect(within(pricing).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Free", "Investor", "Pro"]);
    for (const cents of [0, PLAN_PRICES_CENTS.investor, PLAN_PRICES_CENTS.pro]) {
      expect([...pricing.querySelectorAll(".welcome-price")].map((price) => price.textContent)).toContainEqual(expect.stringContaining(formatPlanPrice(cents, code)));
    }
  });

  it("is flat: none of the old decorative classes remain", () => {
    const { container } = renderWelcome({ language: code, signupOpen: true });
    expect(container.querySelector(".welcome-eyebrow, .welcome-orbit, .welcome-float")).toBeNull();
  });

  it("never names the Tax Report, Screener, Options, Polymarket or the removed US brokers", () => {
    expect(JSON.stringify(copy)).not.toMatch(/Tax|Daň|Steuer|Screener|Options|Polymarket|Schwab|Fidelity/);
  });

  it("lists every supported broker in the two groups, with no promises of more", () => {
    renderWelcome({ language: code });
    const section = document.getElementById("brokeri");
    for (const name of ["Trading 212", "Interactive Brokers", "eToro", "Degiro", "XTB"]) {
      expect(section).toHaveTextContent(name);
    }
    expect(section).toHaveTextContent(copy.brokers.api);
    expect(section).toHaveTextContent(copy.brokers.file);
    expect(section.textContent).not.toMatch(/Schwab|Fidelity|brzy|soon|bald/i);
    expect(screen.getByRole("searchbox")).toBeInTheDocument();
    expect(screen.getByText(copy.brokerCheck.title)).toBeInTheDocument();
  });

  it("renders the page straight from its URL, with legal links, footer and no language gate", () => {
    renderWelcome({ language: code });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(copy.heading);
    expect(screen.getByText(copy.questions[0].q)).toBeInTheDocument();
    expect(screen.getByText(copy.footer.tagline)).toBeInTheDocument();
    const legal = screen.getByRole("navigation", { name: copy.legalNavigation });
    expect(within(legal).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      `/terms?lang=${copy.legalLanguage}`, `/privacy?lang=${copy.legalLanguage}`,
    ]);
    expect(document.documentElement.lang).toBe(code);
    expect(document.title).toBe(copy.title);
    // Landing on a URL is not a choice: nothing is saved until the visitor acts.
    expect(localStorage.getItem(LANGUAGE_KEY)).toBeNull();
  });

  it("asks what happens after the trial only while signup is open, and never says invite-only then", () => {
    const closed = renderWelcome({ language: code, signupOpen: false });
    const closedCount = closed.container.querySelectorAll(".welcome-faq details").length;
    expect(closed.container.textContent).toContain(copy.questions[0].a);
    closed.unmount();
    const open = renderWelcome({ language: code, signupOpen: true });
    expect(open.container.querySelectorAll(".welcome-faq details").length).toBe(closedCount + 1);
    expect(open.container.textContent).not.toContain(copy.questions[0].a);
    expect(open.container.textContent).toContain(copy.questions[0].aOpen);
  });
});

it("shows the hero and the two feature screenshots, and no figure for pictures that are not shot yet", () => {
  const { container } = renderWelcome({ language: "en" });
  const hero = container.querySelector(".welcome-hero img");
  expect(hero).toHaveAttribute("src", LANDING_IMAGES.hero.src);
  expect(hero).toHaveAttribute("width", String(LANDING_IMAGES.hero.width));
  const featureImages = [...container.querySelectorAll("#funkce img")].map((img) => img.getAttribute("src"));
  expect(featureImages).toEqual([LANDING_IMAGES.allocation.src, LANDING_IMAGES.stock.src]);
  expect(container.querySelectorAll("#funkce h3")).toHaveLength(COPY.en.features.length);
  expect(container.querySelectorAll(".welcome-steps img")).toHaveLength(0);
});

it("keeps in-page navigation on the page and every other link a normal one", () => {
  renderWelcome({ language: "cs", signupOpen: true });
  const origin = APP_ORIGIN.replace(/[.]/g, "\\.");
  const allowed = [/^#/, /^\/demo$/, /^\/demo\/(allocation|analytics|dividends|stock\/[A-Z]+)$/, /^\/terms\?lang=cs$/, /^\/privacy\?lang=cs$/, /^\/(en\/|de\/)?$/, /^mailto:support@portfyl\.com$/, new RegExp(`^${origin}/(login|register)`)];
  for (const link of screen.getAllByRole("link")) {
    const href = link.getAttribute("href");
    expect(allowed.some((pattern) => pattern.test(href)), href).toBe(true);
  }
});

it("offers the other languages as crawlable links and remembers an explicit switch", () => {
  renderWelcome({ language: "en" });
  const switcher = screen.getByRole("group", { name: COPY.en.language });
  expect(within(switcher).getAllByRole("link").map((link) => [link.getAttribute("href"), link.getAttribute("hreflang")])).toEqual([
    ["/", "cs"], ["/en/", "en"], ["/de/", "de"],
  ]);
  expect(within(switcher).getByRole("link", { name: "EN" })).toHaveAttribute("aria-current", "page");
  expect(within(switcher).getByRole("link", { name: "DE" })).not.toHaveAttribute("aria-current");
  fireEvent.click(within(switcher).getByRole("link", { name: "DE" }));
  expect(localStorage.getItem(LANGUAGE_KEY)).toBe("de");
});

it("still works if browser storage is blocked", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Blocked"); });
  renderWelcome({ language: "cs" });
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(COPY.cs.heading);
  fireEvent.click(within(screen.getByRole("group", { name: COPY.cs.language })).getByRole("link", { name: "EN" }));
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

it("captures demo_started with entry_point=landing_closing from the closing call to action", async () => {
  const { adapter } = renderWelcome({ initialConsent: "accepted", language: "en" });
  await waitFor(() => expect(adapter.events).toHaveLength(1));
  const links = screen.getAllByRole("link", { name: COPY.en.demoCta });
  expect(links).toHaveLength(2);
  fireEvent.click(links[1], { button: 0 });
  await waitFor(() =>
    expect(adapter.events).toContainEqual(["demo_started", { language: "en", entry_point: "landing_closing" }])
  );
});

const shapeOf = (value) => (value && typeof value === "object"
  ? Object.fromEntries(Object.entries(value).map(([key, inner]) => [key, shapeOf(inner)]))
  : typeof value);

describe("mini demo copy", () => {
  const kinds = ["allocation", "stock", "performance", "dividends", "portfolios"];

  it("has the same keys in all three languages, and every text is filled", () => {
    for (const code of ["en", "de"]) expect(shapeOf(COPY[code].miniDemo), code).toEqual(shapeOf(COPY.cs.miniDemo));
    for (const { code } of LANGUAGES) {
      const empty = [];
      (function walk(value, path) {
        if (value && typeof value === "object") Object.entries(value).forEach(([key, inner]) => walk(inner, `${path}.${key}`));
        else if (typeof value !== "string" || !value.trim()) empty.push(path);
      })(COPY[code].miniDemo, `${code}.miniDemo`);
      expect(empty).toEqual([]);
    }
  });

  it("gives the five features their demo in the planned order", () => {
    for (const { code } of LANGUAGES) expect(COPY[code].features.map((feature) => feature.demo), code).toEqual(kinds);
  });

  it("keeps the texts that reach the prerendered HTML free of digits", () => {
    for (const { code } of LANGUAGES) {
      const { badge, disclaimer, loading, unavailable, openDemo } = COPY[code].miniDemo;
      for (const text of [badge, disclaimer, loading, unavailable, openDemo]) expect(text, `${code}: ${text}`).not.toMatch(/\d/);
    }
  });

  it("names the sample data and the made-up numbers in each language", () => {
    expect(COPY.cs.miniDemo.badge).toBe("Ukázkové portfolio");
    expect(COPY.cs.miniDemo.disclaimer).toBe("Vymyšlená čísla, ne skutečné výnosy.");
    expect(COPY.en.miniDemo.badge).toBe("Sample portfolio");
    expect(COPY.en.miniDemo.disclaimer).toBe("Made-up numbers, not real returns.");
    expect(COPY.de.miniDemo.badge).toBe("Beispielportfolio");
    expect(COPY.de.miniDemo.disclaimer).toBe("Erfundene Zahlen, keine echten Renditen.");
  });

  it.each(LANGUAGES)("renders five labeled frames in the page for $name", ({ code }) => {
    const { container } = renderWelcome({ language: code });
    const frames = [...container.querySelectorAll("#funkce figure.welcome-minidemo")];
    expect(frames.map((frame) => frame.dataset.minidemo)).toEqual(kinds);
    for (const frame of frames) {
      expect(frame).toHaveTextContent(COPY[code].miniDemo.badge);
      expect(frame).toHaveTextContent(COPY[code].miniDemo.disclaimer);
    }
    expect(container.querySelector(".welcome-more")).toBeNull();
  });
});
