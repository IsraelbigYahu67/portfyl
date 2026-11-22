// Validation and defaults for the content-page registry (src/seo/pages/index.js).
// Pure data in, pure data out: publicPages.js merges the result into
// PUBLIC_PAGES, and pages/content/ContentRoute.jsx reads it to render. A bad
// entry throws here, so the prerender (and with it `npm run build:cloud`)
// fails instead of publishing a page that crawlers or the router mishandle.
// See docs/superpowers/plans/2026-11-09-portfyl-seo.md (section 4a, Wave 2).
import { LANDING_PATHS } from "../lib/routes";

export const CONTENT_LANGUAGES = ["cs", "en", "de"];
// Landing pages share the "home" hreflang group; a content page never joins it.
export const LANDING_GROUP = "home";

// First path segments that already mean something else on portfyl.com (the
// app, the API, static files, the retired demo, the legal pages). A content
// page there would shadow or be shadowed by them.
export const RESERVED_FIRST_SEGMENTS = [
  "api", "assets", "og", "prerendered", "dashboard", "login", "register", "onboarding", "settings", "demo", "terms",
  "privacy", "auth", "billing", "pricing", "welcome", "health", "transactions", "allocation", "analytics", "dividends",
  "cash", "stock", "search", "watchlists", "import",
];

// Lowercase words joined by "-", one or two levels, always ending in "/".
// No dot: the server treats a last segment with a dot as a file.
const PATH_PATTERN = /^\/[a-z0-9]+(?:-[a-z0-9]+)*(?:\/[a-z0-9]+(?:-[a-z0-9]+)*)*\/$/;
const BODY_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export const TITLE_LIMITS = [10, 70];
// Snippet size, the same bounds the landing pages are tested against.
export const DESCRIPTION_LIMITS = [110, 165];

const fail = (path, message) => { throw new Error(`Content page ${path}: ${message}`); };
const text = (path, field, value, [min, max]) => {
  if (typeof value !== "string" || value.trim() !== value || value.length < min || value.length > max) {
    fail(path, `${field} must be a trimmed string of ${min}-${max} characters`);
  }
};

// The language prefix of a path: "/en/..." is English, "/de/..." German, and
// everything else is Czech, which owns the root.
export function languageOfPath(path) {
  const match = /^\/(en|de)\//.exec(path);
  return match ? match[1] : "cs";
}

export function normalizeContentPage(page) {
  const path = page?.path;
  if (typeof path !== "string" || !PATH_PATTERN.test(path)) {
    fail(String(path), 'path must be lowercase words joined by "-", start and end with "/", and contain no dot');
  }
  if (Object.values(LANDING_PATHS).includes(path)) fail(path, "that is a landing page path");
  const language = page.language;
  if (!CONTENT_LANGUAGES.includes(language)) fail(path, `language must be one of ${CONTENT_LANGUAGES.join(", ")}`);
  if (languageOfPath(path) !== language) fail(path, `a ${language} page lives under ${language === "cs" ? "no language prefix" : `/${language}/`}`);
  const first = path.split("/")[1];
  if (RESERVED_FIRST_SEGMENTS.includes(first)) fail(path, `"/${first}" is reserved by the app`);
  if (path.split("/").length - 2 < (language === "cs" ? 1 : 2)) fail(path, "a page needs a slug after the language prefix");

  text(path, "title", page.title, TITLE_LIMITS);
  text(path, "description", page.description, DESCRIPTION_LIMITS);
  const heading = page.heading ?? page.title;
  text(path, "heading", heading, [3, 120]);
  text(path, "targetQuery", page.targetQuery, [3, 160]);
  if (!DATE_PATTERN.test(page.lastmod ?? "") || Number.isNaN(Date.parse(page.lastmod))) fail(path, "lastmod must be a real YYYY-MM-DD date");
  if (!(typeof page.body === "function" || (typeof page.body === "string" && BODY_PATTERN.test(page.body)))) {
    fail(path, "body must name a file in pages/content/bodies/ (lowercase words joined by \"-\", no extension) or be an import function");
  }
  const group = page.group ?? path;
  if (typeof group !== "string" || !group || group === LANDING_GROUP) fail(path, `group must be a non-empty string other than "${LANDING_GROUP}"`);
  const ogImage = page.ogImage ?? `/og/portfyl-${language}.jpg`;
  if (typeof ogImage !== "string" || !ogImage.startsWith("/")) fail(path, "ogImage must be a site-relative path");
  if (page.noindex !== undefined && typeof page.noindex !== "boolean") fail(path, "noindex must be true or false");
  if (page.adviceNote !== undefined && typeof page.adviceNote !== "boolean") fail(path, "adviceNote must be true or false");

  return {
    path,
    language,
    group,
    title: page.title,
    heading,
    description: page.description,
    targetQuery: page.targetQuery,
    lastmod: page.lastmod,
    body: page.body,
    ogImage,
    noindex: page.noindex ?? false,
    adviceNote: page.adviceNote ?? true,
  };
}

// Normalizes every page and checks the set: one entry per path, and one
// language per hreflang group.
export function normalizeContentPages(pages) {
  const normalized = pages.map(normalizeContentPage);
  const paths = new Set();
  const languages = new Set();
  for (const page of normalized) {
    if (paths.has(page.path)) fail(page.path, "is registered twice");
    paths.add(page.path);
    const key = `${page.group} ${page.language}`;
    if (languages.has(key)) fail(page.path, `group "${page.group}" already has a ${page.language} page`);
    languages.add(key);
  }
  return normalized;
}

// Where each language's link in the header and footer leads: the sibling
// version of this page when one exists, else that language's landing page.
// noindex siblings are not offered.
export function languagePathsFor(page, pages) {
  const paths = { ...LANDING_PATHS };
  for (const sibling of pages) {
    if (sibling.group === page.group && !sibling.noindex) paths[sibling.language] = sibling.path;
  }
  paths[page.language] = page.path;
  return paths;
}
