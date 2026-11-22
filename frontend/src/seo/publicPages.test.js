import { existsSync } from "node:fs";
import { sourcePath } from "../test/sourcePath";
import { COPY } from "../pages/welcomeCopy";
import { HAS_PUBLIC_HOME, LANDING_PATHS, landingLanguage } from "../lib/routes";
import {
  DISALLOWED_PATHS, PUBLIC_PAGES, SEZNAM_VERIFICATION, TRAINING_CRAWLERS, alternatesFor, contentPublicPages, headTags, robotsTxt, sitemapXml, structuredData,
} from "./publicPages";
import { FIXTURE_PAGES, fixtureCs, fixtureEn, fixtureNoindex, fixtureSolo } from "../test/contentFixtures";

const publicDir = sourcePath(new URL("../../public", import.meta.url));
const publicFile = (path) => `${publicDir}${path}`;

it("lists one page per landing language, each a URL the app renders as that language", () => {
  expect(PUBLIC_PAGES.map(({ path, language }) => [path, language])).toEqual([["/", "cs"], ["/en/", "en"], ["/de/", "de"]]);
  if (HAS_PUBLIC_HOME) for (const page of PUBLIC_PAGES) expect(landingLanguage(page.path)).toBe(page.language);
  expect(Object.values(LANDING_PATHS)).toEqual(PUBLIC_PAGES.map((page) => page.path));
});

it.each(PUBLIC_PAGES)("gives $path a snippet-sized description and the page's own title", (page) => {
  expect(page.title).toBe(COPY[page.language].title);
  expect(page.description.length).toBeGreaterThanOrEqual(110);
  expect(page.description.length).toBeLessThanOrEqual(165);
  expect(page.description).not.toMatch(/tax|daň|steuer|screener/i);
  // The public demo is retired: the snippet promises the examples on the page.
  expect(page.description).not.toMatch(/demo/i);
  expect(existsSync(publicFile(page.ogImage))).toBe(true);
});

it("promises interactive examples in each language", () => {
  const byLanguage = Object.fromEntries(PUBLIC_PAGES.map((page) => [page.language, page.description]));
  expect(byLanguage.cs).toContain("Vyzkoušejte interaktivní ukázky.");
  expect(byLanguage.en).toContain("Try the interactive examples.");
  expect(byLanguage.de).toContain("Probiere die interaktiven Beispiele aus.");
});

it("links every language version reciprocally, with English as x-default", () => {
  const sets = PUBLIC_PAGES.map((page) => alternatesFor(page));
  for (const set of sets) expect(set).toEqual(sets[0]);
  expect(sets[0]).toEqual([
    { hreflang: "cs", href: "https://portfyl.com/" },
    { hreflang: "en", href: "https://portfyl.com/en/" },
    { hreflang: "de", href: "https://portfyl.com/de/" },
    { hreflang: "x-default", href: "https://portfyl.com/en/" },
  ]);
});

it("renders head tags with a self canonical, escaped text and data-only JSON-LD", () => {
  const page = { ...PUBLIC_PAGES[1], title: 'A "quoted" <title>', description: "</script><script>alert(1)</script>" };
  const head = headTags(page);
  expect(head).toContain('<link rel="canonical" href="https://portfyl.com/en/" />');
  expect(head).toContain("<title>A &quot;quoted&quot; &lt;title&gt;</title>");
  expect(head).not.toContain("<script>alert");
  expect(head.match(/<script/g)).toHaveLength(1);
  expect(head).toContain('<script type="application/ld+json">');
  expect(head).toContain('<meta property="og:locale:alternate" content="cs_CZ" />');
});

it("puts the Seznam Webmaster verification tag on the home page only", () => {
  const tag = `<meta name="${SEZNAM_VERIFICATION.name}" content="${SEZNAM_VERIFICATION.content}" />`;
  for (const page of PUBLIC_PAGES) {
    const head = headTags(page);
    if (page.path === "/") expect(head).toContain(tag);
    else expect(head).not.toContain("seznam-wmt");
  }
  expect(SEZNAM_VERIFICATION.path).toBe("/");
});

it("describes the product without offers or FAQ markup", () => {
  const graph = structuredData(PUBLIC_PAGES[0])["@graph"];
  expect(graph.map((node) => node["@type"])).toEqual(["Organization", "WebSite", "SoftwareApplication"]);
  expect(graph[2]).not.toHaveProperty("offers");
  expect(graph[2].inLanguage).toBe("cs");
});

it("writes a sitemap with every page and its alternates", () => {
  const xml = sitemapXml(PUBLIC_PAGES, "2026-11-09");
  expect(xml.match(/<url>/g)).toHaveLength(PUBLIC_PAGES.length);
  expect(xml).toContain("<loc>https://portfyl.com/de/</loc>");
  expect(xml.match(/hreflang="x-default"/g)).toHaveLength(PUBLIC_PAGES.length);
});

it("lets search crawlers in, keeps training crawlers and private paths out, and names the sitemap", () => {
  const robots = robotsTxt();
  for (const agent of TRAINING_CRAWLERS) expect(robots).toContain(`User-agent: ${agent}\n`);
  expect(robots).toMatch(/User-agent: meta-externalagent\nDisallow: \/\n/);
  for (const path of DISALLOWED_PATHS) expect(robots).toContain(`Disallow: ${path}\n`);
  expect(robots).not.toMatch(/Googlebot|SeznamBot|OAI-SearchBot|PerplexityBot|Claude-SearchBot/);
  expect(robots).toContain("Sitemap: https://portfyl.com/sitemap.xml");
  for (const page of PUBLIC_PAGES) expect(DISALLOWED_PATHS.some((path) => page.path.startsWith(path))).toBe(false);
});

// /demo is answered with a 301 to the home page. A crawler must be allowed to
// fetch it to see that redirect, so it is neither disallowed nor listed.
it("neither disallows nor lists the retired /demo", () => {
  expect(DISALLOWED_PATHS.filter((path) => /^\/demo/.test(path))).toEqual([]);
  expect(robotsTxt()).not.toMatch(/\/demo/);
  expect(sitemapXml(PUBLIC_PAGES, "2026-11-19")).not.toMatch(/\/demo/);
});

// Content pages: the registry is empty in production, so these tests hand
// fixture pages to the same functions the prerender calls.
describe("content pages in the public list", () => {
  const withContent = [...PUBLIC_PAGES, ...contentPublicPages(FIXTURE_PAGES)];
  const page = (path) => withContent.find((candidate) => candidate.path === path);

  it("adds nothing in production and keeps the three landing pages first", () => {
    expect(contentPublicPages()).toEqual([]);
    expect(withContent.slice(0, 3)).toEqual(PUBLIC_PAGES);
    expect(PUBLIC_PAGES.every((candidate) => candidate.kind === undefined)).toBe(true);
  });

  it("marks content pages and gives them the language's Open Graph locale", () => {
    expect(page(fixtureCs.path)).toMatchObject({ kind: "content", ogLocale: "cs_CZ", group: "fixture-tracker" });
    expect(page(fixtureEn.path).ogLocale).toBe("en_GB");
  });

  it("links the language versions of one page reciprocally, with English as x-default", () => {
    const expected = [
      { hreflang: "cs", href: "https://portfyl.com/fixture-sledovani-portfolia/" },
      { hreflang: "en", href: "https://portfyl.com/en/fixture-portfolio-tracker/" },
      { hreflang: "x-default", href: "https://portfyl.com/en/fixture-portfolio-tracker/" },
    ];
    expect(alternatesFor(page(fixtureCs.path), withContent)).toEqual(expected);
    expect(alternatesFor(page(fixtureEn.path), withContent)).toEqual(expected);
  });

  it("gives a single-language page a self reference and itself as x-default", () => {
    expect(alternatesFor(page(fixtureSolo.path), withContent)).toEqual([
      { hreflang: "cs", href: "https://portfyl.com/fixture-samostatna-stranka/" },
      { hreflang: "x-default", href: "https://portfyl.com/fixture-samostatna-stranka/" },
    ]);
  });

  it("leaves the landing pages' hreflang untouched", () => {
    expect(alternatesFor(PUBLIC_PAGES[0], withContent)).toEqual(alternatesFor(PUBLIC_PAGES[0]));
    expect(alternatesFor(PUBLIC_PAGES[0], withContent)).toHaveLength(4);
  });

  it("renders an article's head: self canonical, hreflang, article type and a data-only Article", () => {
    const head = headTags(page(fixtureCs.path), withContent);
    expect(head).toContain('<link rel="canonical" href="https://portfyl.com/fixture-sledovani-portfolia/" />');
    expect(head).toContain('<link rel="alternate" hreflang="en" href="https://portfyl.com/en/fixture-portfolio-tracker/" />');
    expect(head).toContain('<meta property="og:type" content="article" />');
    expect(head).toContain('<meta property="og:locale:alternate" content="en_GB" />');
    expect(head).toContain('<meta property="article:modified_time" content="2026-11-20" />');
    expect(head).toContain('<meta property="og:image" content="https://portfyl.com/og/portfyl-cs.jpg" />');
    expect(head).not.toContain('name="robots"');
    expect(head.match(/<script/g)).toHaveLength(1);
    expect(head).toContain('<script type="application/ld+json">');
  });

  it("describes a content page as an Article without an author or offers", () => {
    const graph = structuredData(page(fixtureSolo.path))["@graph"];
    expect(graph.map((node) => node["@type"])).toEqual(["Organization", "WebSite", "Article"]);
    const article = graph[2];
    expect(article).toMatchObject({
      headline: "Samostatná stránka",
      inLanguage: "cs",
      dateModified: "2026-11-19",
      url: "https://portfyl.com/fixture-samostatna-stranka/",
      publisher: { "@id": "https://portfyl.com/#organization" },
    });
    for (const key of ["author", "datePublished", "offers"]) expect(article).not.toHaveProperty(key);
  });

  it("keeps a noindex page out of hreflang and the sitemap, and tells crawlers so", () => {
    const hidden = page(fixtureNoindex.path);
    const head = headTags(hidden, withContent);
    expect(head).toContain('<meta name="robots" content="noindex, nofollow" />');
    expect(head).toContain('<link rel="canonical" href="https://portfyl.com/fixture-skryta-stranka/" />');
    expect(head).not.toContain('rel="alternate"');
    const xml = sitemapXml(withContent, "2026-11-22");
    expect(xml).not.toContain("fixture-skryta-stranka");
    expect(xml.match(/<url>/g)).toHaveLength(withContent.length - 1);
  });

  it("lists content pages in the sitemap with their own lastmod, and landing pages with the build date", () => {
    const xml = sitemapXml(withContent, "2026-11-22");
    expect(xml).toContain("<loc>https://portfyl.com/fixture-sledovani-portfolia/</loc>\n    <lastmod>2026-11-20</lastmod>");
    expect(xml).toContain("<loc>https://portfyl.com/en/fixture-portfolio-tracker/</loc>\n    <lastmod>2026-11-21</lastmod>");
    expect(xml).toContain("<loc>https://portfyl.com/en/</loc>\n    <lastmod>2026-11-22</lastmod>");
    expect(sitemapXml(PUBLIC_PAGES, "2026-11-22")).toBe(sitemapXml(withContent.slice(0, 3), "2026-11-22"));
  });

  it("never lists a content page under a disallowed path", () => {
    for (const { path } of withContent) expect(DISALLOWED_PATHS.some((disallowed) => path.startsWith(disallowed))).toBe(false);
  });
});
