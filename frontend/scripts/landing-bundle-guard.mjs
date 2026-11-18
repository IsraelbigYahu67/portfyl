// Guard for the landing page's weight and its prerendered mini demo frames.
//
//   node scripts/landing-bundle-guard.mjs <dist> [--baseline <json>] [--write-baseline <json>]
//
// Checks (cloud build, after prerender):
//   1. The static graph of src/pages/Welcome.jsx holds no Recharts, no sample
//      ETF name and no showcase data: those belong in the lazy demo chunks.
//   2. The initial entry and the Welcome closure each grow by at most
//      `limit_increase_bytes` gzip over the baseline measured on main.
//   3. Each prerendered page (cs, en, de) has exactly five mini demo frames
//      and no digit in their text (attributes and entities do not count).
// `--write-baseline` measures only and writes the baseline file.
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { gzipSync } from 'node:zlib';
import { collectInitialAssets } from './measure-initial-bundle.mjs';

export const WELCOME_ENTRY = 'src/pages/Welcome.jsx';
export const FORBIDDEN_IN_WELCOME = ['recharts-surface', 'Vanguard S&P 500 UCITS ETF', 'portfyl-showcase-v1'];
export const PRERENDERED_PAGES = ['index.html', 'en/index.html', 'de/index.html'];
export const FIGURES_PER_PAGE = 5;
export const DEFAULT_LIMIT_INCREASE_BYTES = 5120;

const FIGURE_START = '<figure class="welcome-minidemo';

function gzipSize(directory, files) {
  return files.reduce((sum, file) => sum + gzipSync(readFileSync(resolve(directory, file)), { level: 9 }).length, 0);
}

function readManifest(directory) {
  return JSON.parse(readFileSync(resolve(directory, '.vite/manifest.json'), 'utf8'));
}

export function measureLanding(directory) {
  const manifest = readManifest(directory);
  const entryAssets = collectInitialAssets(manifest).assets;
  const welcomeAssets = collectInitialAssets(manifest, WELCOME_ENTRY).assets;
  return {
    entry_gzip_bytes: gzipSize(directory, entryAssets),
    welcome_closure_gzip_bytes: gzipSize(directory, welcomeAssets),
    welcome_assets: welcomeAssets,
  };
}

// Every `<figure class="welcome-minidemo...">...</figure>` block, nested
// figures included (balanced by counting open and close tags).
export function extractFigures(html) {
  const blocks = [];
  let from = 0;
  for (;;) {
    const start = html.indexOf(FIGURE_START, from);
    if (start === -1) return blocks;
    const tag = /<(\/?)figure\b/g;
    tag.lastIndex = start;
    let depth = 0, end = -1, match;
    while ((match = tag.exec(html))) {
      depth += match[1] ? -1 : 1;
      if (depth === 0) { end = html.indexOf('>', match.index) + 1; break; }
    }
    if (end === -1) { blocks.push(html.slice(start)); return blocks; }
    blocks.push(html.slice(start, end));
    from = end;
  }
}

const kindOf = (block) => /data-minidemo="([^"]*)"/.exec(block)?.[1] ?? 'unknown';

// What a reader sees: tags (and so attributes) and character entities removed.
function visibleText(block) {
  return block.replace(/<[^>]*>/g, ' ').replace(/&#?\w+;/g, '');
}

export function checkLanding(directory, { baseline = null, skipFigures = false } = {}) {
  const violations = [];
  const measured = measureLanding(directory);

  for (const file of measured.welcome_assets) {
    if (!file.endsWith('.js')) continue;
    const code = readFileSync(resolve(directory, file), 'utf8');
    for (const needle of FORBIDDEN_IN_WELCOME) {
      if (code.includes(needle)) violations.push(`${file} is in the static graph of ${WELCOME_ENTRY} but contains "${needle}"; load it lazily from the mini demo chunks.`);
    }
  }

  if (baseline) {
    const limit = baseline.limit_increase_bytes ?? DEFAULT_LIMIT_INCREASE_BYTES;
    for (const [key, label] of [['entry_gzip_bytes', 'Initial entry'], ['welcome_closure_gzip_bytes', 'Welcome closure']]) {
      const allowed = baseline[key] + limit;
      if (measured[key] > allowed) {
        violations.push(`${label} is ${measured[key]} B gzip, over the baseline ${baseline[key]} B + ${limit} B limit (${measured[key] - allowed} B too much).`);
      }
    }
  }

  const figures = [];
  if (!skipFigures) {
    for (const file of PRERENDERED_PAGES) {
      const path = resolve(directory, 'prerendered', file);
      if (!existsSync(path)) { violations.push(`Prerendered page prerendered/${file} is missing.`); continue; }
      const blocks = extractFigures(readFileSync(path, 'utf8'));
      figures.push({ page: file, count: blocks.length, kinds: blocks.map(kindOf) });
      if (blocks.length !== FIGURES_PER_PAGE) {
        violations.push(`Prerendered ${file} has ${blocks.length} mini demo frames, expected exactly ${FIGURES_PER_PAGE}.`);
      }
      for (const block of blocks) {
        if (/\d/.test(visibleText(block))) {
          violations.push(`Prerendered ${file}: the "${kindOf(block)}" mini demo frame has a digit in its text; the static HTML must hold no numbers.`);
        }
      }
    }
  }
  return { measured, figures, violations };
}

function gitHead() {
  try { return execFileSync('git', ['rev-parse', '--short', 'HEAD'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim() || 'unknown'; }
  catch { return 'unknown'; }
}

function parseArgs(argv) {
  const options = { directory: 'dist', baseline: null, writeBaseline: null };
  const positional = [];
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--baseline') options.baseline = argv[++i];
    else if (argv[i] === '--write-baseline') options.writeBaseline = argv[++i];
    else positional.push(argv[i]);
  }
  if (positional[0]) options.directory = positional[0];
  return options;
}

export function main(argv) {
  const options = parseArgs(argv);
  if (options.writeBaseline) {
    const { measured, violations } = checkLanding(options.directory, { skipFigures: true });
    if (violations.length) throw new Error(violations.join('\n'));
    const baseline = {
      measured_on: gitHead(),
      entry_gzip_bytes: measured.entry_gzip_bytes,
      welcome_closure_gzip_bytes: measured.welcome_closure_gzip_bytes,
      limit_increase_bytes: DEFAULT_LIMIT_INCREASE_BYTES,
    };
    writeFileSync(options.writeBaseline, `${JSON.stringify(baseline, null, 2)}\n`);
    process.stdout.write(`${JSON.stringify(baseline, null, 2)}\n`);
    return;
  }
  const baseline = options.baseline ? JSON.parse(readFileSync(options.baseline, 'utf8')) : null;
  const result = checkLanding(options.directory, { baseline });
  const { welcome_assets: _assets, ...numbers } = result.measured;
  const report = { ok: result.violations.length === 0, baseline, ...numbers, figures: result.figures, violations: result.violations };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (result.violations.length) {
    process.stderr.write(`Landing bundle guard failed:\n- ${result.violations.join('\n- ')}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { main(process.argv.slice(2)); }
  catch (error) { process.stderr.write(`Landing bundle guard failed: ${error.message}\n`); process.exitCode = 1; }
}
