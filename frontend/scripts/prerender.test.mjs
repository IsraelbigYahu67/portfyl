import assert from 'node:assert/strict';
import { test } from 'node:test';
import { assetsForPage, collectChunkAssets, injectPage, mergeAssets, outputPath, validateDocument, validateMarkup } from './prerender.mjs';

const TEMPLATE = `<!DOCTYPE html>
<html lang="en">
  <head>
    <title>Portfyl</title>
    <script type="module" crossorigin src="/assets/index-a.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-a.css">
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>`;

test('maps public page paths to files under the prerender directory', () => {
  assert.equal(outputPath('/'), 'index.html');
  assert.equal(outputPath('/en/'), 'en/index.html');
  assert.throws(() => outputPath('/en'), /ending in "\/"/);
  assert.throws(() => outputPath('/../x/'), /ending in "\/"/);
});

test('collects a lazy page\'s CSS and modules, dependencies first', () => {
  const manifest = {
    'index.html': { file: 'assets/index-a.js', css: ['assets/index-a.css'] },
    'src/pages/Welcome.jsx': { file: 'assets/Welcome-b.js', css: ['assets/Welcome-b.css'], imports: ['index.html', '_shared.js'] },
    '_shared.js': { file: 'assets/shared-c.js', css: ['assets/shared-c.css'] },
  };
  assert.deepEqual(collectChunkAssets(manifest, 'src/pages/Welcome.jsx'), {
    css: ['assets/index-a.css', 'assets/shared-c.css', 'assets/Welcome-b.css'],
    modules: ['assets/index-a.js', 'assets/shared-c.js', 'assets/Welcome-b.js'],
  });
  assert.throws(() => collectChunkAssets(manifest, 'missing.jsx'), /Missing manifest entry/);
});

test('injects language, head, page assets after the entry CSS, and markup', () => {
  const html = injectPage(TEMPLATE, {
    language: 'cs',
    head: '<title>Portfyl — Vaše investice.</title>\n<meta name="description" content="x" />',
    markup: '<h1>Vaše investice.</h1>',
    css: ['assets/index-a.css', 'assets/Welcome-b.css'],
    modules: ['assets/index-a.js', 'assets/Welcome-b.js'],
  });
  assert.match(html, /<html lang="cs">/);
  assert.match(html, /<title>Portfyl — Vaše investice\.<\/title>/);
  assert.doesNotMatch(html, /<title>Portfyl<\/title>/);
  assert.equal(html.match(/index-a\.css/g).length, 1, 'entry CSS is not linked twice');
  assert.equal(html.match(/index-a\.js/g).length, 1, 'entry module is not preloaded twice');
  assert.ok(html.indexOf('index-a.css') < html.indexOf('Welcome-b.css'), 'page CSS comes after entry CSS');
  assert.match(html, /<link rel="modulepreload" href="\/assets\/Welcome-b\.js" \/>/);
  assert.match(html, /<div id="root"><h1>Vaše investice\.<\/h1><\/div>/);
});

test('refuses a template it no longer understands', () => {
  assert.throws(() => injectPage(TEMPLATE.replace('<div id="root"></div>', '<main></main>'), {
    language: 'cs', head: '', markup: '<h1>x</h1>', css: [], modules: [],
  }), /no longer contains/);
});

test('rejects markup that would not be indexable or would break the CSP', () => {
  assert.doesNotThrow(() => validateMarkup('/', '<div><h1 id="t">Vaše investice.</h1></div>'));
  assert.throws(() => validateMarkup('/', '<div>Loading Portfyl…</div>'), /no <h1>/);
  assert.throws(() => validateMarkup('/', '<h1>x</h1><script>$RC()</script>'), /inline <script>/);
});

test('maps nested content page paths to files under the prerender directory', () => {
  assert.equal(outputPath('/sledovani-portfolia/'), 'sledovani-portfolia/index.html');
  assert.equal(outputPath('/en/trading-212-portfolio-tracker/'), 'en/trading-212-portfolio-tracker/index.html');
});

test('rejects a page with more than one h1', () => {
  assert.throws(() => validateMarkup('/x/', '<h1>a</h1><section><h1>b</h1></section>'), /2 <h1> elements/);
});

const HEAD = [
  '<title>Fixture title</title>',
  '<meta name="description" content="A description." />',
  '<link rel="canonical" href="https://portfyl.com/x/" />',
  '<script type="application/ld+json">{"@type":"Article"}</script>',
  '<script src="/theme-init.js"></script>',
  '<script type="module" crossorigin src="/assets/index-a.js"></script>',
].join('\n');
const page = (head = HEAD, body = '<div id="root"><h1>x</h1></div>') => `<!DOCTYPE html><html><head>${head}</head><body>${body}</body></html>`;

test('accepts a finished page with head metadata, JSON-LD data and script files', () => {
  assert.doesNotThrow(() => validateDocument('/x/', page()));
});

test('rejects a finished page that lacks a title, description or canonical link', () => {
  assert.throws(() => validateDocument('/x/', page(HEAD.replace('<title>Fixture title</title>', '<title></title>'))), /no <title>/);
  assert.throws(() => validateDocument('/x/', page(HEAD.replace(/<meta name="description"[^>]*>/, ''))), /no meta description/);
  assert.throws(() => validateDocument('/x/', page(HEAD.replace('content="A description."', 'content=""'))), /no meta description/);
  assert.throws(() => validateDocument('/x/', page(HEAD.replace(/<link rel="canonical"[^>]*>/, ''))), /no canonical link/);
  assert.throws(() => validateDocument('/x/', page(HEAD.replace('https://portfyl.com/x/', '/x/'))), /no canonical link/);
});

test('rejects a finished page with an inline script, in the head or the body', () => {
  assert.throws(() => validateDocument('/x/', page(`${HEAD}\n<script>window.x = 1</script>`)), /inline <script>/);
  assert.throws(() => validateDocument('/x/', page(HEAD, '<div id="root"><h1>x</h1><script>$RC()</script></div>')), /inline <script>/);
  assert.throws(() => validateDocument('/x/', page(`${HEAD}\n<script type="module">import("/x.js")</script>`)), /inline <script>/);
});

test('merges chunk asset lists without repeating a file', () => {
  assert.deepEqual(
    mergeAssets({ css: ['a.css', 'b.css'], modules: ['a.js'] }, { css: ['a.css', 'c.css'], modules: ['a.js', 'c.js'] }),
    { css: ['a.css', 'b.css', 'c.css'], modules: ['a.js', 'c.js'] },
  );
});

test('gives a content page the shared route chunk plus its body chunk, and a landing page the Welcome chunk', () => {
  const manifest = {
    'index.html': { file: 'assets/index-a.js', css: ['assets/index-a.css'] },
    'src/pages/content/ContentRoute.jsx': { file: 'assets/ContentRoute-b.js', css: ['assets/ContentRoute-b.css'], imports: ['index.html'] },
    'src/pages/content/bodies/trading-212.jsx': { file: 'assets/trading-212-c.js', css: ['assets/trading-212-c.css'], imports: ['index.html'] },
  };
  const landing = { css: ['welcome.css'], modules: ['welcome.js'] };
  assert.equal(assetsForPage(manifest, { path: '/en/' }, landing), landing);
  assert.deepEqual(assetsForPage(manifest, { kind: 'content', body: 'trading-212' }, landing), {
    css: ['assets/index-a.css', 'assets/ContentRoute-b.css', 'assets/trading-212-c.css'],
    modules: ['assets/index-a.js', 'assets/ContentRoute-b.js', 'assets/trading-212-c.js'],
  });
  assert.deepEqual(assetsForPage(manifest, { kind: 'content', body: () => {} }, landing).modules, ['assets/index-a.js', 'assets/ContentRoute-b.js']);
  assert.throws(() => assetsForPage(manifest, { kind: 'content', body: 'missing' }, landing), /Missing manifest entry/);
});
