import path from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { sourcePath } from "./sourcePath";

describe("sourcePath", () => {
  it("uses the real filesystem path of a file: URL", () => {
    // On Linux CI `new URL(relative, import.meta.url)` is a file: URL whose
    // pathname is already absolute (/home/runner/...). Stripping its leading
    // slash and resolving against cwd doubled the path and broke CI.
    const absolute = path.resolve("src", "index.css");
    expect(sourcePath(pathToFileURL(absolute))).toBe(absolute);
  });

  it("resolves a root-relative pathname against the frontend root", () => {
    expect(sourcePath(new URL("http://localhost:3000/src/index.css"))).toBe(
      path.resolve("src", "index.css"),
    );
  });

  it("decodes escaped characters", () => {
    expect(sourcePath(new URL("http://localhost:3000/src/my%20file.css"))).toBe(
      path.resolve("src", "my file.css"),
    );
  });
});
