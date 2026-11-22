import { CONTENT_PAGES } from "./pages";
import {
  DESCRIPTION_LIMITS, LANDING_GROUP, RESERVED_FIRST_SEGMENTS, languageOfPath, languagePathsFor, normalizeContentPage, normalizeContentPages,
} from "./contentPages";
import { LANDING_PATHS } from "../lib/routes";
import { FIXTURE_PAGES, fixtureCs, fixtureEn, fixtureNoindex, fixtureSolo } from "../test/contentFixtures";

const make = (overrides) => ({ ...fixtureCs, ...overrides });

it("ships an empty registry that validates: no page is a placeholder", () => {
  expect(CONTENT_PAGES).toEqual([]);
  expect(normalizeContentPages(CONTENT_PAGES)).toEqual([]);
});

it("accepts the fixture pages and fills in the defaults", () => {
  const [cs, en, solo, hidden] = normalizeContentPages(FIXTURE_PAGES);
  expect(cs).toMatchObject({ heading: fixtureCs.title, ogImage: "/og/portfyl-cs.jpg", noindex: false, adviceNote: true, group: "fixture-tracker" });
  expect(en.ogImage).toBe("/og/portfyl-en.jpg");
  expect(solo).toMatchObject({ group: fixtureSolo.path, heading: "Samostatná stránka", adviceNote: false });
  expect(hidden.noindex).toBe(true);
  for (const page of [cs, en, solo, hidden]) {
    expect(page.description.length).toBeGreaterThanOrEqual(DESCRIPTION_LIMITS[0]);
    expect(page.description.length).toBeLessThanOrEqual(DESCRIPTION_LIMITS[1]);
  }
});

it("reads the language off the path prefix", () => {
  expect(languageOfPath("/guide/")).toBe("cs");
  expect(languageOfPath("/en/guide/")).toBe("en");
  expect(languageOfPath("/de/guide/")).toBe("de");
  expect(languageOfPath("/english-guide/")).toBe("cs");
});

it.each([
  ["no trailing slash", { path: "/fixture-page" }, /path must be/],
  ["an uppercase letter", { path: "/Fixture/" }, /path must be/],
  ["a dot (the server treats it as a file)", { path: "/fixture.html/" }, /path must be/],
  ["a nested empty segment", { path: "/a//b/" }, /path must be/],
  ["a landing path", { path: "/en/", language: "en" }, /landing page path/],
  ["a reserved first segment", { path: "/dashboard/" }, /reserved/],
  ["a language that does not match the prefix", { language: "en" }, /lives under/],
  ["an unknown language", { language: "fr", path: "/fr/x/" }, /language must be/],
  ["a title that is too short", { title: "Short" }, /title must be/],
  ["a description that is too long", { description: "x".repeat(166) }, /description must be/],
  ["no target query", { targetQuery: "" }, /targetQuery/],
  ["a fake date", { lastmod: "2026-13-45" }, /lastmod/],
  ["a date in the wrong format", { lastmod: "22.11.2026" }, /lastmod/],
  ["no body", { body: undefined }, /body must/],
  ["a body path with an extension", { body: "intro.jsx" }, /body must/],
  ["the landing group", { group: LANDING_GROUP }, /group must be/],
  ["an ogImage that is not site-relative", { ogImage: "https://example.com/x.jpg" }, /ogImage/],
  ["a noindex that is not a boolean", { noindex: "yes" }, /noindex/],
])("rejects a page with %s", (_name, overrides, message) => {
  expect(() => normalizeContentPage(make(overrides))).toThrow(message);
});

it("accepts nested paths and a language prefix that matches", () => {
  expect(() => normalizeContentPage(make({ path: "/pruvodce/trading-212/" }))).not.toThrow();
  expect(() => normalizeContentPage(make({ path: "/en/guides/trading-212/", language: "en" }))).not.toThrow();
  expect(() => normalizeContentPage(make({ path: "/de/anleitung/", language: "de" }))).not.toThrow();
});

it("rejects every reserved first segment, the landing paths' own", () => {
  for (const segment of RESERVED_FIRST_SEGMENTS) {
    expect(() => normalizeContentPage(make({ path: `/${segment}/` })), segment).toThrow(/reserved/);
  }
  for (const path of Object.values(LANDING_PATHS)) {
    expect(() => normalizeContentPage(make({ path, language: path === "/" ? "cs" : path.slice(1, 3) })), path).toThrow();
  }
});

it("rejects a language prefix without a slug", () => {
  expect(() => normalizeContentPage(make({ path: "/en/", language: "en" }))).toThrow();
});

it("rejects duplicate paths and two pages of one language in a group", () => {
  expect(() => normalizeContentPages([fixtureCs, fixtureCs])).toThrow(/registered twice/);
  expect(() => normalizeContentPages([fixtureCs, make({ path: "/fixture-druha/", group: fixtureCs.group })])).toThrow(/already has a cs page/);
});

it("points each language link at the sibling version, else the landing page, and never at a noindex sibling", () => {
  const pages = normalizeContentPages(FIXTURE_PAGES);
  const cs = pages.find((page) => page.path === fixtureCs.path);
  const solo = pages.find((page) => page.path === fixtureSolo.path);
  expect(languagePathsFor(cs, pages)).toEqual({ cs: fixtureCs.path, en: fixtureEn.path, de: "/de/" });
  expect(languagePathsFor(solo, pages)).toEqual({ cs: fixtureSolo.path, en: "/en/", de: "/de/" });

  const hiddenSibling = normalizeContentPages([fixtureCs, { ...fixtureEn, noindex: true }]);
  expect(languagePathsFor(hiddenSibling[0], hiddenSibling)).toEqual({ cs: fixtureCs.path, en: "/en/", de: "/de/" });
  expect(fixtureNoindex.noindex).toBe(true);
});
