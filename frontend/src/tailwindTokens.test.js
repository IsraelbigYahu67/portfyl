import postcss from "postcss";
import tailwindcss from "tailwindcss";

import config from "../tailwind.config.js";

// Every theme color is a CSS variable. Tailwind drops opacity modifiers on a
// bare var(--x) without a word, so this compiles real classes and checks the
// CSS they produce (see the token() helper in tailwind.config.js).
async function compile(classes) {
  const result = await postcss([
    tailwindcss({ ...config, content: [{ raw: `<div class="${classes.join(" ")}"></div>` }] }),
  ]).process("@tailwind utilities;", { from: undefined });
  return result.css;
}

const escape = (className) => className.replace(/[/.[\]]/g, (char) => `\\${char}`);

describe("Tailwind theme colors", () => {
  it("generate CSS for opacity modifiers on every token", async () => {
    const tokens = ["surface", "surface-card", "surface-card-elevated", "surface-hover", "surface-border",
      "brand", "brand-dim", "brand-light", "ink", "muted", "hairline", "gain", "loss"];
    const classes = tokens.flatMap((name) => [`bg-${name}/10`, `border-${name}/30`, `text-${name}/80`]);
    const css = await compile([...classes, "ring-brand/30"]);

    for (const className of [...classes, "ring-brand/30"]) {
      expect(css, className).toContain(`.${escape(className)}`);
    }
    expect(css).toMatch(/\.bg-loss\\\/10\s*\{[^}]*color-mix\(in srgb, var\(--loss\) calc\(0\.1 \* 100%\), transparent\)/);
  });

  it("keep the exact token color when there is no modifier", async () => {
    const css = await compile(["bg-loss", "text-ink"]);

    expect(css).toMatch(/\.bg-loss\s*\{[^}]*--tw-bg-opacity:\s*1;[^}]*color-mix\(in srgb, var\(--loss\) calc\(var\(--tw-bg-opacity, 1\) \* 100%\), transparent\)/);
    expect(css).toMatch(/\.text-ink\s*\{[^}]*--tw-text-opacity:\s*1;[^}]*var\(--ink\)/);
  });
});
