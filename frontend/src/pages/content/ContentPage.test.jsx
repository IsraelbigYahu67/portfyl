import { readFile } from "node:fs/promises";
import { render, screen, within } from "@testing-library/react";
import ContentPage, { formatUpdated } from "./ContentPage";
import AnalyticsProvider from "../../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../../analytics/analyticsClient";
import { COPY } from "../welcomeCopy";
import { sourcePath } from "../../test/sourcePath";
import { normalizeContentPages } from "../../seo/contentPages";
import { FIXTURE_PAGES, fixtureCs, fixtureEn, fixtureSolo } from "../../test/contentFixtures";

const pages = normalizeContentPages(FIXTURE_PAGES);
const pageFor = (fixture) => pages.find((page) => page.path === fixture.path);

function renderPage(fixture, props = {}) {
  const adapter = createMemoryAdapter();
  return render(
    <AnalyticsProvider initialConsent="pending" adapterFactory={() => adapter}>
      <ContentPage page={pageFor(fixture)} signupOpen={false} {...props}><p>Body text.</p></ContentPage>
    </AnalyticsProvider>,
  );
}

beforeEach(() => { localStorage.clear(); });

it("renders exactly one h1, the body, the updated date, the note and the call to action", () => {
  renderPage(fixtureCs);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(fixtureCs.title);
  expect(screen.getByText("Body text.")).toBeInTheDocument();
  expect(screen.getByText("20. 11. 2026").closest("time")).toHaveAttribute("datetime", "2026-11-20");
  expect(screen.getByRole("note")).toHaveTextContent("Nejde o investiční poradenství.");
  const cta = screen.getByRole("region", { name: "Vyzkoušejte Portfyl" });
  expect(within(cta).getByRole("link", { name: COPY.cs.examplesCta })).toHaveAttribute("href", "/#funkce");
});

it("uses the heading when it differs from the title, and can drop the advice note", () => {
  renderPage(fixtureSolo);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Samostatná stránka");
  expect(screen.queryByRole("note")).not.toBeInTheDocument();
});

it("links back to the landing page of its language and carries the legal links in the footer", () => {
  renderPage(fixtureEn);
  expect(screen.getByRole("link", { name: /Back to home/ })).toHaveAttribute("href", "/en/");
  const legal = screen.getByRole("navigation", { name: COPY.en.legalNavigation });
  expect(within(legal).getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms?lang=en");
  expect(within(legal).getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy?lang=en");
  expect(document.querySelector("main")).toHaveAttribute("lang", "en");
});

it("sends the language links to sibling versions where they exist and to the landing otherwise", () => {
  renderPage(fixtureCs, { languagePaths: { cs: fixtureCs.path, en: fixtureEn.path, de: "/de/" } });
  const links = screen.getByRole("group", { name: COPY.cs.language });
  expect(links.querySelector('a[hreflang="cs"]')).toHaveAttribute("href", fixtureCs.path);
  expect(links.querySelector('a[hreflang="cs"]')).toHaveAttribute("aria-current", "page");
  expect(links.querySelector('a[hreflang="en"]')).toHaveAttribute("href", fixtureEn.path);
  expect(links.querySelector('a[hreflang="de"]')).toHaveAttribute("href", "/de/");
});

it("offers the trial instead of the examples when sign-up is open", () => {
  renderPage(fixtureCs, { signupOpen: true });
  const cta = screen.getByRole("region", { name: "Vyzkoušejte Portfyl" });
  expect(within(cta).getByRole("link", { name: COPY.cs.trialCtaShort }).getAttribute("href")).toMatch(/\/register\?source=content_page&lang=cs$/);
});

it("sets the document title and language while mounted", () => {
  const { unmount } = renderPage(fixtureEn);
  expect(document.title).toBe(fixtureEn.title);
  expect(document.documentElement.lang).toBe("en");
  unmount();
  expect(document.title).not.toBe(fixtureEn.title);
});

it.each([["2026-11-22", "cs", "22. 11. 2026"], ["2026-01-05", "en", "5 January 2026"], ["2026-03-09", "de", "9. März 2026"]])(
  "formats %s in %s as %s, the same on the server and in the browser", (date, language, text) => {
    expect(formatUpdated(date, language)).toBe(text);
  },
);

describe("ContentPage.css", () => {
  const css = () => readFile(sourcePath(new URL("./ContentPage.css", import.meta.url)), "utf-8");

  it("holds no hex color: colors come from the Clay tokens", async () => {
    expect((await css()).match(/#[0-9a-fA-F]{3,8}\b/g)).toBeNull();
  });

  it("keeps every declared font-size at or above the 12px readability floor", async () => {
    const sizes = [...(await css()).matchAll(/font-size:\s*(\d+(?:\.\d+)?)(px|rem)/g)].map(([, n, unit]) => (unit === "rem" ? Number(n) * 16 : Number(n)));
    expect(sizes.length).toBeGreaterThan(0);
    expect(sizes.filter((size) => size < 12)).toEqual([]);
  });
});
