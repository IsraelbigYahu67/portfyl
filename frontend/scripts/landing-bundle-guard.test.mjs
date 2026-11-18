import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkLanding, measureLanding, extractFigures } from './landing-bundle-guard.mjs';

const SCRIPT = resolve(dirname(fileURLToPath(import.meta.url)), 'landing-bundle-guard.mjs');
const KINDS = ['allocation', 'stock', 'performance', 'dividends', 'portfolios'];

// A text that does not gzip to nothing and differs between chunks.
const filler = (seed, length) => Array.from({ length }, (_, i) => String.fromCharCode(97 + ((i * 7 + seed * 13 + (i >> 3)) % 26))).join('');

function figure(kind, inner = 'Ukazkove portfolio. Vymyslena cisla.') {
  return `<figure class="welcome-minidemo" data-minidemo="${kind}"><p>${inner}</p><img src="/a.png" width="1047" height="365" alt="Obrazek 12"/></figure>`;
}

function page(figures) {
  return `<!doctype html><html><body><main>${figures.join('')}</main></body></html>`;
}

// A fake dist: entry imports a shared chunk; Welcome imports the same shared
// chunk plus its own; the live demo chunk is a dynamic import of Welcome.
function makeDist({ welcomeCode = 'const a = 1;', entryCode = filler(1, 4000), figures = KINDS.map((k) => figure(k)), pages = ['index.html', 'en/index.html', 'de/index.html'] } = {}) {
  const dist = mkdtempSync(join(tmpdir(), 'landing-guard-'));
  mkdirSync(join(dist, '.vite'), { recursive: true });
  mkdirSync(join(dist, 'assets'), { recursive: true });
  const manifest = {
    'index.html': { file: 'assets/entry.js', imports: ['shared'], dynamicImports: ['src/pages/Welcome.jsx'] },
    shared: { file: 'assets/shared.js' },
    'src/pages/Welcome.jsx': { file: 'assets/welcome.js', imports: ['shared'], dynamicImports: ['src/demo/live.jsx'] },
    'src/demo/live.jsx': { file: 'assets/live.js' },
  };
  writeFileSync(join(dist, '.vite/manifest.json'), JSON.stringify(manifest));
  writeFileSync(join(dist, 'assets/entry.js'), entryCode);
  writeFileSync(join(dist, 'assets/shared.js'), filler(2, 3000));
  writeFileSync(join(dist, 'assets/welcome.js'), `${welcomeCode}\n${filler(3, 2000)}`);
  writeFileSync(join(dist, 'assets/live.js'), `recharts-surface Vanguard S&P 500 UCITS ETF portfyl-showcase-v1 ${filler(4, 2000)}`);
  for (const file of pages) {
    mkdirSync(dirname(join(dist, 'prerendered', file)), { recursive: true });
    writeFileSync(join(dist, 'prerendered', file), page(figures));
  }
  return dist;
}

const baselineFor = (dist, slack = {}) => {
  const measured = measureLanding(dist);
  return { measured_on: 'test', entry_gzip_bytes: measured.entry_gzip_bytes, welcome_closure_gzip_bytes: measured.welcome_closure_gzip_bytes, limit_increase_bytes: 5120, ...slack };
};

test('passes when forbidden code is only in dynamic imports and sizes match the baseline', () => {
  const dist = makeDist();
  try {
    const result = checkLanding(dist, { baseline: baselineFor(dist) });
    assert.deepEqual(result.violations, []);
    assert.equal(result.figures.length, 3);
  } finally { rmSync(dist, { recursive: true, force: true }); }
});

for (const needle of ['recharts-surface', 'Vanguard S&P 500 UCITS ETF', 'portfyl-showcase-v1']) {
  test(`fails when the static Welcome graph contains ${needle}`, () => {
    const dist = makeDist({ welcomeCode: `const x = "${needle}";` });
    try {
      const { violations } = checkLanding(dist, { baseline: baselineFor(dist) });
      assert.ok(violations.some((message) => message.includes(needle)), violations.join('\n'));
    } finally { rmSync(dist, { recursive: true, force: true }); }
  });
}

test('fails when the entry grows over the baseline plus the limit', () => {
  const dist = makeDist();
  try {
    const baseline = baselineFor(dist);
    baseline.entry_gzip_bytes -= 6000;
    const { violations } = checkLanding(dist, { baseline });
    assert.ok(violations.some((message) => /entry/i.test(message)), violations.join('\n'));
  } finally { rmSync(dist, { recursive: true, force: true }); }
});

test('fails when the Welcome closure grows over the baseline plus the limit', () => {
  const dist = makeDist();
  try {
    const baseline = baselineFor(dist);
    baseline.welcome_closure_gzip_bytes -= 6000;
    const { violations } = checkLanding(dist, { baseline });
    assert.ok(violations.some((message) => /welcome/i.test(message)), violations.join('\n'));
  } finally { rmSync(dist, { recursive: true, force: true }); }
});

test('allows growth that stays inside the limit', () => {
  const dist = makeDist();
  try {
    const baseline = baselineFor(dist);
    baseline.entry_gzip_bytes -= 5000;
    baseline.welcome_closure_gzip_bytes -= 5000;
    assert.deepEqual(checkLanding(dist, { baseline }).violations, []);
  } finally { rmSync(dist, { recursive: true, force: true }); }
});

test('fails when a prerendered page has fewer or more than five mini demo frames', () => {
  const dist = makeDist({ figures: KINDS.slice(0, 4).map((k) => figure(k)) });
  try {
    const { violations } = checkLanding(dist, { baseline: baselineFor(dist) });
    assert.ok(violations.some((message) => message.includes('index.html') && message.includes('5')), violations.join('\n'));
  } finally { rmSync(dist, { recursive: true, force: true }); }
  const extra = makeDist({ figures: [...KINDS, 'stock'].map((k) => figure(k)) });
  try {
    assert.ok(checkLanding(extra, { baseline: baselineFor(extra) }).violations.length > 0);
  } finally { rmSync(extra, { recursive: true, force: true }); }
});

test('fails when a prerendered page is missing', () => {
  const dist = makeDist({ pages: ['index.html', 'en/index.html'] });
  try {
    const { violations } = checkLanding(dist, { baseline: baselineFor(dist) });
    assert.ok(violations.some((message) => message.includes('de/index.html')), violations.join('\n'));
  } finally { rmSync(dist, { recursive: true, force: true }); }
});

test('fails when the text of a frame holds a digit, but attributes and entities do not count', () => {
  const dist = makeDist({ figures: KINDS.map((k, i) => figure(k, i === 2 ? 'Vynos 12 procent' : 'Bez cisel, it&#x27;s fine')) });
  try {
    const { violations } = checkLanding(dist, { baseline: baselineFor(dist) });
    assert.ok(violations.some((message) => /digit|číslic|cislic/i.test(message) && message.includes('performance')), violations.join('\n'));
    assert.equal(violations.filter((message) => /digit/i.test(message)).length, 3);
  } finally { rmSync(dist, { recursive: true, force: true }); }
  const clean = makeDist({ figures: KINDS.map((k) => figure(k, 'Bez cisel, it&#x27;s fine &amp; more')) });
  try {
    assert.deepEqual(checkLanding(clean, { baseline: baselineFor(clean) }).violations, []);
  } finally { rmSync(clean, { recursive: true, force: true }); }
});

test('extractFigures keeps nested figures inside their block', () => {
  const html = '<figure class="welcome-minidemo" data-minidemo="a"><figure class="welcome-shot">x</figure>tail</figure><figure class="welcome-shot">no</figure>';
  const blocks = extractFigures(html);
  assert.equal(blocks.length, 1);
  assert.ok(blocks[0].includes('tail'));
});

test('--write-baseline skips the figure check and writes the measured numbers', () => {
  const dist = makeDist({ figures: [] });
  const out = join(dist, 'baseline.json');
  try {
    const run = spawnSync(process.execPath, [SCRIPT, dist, '--write-baseline', out], { encoding: 'utf8' });
    assert.equal(run.status, 0, run.stderr);
    const written = JSON.parse(readFileSync(out, 'utf8'));
    const measured = measureLanding(dist);
    assert.equal(written.entry_gzip_bytes, measured.entry_gzip_bytes);
    assert.equal(written.welcome_closure_gzip_bytes, measured.welcome_closure_gzip_bytes);
    assert.equal(written.limit_increase_bytes, 5120);
    assert.equal(typeof written.measured_on, 'string');
    assert.ok(written.measured_on.length > 0);
  } finally { rmSync(dist, { recursive: true, force: true }); }
});

test('the CLI exits 1 with a clear message on a violation and 0 when clean', () => {
  const bad = makeDist({ welcomeCode: 'const x = "recharts-surface";' });
  const good = makeDist();
  try {
    const baselinePath = join(good, 'baseline.json');
    writeFileSync(baselinePath, JSON.stringify(baselineFor(good)));
    const failing = spawnSync(process.execPath, [SCRIPT, bad, '--baseline', baselinePath], { encoding: 'utf8' });
    assert.equal(failing.status, 1);
    assert.match(failing.stderr, /recharts-surface/);
    const passing = spawnSync(process.execPath, [SCRIPT, good, '--baseline', baselinePath], { encoding: 'utf8' });
    assert.equal(passing.status, 0, passing.stderr);
    assert.equal(JSON.parse(passing.stdout).ok, true);
  } finally {
    rmSync(bad, { recursive: true, force: true });
    rmSync(good, { recursive: true, force: true });
  }
});
