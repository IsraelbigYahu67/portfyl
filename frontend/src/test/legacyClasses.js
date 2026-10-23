import { readFile } from "node:fs/promises";
import { sourcePath } from "./sourcePath";

// Tailwind palette classes that bypass the Clay tokens (bg-white,
// text-slate-500, bg-[#fff], ...). Pass `new URL("./File.jsx", import.meta.url)`;
// an empty array means the file only uses token-based colors.
const LEGACY_COLOR_CLASS =
  /\b(?:bg|text|border|ring|fill|stroke|from|via|to)-(?:white|(?:gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3})(?:\/\d+)?\b|\b(?:bg|text|border)-\[#[0-9a-fA-F]{3,8}\]/g;

export async function legacyColorClassesIn(url) {
  const source = await readFile(sourcePath(url), "utf-8");
  return source.match(LEGACY_COLOR_CLASS) ?? [];
}
