import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { gzipSync } from 'node:zlib';

export function collectInitialAssets(manifest, entry = 'index.html') {
  const visited = new Set(), assets = new Set(), dynamicImports = new Set();
  function visit(key) {
    if (visited.has(key)) return;
    const chunk = manifest[key];
    if (!chunk) throw new Error(`Missing manifest entry: ${key}`);
    visited.add(key);
    if (/\.(js|css)$/.test(chunk.file)) assets.add(chunk.file);
    for (const css of chunk.css || []) assets.add(css);
    for (const dynamic of chunk.dynamicImports || []) dynamicImports.add(dynamic);
    for (const dependency of chunk.imports || []) visit(dependency);
  }
  visit(entry);
  return { assets: [...assets].sort(), dynamicImports: [...dynamicImports].sort() };
}

export function measureInitialBundle(directory) {
  const manifest = JSON.parse(readFileSync(resolve(directory, '.vite/manifest.json'), 'utf8'));
  const graph = collectInitialAssets(manifest);
  const assets = graph.assets.map(file => {
    const bytes = readFileSync(resolve(directory, file));
    return { file, raw_bytes: bytes.length, gzip_bytes: gzipSync(bytes, { level: 9 }).length };
  });
  const total = extension => assets.filter(asset => asset.file.endsWith(extension)).reduce((sum, asset) => sum + asset.gzip_bytes, 0);
  const js = total('.js'), css = total('.css');
  return {
    entry: 'index.html', gzip_level: 9,
    initial_js_gzip_bytes: js, initial_css_gzip_bytes: css,
    initial_combined_gzip_bytes: js + css, initial_combined_gzip_kib: (js + css) / 1024,
    assets, excluded_dynamic_imports: graph.dynamicImports,
    exclusions: ['dynamic imports', 'fonts', 'images', 'source maps'],
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { process.stdout.write(`${JSON.stringify(measureInitialBundle(process.argv[2] || 'dist'), null, 2)}\n`); }
  catch (error) { process.stderr.write(`Bundle measurement failed: ${error.message}\n`); process.exitCode = 1; }
}
