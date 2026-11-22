// The registry of public content pages (guides, broker and feature pages,
// explainers, trust pages) on portfyl.com. It is EMPTY on purpose until a
// page is written and reviewed by a person: nothing here is a placeholder.
//
// Adding a page is three steps, and nothing else needs a second copy:
//
//   1. Body: `src/pages/content/bodies/<name>.jsx`, a default-exported React
//      component with the article text. It renders into <ContentPage>, which
//      already provides the single <h1> (from `heading`), the header with the
//      language links, the "last updated" line, the "not investment advice"
//      note, the call to action and the footer with the legal links. The body
//      uses plain h2/h3/p/ul/ol/table/figure elements and no h1. No
//      inline <script>, no hex colors, no copy for chrome the layout owns.
//
//   2. Metadata: `src/seo/pages/<name>.js`, a default export (plain data):
//        path         "/sledovani-portfolia-trading-212/"  Czech, no prefix;
//                     "/en/..." English, "/de/..." German. Lowercase words
//                     joined by "-", one or two levels, ends in "/", no dot,
//                     not an app path (see RESERVED_FIRST_SEGMENTS).
//        language     "cs" | "en" | "de", and it must match the path prefix.
//        title        10-70 characters, unique, the search result headline.
//        description  110-165 characters, the snippet. Claims limited to what
//                     the product does in cloud: no Tax Report, no Screener.
//        targetQuery  the search query and intent the page answers, so the
//                     keyword decision stays reviewable (plan section 5, Wave 2).
//        lastmod      "YYYY-MM-DD", the day the text last changed in substance
//                     (sitemap <lastmod>, "updated" line, Article dateModified).
//        body         "<name>" -- the file name in step 1, without extension.
//        heading      optional H1 text when it should differ from `title`.
//        group        optional hreflang group. Versions of one page in several
//                     languages share a group (one page per language). Left
//                     out, the page is its own group: it points hreflang at
//                     itself and x-default at itself.
//        ogImage      optional site-relative image, default
//                     /og/portfyl-<language>.jpg (1200x630).
//        noindex      optional, default false. true still prerenders the page
//                     but adds <meta name="robots" content="noindex, nofollow">
//                     and keeps it out of sitemap.xml and hreflang.
//        adviceNote   optional, default true: the "not investment advice" note.
//                     Set false only on pages that do not touch decisions.
//
//   3. Register it below: `import page from "./<name>";` and add it to
//      CONTENT_PAGES.
//
// `src/seo/contentPages.js` validates every entry, and `npm run build:cloud`
// fails on a bad one. Prerender, sitemap.xml, robots.txt, hreflang and the
// backend all read this one list through `src/seo/publicPages.js`. Tests use
// fixture pages passed in as an override; never add one here.
export const CONTENT_PAGES = [];
