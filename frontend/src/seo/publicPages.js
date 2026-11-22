// The single list of public, indexable pages on portfyl.com and their head
// metadata. The build-time prerender (scripts/prerender.mjs) renders exactly
// these, writes sitemap.xml and robots.txt from them, and the backend serves
// a prerendered file only when one exists -- so a page missing here is not
// public, and nothing else needs a second copy of this list.
// The list is the three landing pages plus the content pages registered in
// src/seo/pages/index.js (validated by contentPages.js).
// See docs/superpowers/plans/2026-11-09-portfyl-seo.md.
import { COPY } from "../pages/welcomeCopy";
import { LANDING_PATHS } from "../lib/routes";
import { normalizeContentPages } from "./contentPages";
import { CONTENT_PAGES } from "./pages";

export const SITE_ORIGIN = "https://portfyl.com";
export const SITE_NAME = "Portfyl";
// hreflang x-default: visitors whose language we do not offer read English.
export const DEFAULT_LANGUAGE = "en";

// Paths crawlers should skip. The tracker paths are also behind Cloudflare
// Access and the API needs a session; listing them keeps crawl budget on the
// public pages. The retired /demo is deliberately not listed: the server
// answers it with a 301 to the home page and a crawler has to be allowed to see
// that.
export const DISALLOWED_PATHS = ["/api/", "/dashboard", "/login", "/register", "/onboarding", "/settings"];

// Seznam Webmaster proves ownership of https://portfyl.com/ with this tag, so
// it goes on the home page only. Keep it for as long as the site stays
// registered there. Generating a new tag in Seznam invalidates this one.
export const SEZNAM_VERIFICATION = { path: "/", name: "seznam-wmt", content: "QTkKyFGdNiTb22LeuVunhEBSy9VIDQd2" };

// Search snippets: about 150 characters, claims limited to what the landing
// itself says (Trading 212 and CSV import, no Tax Report or Screener).
const DESCRIPTIONS = {
  cs: "Portfyl je přehled investičního portfolia: výkonnost, rozložení a dividendy akcií a ETF na jednom místě. Import z Trading 212 i CSV. Vyzkoušejte interaktivní ukázky.",
  en: "Portfyl shows your stock and ETF portfolio: performance, allocation and dividends in one clear view. Import from Trading 212 or CSV. Try the interactive examples.",
  de: "Portfyl zeigt dein Aktien- und ETF-Portfolio: Performance, Aufteilung und Dividenden. Import aus Trading 212 oder CSV. Probiere die interaktiven Beispiele aus.",
};

const OG_LOCALES = { cs: "cs_CZ", en: "en_GB", de: "de_DE" };

// `group` ties the language versions of one page together for hreflang.
const LANDING_PAGES = Object.entries(LANDING_PATHS).map(([language, path]) => ({
  group: "home",
  path,
  language,
  title: COPY[language].title,
  description: DESCRIPTIONS[language],
  ogImage: `/og/portfyl-${language}.jpg`,
  ogLocale: OG_LOCALES[language],
}));

// Content pages carry `kind: "content"` (an article, not the product page),
// plus their own lastmod and noindex flag; see contentPages.js for the rest.
export function contentPublicPages(pages = CONTENT_PAGES) {
  return normalizeContentPages(pages).map((page) => ({ ...page, kind: "content", ogLocale: OG_LOCALES[page.language] }));
}

export const PUBLIC_PAGES = [...LANDING_PAGES, ...contentPublicPages()];

export const absoluteUrl = (path) => new URL(path, SITE_ORIGIN).href;

// hreflang set of a page: every indexable version in its group plus x-default
// (English when it exists, else the first version -- so a single-language page
// points x-default at itself).
export function alternatesFor(page, pages = PUBLIC_PAGES) {
  const versions = pages.filter((candidate) => candidate.group === page.group && !candidate.noindex);
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
  const organization = { "@type": "Organization", "@id": `${SITE_ORIGIN}/#organization`, name: SITE_NAME, url: `${SITE_ORIGIN}/`, logo: absoluteUrl("/logo.png") };
  const website = { "@type": "WebSite", "@id": `${SITE_ORIGIN}/#website`, name: SITE_NAME, url: `${SITE_ORIGIN}/`, publisher: { "@id": `${SITE_ORIGIN}/#organization` }, inLanguage: ["cs", "en", "de"] };
  if (page.kind === "content") {
    // An article by the publisher: no `author` (nobody is credited until a
    // real, named author exists) and no datePublished (only lastmod is known).
    const url = absoluteUrl(page.path);
    return {
      "@context": "https://schema.org",
      "@graph": [
        organization,
        website,
        {
          "@type": "Article",
          "@id": `${url}#article`,
          headline: page.heading,
          description: page.description,
          url,
          mainEntityOfPage: { "@type": "WebPage", "@id": url },
          image: absoluteUrl(page.ogImage),
          inLanguage: page.language,
          dateModified: page.lastmod,
          publisher: { "@id": `${SITE_ORIGIN}/#organization` },
        },
      ],
    };
  }
  return {
    "@context": "https://schema.org",
    "@graph": [
      organization,
      website,
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
  const article = page.kind === "content";
  // A noindex page stays out of every hreflang set, its own included.
  const alternates = page.noindex ? [] : alternatesFor(page, pages);
  const otherLocales = page.noindex ? [] : pages
    .filter((candidate) => candidate.group === page.group && candidate.language !== page.language && !candidate.noindex)
    .map((candidate) => candidate.ogLocale);
  return [
    `<title>${escapeHtml(page.title)}</title>`,
    `<meta name="description" content="${escapeHtml(page.description)}" />`,
    ...(page.noindex ? [`<meta name="robots" content="noindex, nofollow" />`] : []),
    ...(page.path === SEZNAM_VERIFICATION.path
      ? [`<meta name="${SEZNAM_VERIFICATION.name}" content="${SEZNAM_VERIFICATION.content}" />`]
      : []),
    `<link rel="canonical" href="${url}" />`,
    ...alternates.map(({ hreflang, href }) => `<link rel="alternate" hreflang="${hreflang}" href="${href}" />`),
    `<meta property="og:type" content="${article ? "article" : "website"}" />`,
    `<meta property="og:site_name" content="${SITE_NAME}" />`,
    `<meta property="og:title" content="${escapeHtml(page.title)}" />`,
    `<meta property="og:description" content="${escapeHtml(page.description)}" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:image" content="${image}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta property="og:locale" content="${page.ogLocale}" />`,
    ...otherLocales.map((locale) => `<meta property="og:locale:alternate" content="${locale}" />`),
    ...(article ? [`<meta property="article:modified_time" content="${page.lastmod}" />`] : []),
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<script type="application/ld+json">${jsonForHtml(structuredData(page))}</script>`,
  ].join("\n    ");
}

// noindex pages are left out; a content page's own lastmod wins over the
// build date the landing pages use.
export function sitemapXml(pages = PUBLIC_PAGES, lastmod = new Date().toISOString().slice(0, 10)) {
  const entries = pages.filter((page) => !page.noindex).map((page) => [
    "  <url>",
    `    <loc>${absoluteUrl(page.path)}</loc>`,
    `    <lastmod>${page.lastmod ?? lastmod}</lastmod>`,
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
