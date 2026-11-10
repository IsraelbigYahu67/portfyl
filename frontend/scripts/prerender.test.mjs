import assert from 'node:assert/strict';
import { test } from 'node:test';
import { collectChunkAssets, injectPage, outputPath, validateMarkup } from './prerender.mjs';

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
