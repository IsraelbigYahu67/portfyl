// Build-time prerender of the public pages (cloud edition only; run by
// `npm run build:cloud` after the client build).
//
//   1. SSR-builds src/entry-prerender.jsx into .prerender/ (git-ignored).
//   2. Renders every page in src/seo/publicPages.js to HTML and writes it,
//      with its head metadata and the CSS of the chunks it uses, into
//      dist/prerendered/<path>/index.html. dist/index.html stays the empty
//      app shell: the backend serves it for every non-public path.
//   3. Writes dist/robots.txt and dist/sitemap.xml from the same page list.
//
// The build fails when a page renders without content or with an inline
// script (the CSP allows script-src 'self' only).
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const PRERENDER_DIR = 'prerendered';

// "/" -> "index.html", "/en/" -> "en/index.html".
export function outputPath(pagePath) {
  if (!pagePath.startsWith('/') || !pagePath.endsWith('/') || pagePath.includes('..')) {
    throw new Error(`Public page paths must be absolute directories ending in "/": ${pagePath}`);
  }
  return `${pagePath.slice(1)}index.html`;
}

// Stylesheets of a lazily loaded page: its own chunk and every chunk it
// statically imports. Linked in <head> so the prerendered HTML is styled at
// first paint instead of waiting for the JS to load the chunk.
export function collectChunkAssets(manifest, entry) {
  const visited = new Set(), css = new Set(), modules = new Set();
  function visit(key) {
    if (visited.has(key)) return;
    const chunk = manifest[key];
    if (!chunk) throw new Error(`Missing manifest entry: ${key}`);
    visited.add(key);
    // Dependencies first, like Vite's own preloading: shared CSS precedes the
    // page's, so the page's rules win ties as they do on a client-side load.
    for (const dependency of chunk.imports || []) visit(dependency);
    if (chunk.file.endsWith('.js')) modules.add(chunk.file);
    for (const file of chunk.css || []) css.add(file);
  }
  visit(entry);
  return { css: [...css], modules: [...modules] };
}

export function validateMarkup(pagePath, markup) {
  if (!/<h1[\s>]/.test(markup)) throw new Error(`Prerendered ${pagePath} has no <h1>; did it render the fallback?`);
  if (/<script/i.test(markup)) throw new Error(`Prerendered ${pagePath} contains an inline <script>, which the CSP blocks.`);
  if (markup.includes('Loading Portfyl')) throw new Error(`Prerendered ${pagePath} rendered the loading fallback.`);
}

// The page's own stylesheets and modules go last in <head>, after the
// entry's, so the cascade order matches a client-side load (entry CSS first,
// then the lazy chunk's). Files the template already references are skipped.
export function injectPage(template, { language, head, markup, css, modules }) {
  const referenced = (file) => template.includes(`/${file}"`);
  const assets = [
    ...css.filter((file) => !referenced(file)).map((file) => `<link rel="stylesheet" href="/${file}" />`),
    ...modules.filter((file) => !referenced(file)).map((file) => `<link rel="modulepreload" href="/${file}" />`),
  ];
  const steps = [
    [/<html lang="[^"]*">/, `<html lang="${language}">`],
    [/<title>[^<]*<\/title>/, head],
    ['</head>', `  ${assets.join('\n    ')}\n  </head>`],
    ['<div id="root"></div>', `<div id="root">${markup}</div>`],
  ];
  return steps.reduce((html, [pattern, replacement]) => {
    if (!(typeof pattern === 'string' ? html.includes(pattern) : pattern.test(html))) {
      throw new Error(`index.html template no longer contains ${pattern}`);
    }
    return html.replace(pattern, () => replacement);
  }, template);
}

const WELCOME_CHUNK = 'src/pages/Welcome.jsx';

export async function prerender({ root = resolve(dirname(fileURLToPath(import.meta.url)), '..') } = {}) {
  const dist = resolve(root, 'dist');
  const ssrOut = resolve(root, '.prerender');
  const { build } = await import('vite');
  await build({
    root,
    mode: 'edition-cloud',
    logLevel: 'warn',
    build: { ssr: 'src/entry-prerender.jsx', outDir: ssrOut, emptyOutDir: true, manifest: false, copyPublicDir: false },
  });
  try {
    const server = await import(pathToFileURL(resolve(ssrOut, 'entry-prerender.js')).href);
    const template = readFileSync(resolve(dist, 'index.html'), 'utf8');
    const manifest = JSON.parse(readFileSync(resolve(dist, '.vite/manifest.json'), 'utf8'));
    const assets = collectChunkAssets(manifest, WELCOME_CHUNK);
    rmSync(resolve(dist, PRERENDER_DIR), { recursive: true, force: true });
    for (const page of server.PUBLIC_PAGES) {
      const markup = await server.render(page.path);
      validateMarkup(page.path, markup);
      const html = injectPage(template, { language: page.language, head: server.headTags(page), markup, ...assets });
      const target = resolve(dist, PRERENDER_DIR, outputPath(page.path));
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, html);
      console.log(`prerendered ${page.path} -> dist/${PRERENDER_DIR}/${outputPath(page.path)}`);
    }
    writeFileSync(resolve(dist, 'robots.txt'), server.robotsTxt());
    writeFileSync(resolve(dist, 'sitemap.xml'), server.sitemapXml());
    console.log('wrote dist/robots.txt and dist/sitemap.xml');
  } finally {
    rmSync(ssrOut, { recursive: true, force: true });
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  prerender().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
