// The single list of public, indexable pages on portfyl.com and their head
// metadata. The build-time prerender (scripts/prerender.mjs) renders exactly
// these, writes sitemap.xml and robots.txt from them, and the backend serves
// a prerendered file only when one exists -- so a page missing here is not
// public, and nothing else needs a second copy of this list.
// See docs/superpowers/plans/2026-11-09-portfyl-seo.md.
import { COPY } from "../pages/welcomeCopy";
import { LANDING_PATHS } from "../lib/routes";

export const SITE_ORIGIN = "https://portfyl.com";
export const SITE_NAME = "Portfyl";
// hreflang x-default: visitors whose language we do not offer read English.
export const DEFAULT_LANGUAGE = "en";

// Paths crawlers should skip. The tracker paths are also behind Cloudflare
// Access and the API needs a session; listing them keeps crawl budget on the
// public pages. /demo stays out until market-data rights cover public display
// (SEO plan, decision O3).
export const DISALLOWED_PATHS = ["/api/", "/demo", "/dashboard", "/login", "/register", "/onboarding", "/settings"];

// Search snippets: about 150 characters, claims limited to what the landing
// itself says (Trading 212 and CSV import, no Tax Report or Screener).
const DESCRIPTIONS = {
  cs: "Portfyl je přehled investičního portfolia: výkonnost, rozložení a dividendy akcií a ETF na jednom místě. Import z Trading 212 i CSV. Vyzkoušejte živé demo.",
  en: "Portfyl brings your stock and ETF portfolio together: performance, allocation and dividends in one clear view. Import from Trading 212 or CSV. Try the live demo.",
  de: "Portfyl zeigt dein Aktien- und ETF-Portfolio übersichtlich: Performance, Aufteilung und Dividenden an einem Ort. Import aus Trading 212 oder CSV. Live-Demo testen.",
};

const OG_LOCALES = { cs: "cs_CZ", en: "en_GB", de: "de_DE" };

// `group` ties the language versions of one page together for hreflang.
export const PUBLIC_PAGES = Object.entries(LANDING_PATHS).map(([language, path]) => ({
  group: "home",
  path,
  language,
  title: COPY[language].title,
  description: DESCRIPTIONS[language],
  ogImage: `/og/portfyl-${language}.jpg`,
  ogLocale: OG_LOCALES[language],
}));

export const absoluteUrl = (path) => new URL(path, SITE_ORIGIN).href;

export function alternatesFor(page, pages = PUBLIC_PAGES) {
  const versions = pages.filter((candidate) => candidate.group === page.group);
  const fallback = versions.find((candidate) => candidate.language === DEFAULT_LANGUAGE) ?? versions[0];
  return [
    ...versions.map((version) => ({ hreflang: version.language, href: absoluteUrl(version.path) })),
    { hreflang: "x-default", href: absoluteUrl(fallback.path) },
  ];
}

// Structured data (schema.org): who publishes the site and what the product
// is. No `offers` until pricing is public; no FAQ/HowTo markup (Google no
// longer shows those rich results for sites like this one).
export function structuredData(page) {
  return {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "Organization", "@id": `${SITE_ORIGIN}/#organization`, name: SITE_NAME, url: `${SITE_ORIGIN}/`, logo: absoluteUrl("/logo.png") },
      { "@type": "WebSite", "@id": `${SITE_ORIGIN}/#website`, name: SITE_NAME, url: `${SITE_ORIGIN}/`, publisher: { "@id": `${SITE_ORIGIN}/#organization` }, inLanguage: ["cs", "en", "de"] },
      {
        "@type": "SoftwareApplication",
        name: SITE_NAME,
        applicationCategory: "FinanceApplication",
        operatingSystem: "Web",
        url: absoluteUrl(page.path),
        description: page.description,
        inLanguage: page.language,
        publisher: { "@id": `${SITE_ORIGIN}/#organization` },
      },
    ],
  };
}

const escapeHtml = (value) => String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// JSON inside <script type="application/ld+json"> is data, not code: the CSP
// (script-src 'self') does not apply to it. "<" is escaped so the text can
// never close the element.
const jsonForHtml = (value) => JSON.stringify(value).replace(/</g, "\\u003c");

export function headTags(page, pages = PUBLIC_PAGES) {
  const url = absoluteUrl(page.path);
  const image = absoluteUrl(page.ogImage);
  const alternates = alternatesFor(page, pages);
  const otherLocales = pages
    .filter((candidate) => candidate.group === page.group && candidate.language !== page.language)
    .map((candidate) => candidate.ogLocale);
  return [
    `<title>${escapeHtml(page.title)}</title>`,
    `<meta name="description" content="${escapeHtml(page.description)}" />`,
    `<link rel="canonical" href="${url}" />`,
    ...alternates.map(({ hreflang, href }) => `<link rel="alternate" hreflang="${hreflang}" href="${href}" />`),
    `<meta property="og:type" content="website" />`,
    `<meta property="og:site_name" content="${SITE_NAME}" />`,
    `<meta property="og:title" content="${escapeHtml(page.title)}" />`,
    `<meta property="og:description" content="${escapeHtml(page.description)}" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:image" content="${image}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta property="og:locale" content="${page.ogLocale}" />`,
    ...otherLocales.map((locale) => `<meta property="og:locale:alternate" content="${locale}" />`),
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<script type="application/ld+json">${jsonForHtml(structuredData(page))}</script>`,
  ].join("\n    ");
}

export function sitemapXml(pages = PUBLIC_PAGES, lastmod = new Date().toISOString().slice(0, 10)) {
  const entries = pages.map((page) => [
    "  <url>",
    `    <loc>${absoluteUrl(page.path)}</loc>`,
    `    <lastmod>${lastmod}</lastmod>`,
    ...alternatesFor(page, pages).map(({ hreflang, href }) => `    <xhtml:link rel="alternate" hreflang="${hreflang}" href="${href}" />`),
    "  </url>",
  ].join("\n"));
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ...entries,
    "</urlset>",
    "",
  ].join("\n");
}

// Crawlers that collect model-training data rather than serve search
// results. Search and AI-answer crawlers (Googlebot, Bingbot, SeznamBot,
// OAI-SearchBot, PerplexityBot, Claude-SearchBot) fall under "*" and may read
// the public pages; these may not (SEO plan, decision O4). Cloudflare's own
// AI-bot settings must agree -- see the plan's task S0.
export const TRAINING_CRAWLERS = [
  "GPTBot", "ClaudeBot", "anthropic-ai", "Google-Extended", "Applebot-Extended",
  "CCBot", "Bytespider", "meta-externalagent",
];

export function robotsTxt(disallowed = DISALLOWED_PATHS, trainingCrawlers = TRAINING_CRAWLERS) {
  return [
    ...trainingCrawlers.map((agent) => `User-agent: ${agent}`),
    "Disallow: /",
    "",
    "User-agent: *",
    ...disallowed.map((path) => `Disallow: ${path}`),
    "",
    `Sitemap: ${absoluteUrl("/sitemap.xml")}`,
    "",
  ].join("\n");
}
