// Renders the server entry the way the build step does (scripts/prerender.mjs).
// Content pages come from a fixture registry: the real one is empty.
import { StrictMode } from "react";
import { act, screen } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import Root from "./Root";
import { HAS_PUBLIC_HOME } from "./lib/routes";
import { render } from "./entry-prerender";
import { contentPublicPages, headTags } from "./seo/publicPages";
import { injectPage, validateDocument, validateMarkup } from "../scripts/prerender.mjs";
import { FIXTURE_PAGES, fixtureCs, fixtureEn } from "./test/contentFixtures";

const TEMPLATE = `<!DOCTYPE html>
<html lang="en">
  <head>
    <title>Portfyl</title>
    <script src="/theme-init.js"></script>
    <script type="module" crossorigin src="/assets/index-a.js"></script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;

describe.skipIf(!HAS_PUBLIC_HOME)("prerendering a content page", () => {
  const pages = contentPublicPages(FIXTURE_PAGES);
  const build = async (fixture) => {
    const page = pages.find((candidate) => candidate.path === fixture.path);
    const markup = await render(page.path, { contentPages: FIXTURE_PAGES });
    return { page, markup, html: injectPage(TEMPLATE, { language: page.language, head: headTags(page, pages), markup, css: [], modules: [] }) };
  };

  it("renders the complete article, not the loading fallback, with one h1 and no inline script", async () => {
    const { page, markup, html } = await build(fixtureCs);
    expect(() => validateMarkup(page.path, markup)).not.toThrow();
    expect(() => validateDocument(page.path, html)).not.toThrow();
    expect(markup).toContain(`<h1>${fixtureCs.title}</h1>`);
    expect(markup).toContain("Fixture body paragraph about tracking a portfolio.");
    expect(markup).toContain("Nejde o investiční poradenství.");
    expect(markup).not.toContain("Loading Portfyl");
    expect(html).toContain('<html lang="cs">');
    expect(html).toContain('<link rel="canonical" href="https://portfyl.com/fixture-sledovani-portfolia/" />');
    expect(html).toContain('"@type":"Article"');
  });

  it("renders the English sibling with links to both versions", async () => {
    const { markup, html } = await build(fixtureEn);
    expect(markup).toContain(`<a href="${fixtureCs.path}" hrefLang="cs"`);
    expect(markup).toContain(`<a href="${fixtureEn.path}" hrefLang="en"`);
    expect(html).toContain('<link rel="alternate" hreflang="x-default" href="https://portfyl.com/en/fixture-portfolio-tracker/" />');
  });

  // main.jsx hydrates a prerendered public URL with the same Root, reading the
  // location from the window. Any mismatch would surface as a recoverable error.
  it("hydrates the prerendered HTML without a mismatch", async () => {
    const { markup } = await build(fixtureCs);
    window.history.replaceState({}, "", fixtureCs.path);
    const container = document.createElement("div");
    container.innerHTML = markup;
    document.body.append(container);
    const errors = [];
    await act(async () => {
      hydrateRoot(container, <StrictMode><Root contentPages={FIXTURE_PAGES} /></StrictMode>, { onRecoverableError: (error) => errors.push(error) });
    });
    expect(await screen.findByRole("heading", { level: 1, name: fixtureCs.title })).toBeInTheDocument();
    expect(errors.map((error) => error.message)).toEqual([]);
    expect(container.querySelectorAll("h1")).toHaveLength(1);
    container.remove();
  });
});
