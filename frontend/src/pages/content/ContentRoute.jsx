import { lazy, useMemo } from "react";
import ContentPage from "./ContentPage";
import { languagePathsFor, normalizeContentPages } from "../../seo/contentPages";

// Article bodies, one lazy chunk each. A registry entry names its body by file
// name (`body: "<name>"` -> ./bodies/<name>.jsx); an entry whose `body` is an
// import function (tests) is used as is. The prerender reads the same chunk
// names from the build manifest, so a page's JS is preloaded.
const BODIES = import.meta.glob("./bodies/*.jsx");
const loaded = new Map();

function lazyBody(page) {
  const loader = typeof page.body === "function" ? page.body : BODIES[`./bodies/${page.body}.jsx`];
  if (!loader) throw new Error(`Content page ${page.path}: no body file src/pages/content/bodies/${page.body}.jsx`);
  if (!loaded.has(loader)) loaded.set(loader, lazy(loader));
  return loaded.get(loader);
}

// Renders the registered content page `page` (one of `pages`, the registry
// Root read it from) inside the shared layout. Root puts it in a Suspense
// boundary, so the prerender and the browser both wait for the body chunk.
export default function ContentRoute({ page: entry, pages }) {
  const all = useMemo(() => normalizeContentPages(pages), [pages]);
  const page = all.find((candidate) => candidate.path === entry.path);
  const Body = lazyBody(page);
  return (
    <ContentPage page={page} languagePaths={languagePathsFor(page, all)}>
      <Body />
    </ContentPage>
  );
}
