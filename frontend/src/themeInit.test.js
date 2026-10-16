import { readFile } from "node:fs/promises";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sourcePath } from "./test/sourcePath";

// The production CSP (backend/security_headers.py) has no 'unsafe-inline' in
// script-src, so the pre-paint theme snippet must live in a same-origin file.

// See test/sourcePath.js for how the asset URL becomes a filesystem path.
async function readSource(relativePath) {
  return readFile(sourcePath(new URL(relativePath, import.meta.url)), "utf-8");
}

function parseIndexHtml(html) {
  return new DOMParser().parseFromString(html, "text/html");
}

describe("index.html", () => {
  it("has no inline scripts the CSP would block", async () => {
    const doc = parseIndexHtml(await readSource("../index.html"));
    const inline = [...doc.querySelectorAll("script")].filter((s) => !s.hasAttribute("src"));
    expect(inline).toEqual([]);
  });

  it("loads theme-init.js synchronously in <head>, before the app module", async () => {
    const doc = parseIndexHtml(await readSource("../index.html"));
    const themeInit = doc.head.querySelector('script[src="/theme-init.js"]');
    expect(themeInit).not.toBeNull();
    for (const attr of ["type", "async", "defer"]) {
      expect(themeInit.hasAttribute(attr)).toBe(false);
    }
    const scripts = [...doc.querySelectorAll("script")];
    const appModule = doc.querySelector('script[type="module"]');
    expect(scripts.indexOf(themeInit)).toBeLessThan(scripts.indexOf(appModule));
  });
});

describe("theme-init.js", () => {
  let code;
  let prefersDark;

  beforeEach(async () => {
    code = await readSource("../public/theme-init.js");
    prefersDark = false;
    vi.stubGlobal("matchMedia", (query) => ({
      matches: query === "(prefers-color-scheme: dark)" && prefersDark,
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    const el = document.documentElement;
    el.classList.remove("dark");
    el.removeAttribute("style");
  });

  const run = () => new Function(code)();
  const isDark = () => document.documentElement.classList.contains("dark");

  it("applies dark for a saved sb_theme=dark", () => {
    localStorage.setItem("sb_theme", "dark");
    run();
    expect(isDark()).toBe(true);
    expect(document.documentElement.style.getPropertyValue("--bg")).toBe("#020617");
  });

  it("stays light for a saved sb_theme=light even if the OS prefers dark", () => {
    prefersDark = true;
    localStorage.setItem("sb_theme", "light");
    run();
    expect(isDark()).toBe(false);
  });

  it("follows the OS preference when nothing is saved", () => {
    prefersDark = true;
    run();
    expect(isDark()).toBe(true);
  });

  it("does not throw when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    try {
      expect(run).not.toThrow();
      expect(isDark()).toBe(false);
    } finally {
      vi.restoreAllMocks();
    }
  });
});
