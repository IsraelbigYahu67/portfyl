import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

// Exact { path, token, reason } entries only -- never a whole directory or a
// wildcard. Every entry must name a specific file (repo-relative, forward
// slashes) and the exact matched token it excuses. Per the readability plan
// (docs/superpowers/plans/2026-09-19-portfyl-readability-system.md), never
// allowlist a financial value, input, action, axis, or legend -- only
// genuinely decorative, non-data text.
export const ALLOWLIST = [];

const SCANNABLE_EXTENSIONS = [".jsx", ".js", ".css"];
const SKIP_DIRS = new Set(["node_modules", "dist", ".git"]);
const CLASS_TOKEN_RE = /text-\[(8|9|10|11)px\]/g;
const CSS_FONT_SIZE_RE = /font-size:\s*(\d+(?:\.\d+)?)px/g;

function isTestFile(relPath) {
  return /\.test\.[jt]sx?$/.test(relPath) || /\.test\.mjs$/.test(relPath);
}

function toPosix(p) {
  return p.split("\\").join("/");
}

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    const stats = statSync(full);
    if (stats.isDirectory()) {
      walk(full, files);
    } else if (SCANNABLE_EXTENSIONS.includes(entry.slice(entry.lastIndexOf("."))) && !isTestFile(entry)) {
      files.push(full);
    }
  }
  return files;
}

// Any className string containing `sr-only` is visually hidden -- its
// declared pixel size never reaches a screen, so it's exempt by definition,
// not by allowlist.
function isInSrOnlyClass(source, matchIndex) {
  const lineStart = source.lastIndexOf("\n", matchIndex) + 1;
  const lineEnd = source.indexOf("\n", matchIndex);
  const line = source.slice(lineStart, lineEnd === -1 ? source.length : lineEnd);
  return /\bsr-only\b/.test(line);
}

function lineNumberAt(source, index) {
  let line = 1;
  for (let i = 0; i < index; i++) if (source[i] === "\n") line++;
  return line;
}

function scanFile(root, filePath) {
  const relPath = toPosix(relative(root, filePath));
  const source = readFileSync(filePath, "utf-8");
  const violations = [];
  const isCss = filePath.endsWith(".css");

  const pattern = isCss ? CSS_FONT_SIZE_RE : CLASS_TOKEN_RE;
  pattern.lastIndex = 0;
  let match;
  while ((match = pattern.exec(source))) {
    if (isCss && Number(match[1]) >= 12) continue;
    if (!isCss && isInSrOnlyClass(source, match.index)) continue;
    const token = match[0];
    violations.push({ path: relPath, line: lineNumberAt(source, match.index), token });
  }
  return violations;
}

/**
 * Scans `root` for forbidden critical-size patterns:
 * `text-[8px]` through `text-[11px]` class utilities, and CSS `font-size`
 * declarations below 12px. Returns an array of { path, line, token }
 * violations not excused by `allowlist` (defaults to the module's own
 * ALLOWLIST). `sr-only` text and *.test.* files are always exempt.
 */
export function auditReadability(root, allowlist = ALLOWLIST) {
  const files = walk(resolve(root));
  const allExcused = (v) => allowlist.some((e) => e.path === v.path && e.token === v.token);
  return files.flatMap((file) => scanFile(root, file)).filter((v) => !allExcused(v));
}

function main() {
  const root = process.argv[2] || "src";
  const violations = auditReadability(root);
  if (violations.length === 0) {
    console.log(`audit-readability: 0 violations in ${root}`);
    return;
  }
  console.error(`audit-readability: ${violations.length} violation(s) below the readability floor:`);
  for (const v of violations) {
    console.error(`  ${v.path}:${v.line}  ${v.token}`);
  }
  process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main();
}
