import { test } from 'node:test';
import assert from 'node:assert/strict';
import { collectInitialAssets } from './measure-initial-bundle.mjs';

test('follows static imports once, handles cycles, and excludes dynamic chunks', () => {
  const manifest = {
    'index.html': { file: 'entry.js', css: ['entry.css'], imports: ['a', 'b'], dynamicImports: ['route'] },
    a: { file: 'a.js', imports: ['b'], css: ['shared.css'] },
    b: { file: 'b.js', imports: ['a'], css: ['shared.css'], dynamicImports: ['other'] },
    route: { file: 'route.js' }, other: { file: 'other.js' },
  };
  assert.deepEqual(collectInitialAssets(manifest), {
    assets: ['a.js', 'b.js', 'entry.css', 'entry.js', 'shared.css'],
    dynamicImports: ['other', 'route'],
  });
});

test('rejects missing entries and static imports', () => {
  assert.throws(() => collectInitialAssets({}), /index.html/);
  assert.throws(() => collectInitialAssets({ 'index.html': { file: 'entry.js', imports: ['missing'] } }), /missing/);
});
