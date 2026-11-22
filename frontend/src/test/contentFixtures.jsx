// Fixture content pages for tests only. The real registry
// (src/seo/pages/index.js) is empty until a person writes a page, and nothing
// here ever ships: tests hand these in through the override parameters of
// contentPageFor(), <Root contentPages>, render() and contentPublicPages().
export function FixtureBody() {
  return (
    <>
      <p>Fixture body paragraph about tracking a portfolio.</p>
      <h2>Fixture section</h2>
      <p>Second paragraph with a <a href="/terms">link</a>.</p>
    </>
  );
}

const loadFixtureBody = () => Promise.resolve({ default: FixtureBody });

// Czech page and its English sibling share a hreflang group.
export const fixtureCs = {
  path: "/fixture-sledovani-portfolia/",
  language: "cs",
  group: "fixture-tracker",
  title: "Fixture: sledování portfolia v Portfylu",
  description: "Testovací stránka pro ověření prerenderu, hreflang a sitemapy. Obsah je vymyšlený a nikdy se nezveřejní na portfyl.com ani nikde jinde.",
  targetQuery: "fixture sledování portfolia",
  lastmod: "2026-11-20",
  body: loadFixtureBody,
};

export const fixtureEn = {
  path: "/en/fixture-portfolio-tracker/",
  language: "en",
  group: "fixture-tracker",
  title: "Fixture: portfolio tracker in Portfyl",
  description: "Test page for checking the prerender, hreflang and the sitemap. The content is made up and is never published on portfyl.com or anywhere else.",
  targetQuery: "fixture portfolio tracker",
  lastmod: "2026-11-21",
  body: loadFixtureBody,
};

// A single-language page: no group given, so it is its own group.
export const fixtureSolo = {
  path: "/fixture-samostatna-stranka/",
  language: "cs",
  title: "Fixture: samostatná stránka bez jazykových verzí",
  heading: "Samostatná stránka",
  description: "Testovací stránka bez sourozenců v jiných jazycích. Ověřuje, že hreflang i x-default ukazují na ni samu. Obsah je vymyšlený a nezveřejní se.",
  targetQuery: "fixture samostatná stránka",
  lastmod: "2026-11-19",
  body: loadFixtureBody,
  adviceNote: false,
};

export const fixtureNoindex = {
  path: "/fixture-skryta-stranka/",
  language: "cs",
  title: "Fixture: skrytá stránka mimo vyhledávače",
  description: "Testovací stránka s příznakem noindex. Ověřuje, že se vykreslí, ale nedostane se do sitemapy, do hreflang ani do indexu. Obsah je vymyšlený.",
  targetQuery: "fixture skrytá stránka",
  lastmod: "2026-11-18",
  body: loadFixtureBody,
  noindex: true,
};

export const FIXTURE_PAGES = [fixtureCs, fixtureEn, fixtureSolo, fixtureNoindex];
