import { existsSync } from "node:fs";
import { sourcePath } from "../test/sourcePath";
import { COPY } from "../pages/welcomeCopy";
import { HAS_PUBLIC_HOME, LANDING_PATHS, landingLanguage } from "../lib/routes";
import {
  DISALLOWED_PATHS, PUBLIC_PAGES, TRAINING_CRAWLERS, alternatesFor, headTags, robotsTxt, sitemapXml, structuredData,
} from "./publicPages";

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
  expect(existsSync(publicFile(page.ogImage))).toBe(true);
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
