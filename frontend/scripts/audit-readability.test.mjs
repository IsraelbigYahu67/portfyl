import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { auditReadability } from "./audit-readability.mjs";

function withFixture(files, fn) {
  const root = mkdtempSync(join(tmpdir(), "audit-readability-"));
  try {
    for (const [name, content] of Object.entries(files)) {
      writeFileSync(join(root, name), content);
    }
    return fn(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test("flags a financial value rendered at a sub-floor size", () => {
  const violations = withFixture(
    { "Widget.jsx": `export default () => <span className="financial-data text-[10px]">$1</span>;` },
    (root) => auditReadability(root)
  );
  assert.equal(violations.length, 1);
  assert.match(violations[0].path, /Widget\.jsx$/);
  assert.equal(violations[0].token, "text-[10px]");
});

test("passes a component already at the metadata floor", () => {
  const violations = withFixture(
    { "Widget.jsx": `export default () => <span className="financial-meta">as of today</span>;` },
    (root) => auditReadability(root)
  );
  assert.equal(violations.length, 0);
});

test("passes a CSS font-size at or above 12px but flags one below it", () => {
  const violations = withFixture(
    { "styles.css": `.ok { font-size: 12px; } .bad { font-size: 10px; }` },
    (root) => auditReadability(root)
  );
  assert.equal(violations.length, 1);
  assert.match(violations[0].path, /styles\.css$/);
});

test("skips test files entirely", () => {
  const violations = withFixture(
    { "Widget.test.jsx": `export default () => <span className="text-[9px]">x</span>;` },
    (root) => auditReadability(root)
  );
  assert.equal(violations.length, 0);
});

test("skips sr-only (visually hidden) text regardless of declared size", () => {
  const violations = withFixture(
    { "Widget.jsx": `export default () => <span className="sr-only text-[8px]">hidden</span>;` },
    (root) => auditReadability(root)
  );
  assert.equal(violations.length, 0);
});

test("passes a fixture matching an explicit, documented allowlist entry", () => {
  const violations = withFixture(
    { "Decorative.jsx": `export default () => <span className="text-[10px]">···</span>;` },
    (root) =>
      auditReadability(root, [
        { path: "Decorative.jsx", token: "text-[10px]", reason: "decorative ellipsis marker in a fixture, never a real value" },
      ])
  );
  assert.equal(violations.length, 0);
});
