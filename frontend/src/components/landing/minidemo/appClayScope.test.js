import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { APP_CLAY_SCOPE } from "./appClayScope";
import { CLAY_TOKENS } from "../../../lib/themeTokens";
import { sourcePath } from "../../../test/sourcePath";

// The warm (Premium/Clay) branch of applyAppearance(): everything between
// `if (warm) {` and its first `return;`.
async function warmBranch() {
  const source = await readFile(sourcePath(new URL("../../../App.jsx", import.meta.url)), "utf-8");
  const start = source.indexOf("if (warm) {");
  const end = source.indexOf("return;", start);
  expect(start).toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe("APP_CLAY_SCOPE", () => {
  it("sets every variable the app sets for the Clay look, with the same values", async () => {
    const branch = await warmBranch();
    const setters = [...branch.matchAll(/s\.setProperty\("(--[\w-]+)",\s*([^)]+)\)/g)].map(([, name, value]) => [name, value.trim()]);
    expect(setters.length).toBeGreaterThan(15);
    for (const [name, value] of setters) {
      expect(APP_CLAY_SCOPE, name).toHaveProperty([name]);
      const token = /^t\.(\w+)$/.exec(value)?.[1];
      if (token) expect(APP_CLAY_SCOPE[name], name).toBe(CLAY_TOKENS[token]);
    }
  });

  it("covers the eight chart colors in order, from CLAY_TOKENS", () => {
    for (let i = 1; i <= 8; i += 1) expect(APP_CLAY_SCOPE[`--chart-${i}`]).toBe(CLAY_TOKENS.chart[i - 1]);
  });

  it("uses the Clay light brand for the active sidebar tint, like the app", () => {
    expect(APP_CLAY_SCOPE["--sidebar-active"]).toBe(CLAY_TOKENS.brandLight);
  });

  it("leaves the landing's own paper color out", () => {
    expect(Object.keys(APP_CLAY_SCOPE)).not.toContain("--landing-paper");
  });

  it("holds no hex color of its own in its source", async () => {
    const source = await readFile(sourcePath(new URL("./appClayScope.js", import.meta.url)), "utf-8");
    expect(source.match(/#[0-9a-fA-F]{3,8}\b/g)).toBeNull();
  });
});
