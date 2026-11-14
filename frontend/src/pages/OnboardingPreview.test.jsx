import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { useRef } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { ONBOARDING_CHOICE_KEYS } from "../components/onboarding/OnboardingView";
import { resetRouteFocusAnnouncerForTests, useRouteFocusAnnouncer } from "../hooks/useRouteFocusAnnouncer";
import { ONBOARDING_PREVIEW_PATH } from "../lib/routes";
import { legacyColorClassesIn } from "../test/legacyClasses";
import { sourcePath } from "../test/sourcePath";

import OnboardingPreview, { OUTCOMES, PREVIEW_EXIT_PATH } from "./OnboardingPreview";

// ---------------------------------------------------------------------------
// Import-graph guard. The preview must stay pure frontend, so instead of
// grepping one file it walks every module the preview can load.
// ---------------------------------------------------------------------------

const SCRIPT_EXTENSIONS = [".js", ".jsx", ".mjs", ".ts", ".tsx"];
// `import x from "y"`, `import { a,\n b } from "y"`, `export { a } from "y"`, `export * from "y"`.
const FROM_SPECIFIER = /\bfrom\s*(["'])([^"'\r\n]+)\1/g;
// `import "y"` (side effect only).
const SIDE_EFFECT_SPECIFIER = /\bimport\s*(["'])([^"'\r\n]+)\1/g;
// `import("y")`, `require("y")` with a literal argument.
const CALL_SPECIFIER = /\b(?:import|require)\s*\(\s*(["'`])([^"'`\r\n]+)\1\s*\)/g;
// Every `import(` / `require(`; more of these than literal calls means one
// loads a computed specifier the walk cannot follow.
const ANY_CALL = /\b(?:import|require)\s*\(/g;

// Paths relative to src/ (posix separators).
const FORBIDDEN_MODULES = [
  [/^api(?:\.[cm]?[jt]sx?)?$|^api\//, "the API client"],
  [/^App(?:\.[cm]?[jt]sx?)?$/, "the portfolio context"],
  [/^analytics(?:\/|$)/, "analytics"],
];
// Bare packages are checked, never followed.
const FORBIDDEN_PACKAGE = /^(?:axios|firebase|@firebase|@sentry)(?:\/|$)/;
// Translation dictionaries (i18n/messages/*.js) are data: their English keys
// can read like `import "...` to the patterns above. Instead of being scanned
// they must be exactly one exported object of string pairs, so no code can
// hide in one.
const DATA_MODULE = /^i18n\/messages\/[a-z]{2}\.js$/;
const STRING_LITERAL = /"(?:[^"\\\r\n]|\\.)*"/g;
// `//` comments are allowed anywhere (a line comment cannot hide code, and the
// onboarding-flow tasks head their appended dictionary block with one).
const STRING_TABLE = /^(?:\s*\/\/[^\r\n]*)*\s*export default\s*\{(?:\s*(?:\/\/[^\r\n]*|""\s*:\s*""\s*,?))*\s*\}\s*;?\s*$/;

function packageName(specifier) {
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
}

function resolveRelative(fromFile, specifier, isFile) {
  const base = path.resolve(path.dirname(fromFile), specifier.replace(/[?#].*$/, ""));
  const candidates = [
    base,
    ...SCRIPT_EXTENSIONS.map((extension) => base + extension),
    ...SCRIPT_EXTENSIONS.map((extension) => path.join(base, `index${extension}`)),
  ];
  return candidates.find(isFile) ?? null;
}

// Breadth-first walk of `entry`'s import graph. Relative specifiers are
// resolved like Vite does (.js/.jsx/.ts/.tsx, then index.*) and followed;
// bare ones must be installed packages and are only checked. Anything the
// walk cannot resolve -- a Vite alias such as @edition-manifest, a
// root-relative path, a computed dynamic import -- is reported, so the guard
// fails closed instead of silently skipping a branch.
function scanImportGraph(entry, { srcRoot, readSource, isFile, packageExists }) {
  const label = (file) => path.relative(srcRoot, file).split(path.sep).join("/");
  const importedBy = new Map([[entry, null]]);
  const chain = (file) => {
    const files = [];
    for (let current = file; current; current = importedBy.get(current)) files.unshift(label(current));
    return files.join(" -> ");
  };
  const visited = [];
  const violations = [];
  const queue = [entry];

  while (queue.length > 0) {
    const file = queue.shift();
    visited.push(label(file));
    const source = readSource(file);
    if (DATA_MODULE.test(label(file))) {
      if (!STRING_TABLE.test(source.replace(STRING_LITERAL, '""'))) {
        violations.push(`${chain(file)}: a translation dictionary must be a plain object of strings`);
      }
      continue;
    }
    const calls = [...source.matchAll(CALL_SPECIFIER)];
    if ((source.match(ANY_CALL) ?? []).length > calls.length) {
      violations.push(`${chain(file)}: dynamic import with a computed specifier`);
    }
    const specifiers = [
      ...source.matchAll(FROM_SPECIFIER),
      ...source.matchAll(SIDE_EFFECT_SPECIFIER),
      ...calls,
    ].map((match) => match[2]);

    for (const specifier of specifiers) {
      if (specifier.startsWith(".")) {
        const target = resolveRelative(file, specifier, isFile);
        if (!target) {
          violations.push(`${chain(file)}: cannot resolve "${specifier}"`);
          continue;
        }
        const forbidden = FORBIDDEN_MODULES.find(([pattern]) => pattern.test(label(target)));
        if (forbidden) {
          violations.push(`${chain(file)} -> ${label(target)} (${forbidden[1]})`);
        } else if (!importedBy.has(target)) {
          importedBy.set(target, file);
          if (SCRIPT_EXTENSIONS.includes(path.extname(target))) queue.push(target);
        }
      } else if (FORBIDDEN_PACKAGE.test(specifier)) {
        violations.push(`${chain(file)} -> ${specifier} (forbidden package)`);
      } else if (!packageExists(packageName(specifier))) {
        violations.push(`${chain(file)}: "${specifier}" is not an installed package (alias or root-relative path?) and cannot be followed`);
      }
    }
  }
  return { visited, violations };
}

const PREVIEW_ENTRY = sourcePath(new URL("./OnboardingPreview.jsx", import.meta.url));
const SRC_ROOT = path.resolve(path.dirname(PREVIEW_ENTRY), "..");
const FRONTEND_ROOT = path.dirname(SRC_ROOT);

function scanFromDisk(entry) {
  return scanImportGraph(entry, {
    srcRoot: SRC_ROOT,
    readSource: (file) => readFileSync(file, "utf8"),
    isFile: (file) => existsSync(file) && statSync(file).isFile(),
    packageExists: (name) => existsSync(path.join(FRONTEND_ROOT, "node_modules", name, "package.json")),
  });
}

describe("OnboardingPreview import guard", () => {
  it("never reaches the API client, portfolio context, analytics or a tracking SDK", () => {
    const { visited, violations } = scanFromDisk(PREVIEW_ENTRY);

    expect(violations).toEqual([]);
    // The walk really followed the preview's own imports, transitively.
    expect(visited).toEqual(expect.arrayContaining([
      "pages/OnboardingPreview.jsx",
      "components/onboarding/OnboardingView.jsx",
      "components/ui/Badge.jsx",
      "lib/onboardingBrokers.js",
      "hooks/useRouteFocusAnnouncer.js",
    ]));
  });

  it("reports the real onboarding page, which does use the API", () => {
    const onboarding = sourcePath(new URL("./Onboarding.jsx", import.meta.url));
    const { violations } = scanFromDisk(onboarding);

    expect(violations).toEqual(expect.arrayContaining([
      "pages/Onboarding.jsx -> api.js (the API client)",
      "pages/Onboarding.jsx -> App.jsx (the portfolio context)",
    ]));
  });

  describe("on a synthetic graph", () => {
    const fixtureRoot = path.resolve("import-guard-fixture", "src");
    const at = (relative) => path.join(fixtureRoot, ...relative.split("/"));
    const scan = (files) => {
      const sources = new Map(Object.entries(files).map(([relative, source]) => [at(relative), source]));
      return scanImportGraph(at("pages/Entry.jsx"), {
        srcRoot: fixtureRoot,
        readSource: (file) => sources.get(file),
        isFile: (file) => sources.has(file),
        packageExists: (name) => ["react", "axios", "firebase", "@sentry/react"].includes(name),
      }).violations;
    };

    it("passes a clean graph", () => {
      expect(scan({
        "pages/Entry.jsx": 'import { useState } from "react";\nimport View from "../components/View";\nimport "./entry.css";\nconst load = () => import("../i18n/messages/cs.js");',
        "components/View.jsx": 'export { helper } from "../lib/helper";',
        "lib/helper.js": "export const helper = 1;",
        "pages/entry.css": "",
        "i18n/messages/cs.js": '// Czech.\nexport default {\n  "CSV import": "import \\"CSV\\"",\n  // a heading comment inside the table\n  "Save": "Uložit",\n  // trailing comment\n};\n',
      })).toEqual([]);
    });

    it.each([
      ["a direct import with an extension", { "pages/Entry.jsx": 'import { get } from "../api.js";', "api.js": "" }, "pages/Entry.jsx -> api.js (the API client)"],
      ["a directory index", { "pages/Entry.jsx": 'import { get } from "../api";', "api/index.js": "" }, "pages/Entry.jsx -> api/index.js (the API client)"],
      [
        "a transitive re-export",
        {
          "pages/Entry.jsx": 'import View from "../components/View";',
          "components/View.jsx": 'export { usePortfolio } from "../App.jsx";',
          "App.jsx": "",
        },
        "pages/Entry.jsx -> components/View.jsx -> App.jsx (the portfolio context)",
      ],
      ["a side-effect import", { "pages/Entry.jsx": 'import "../analytics/track";', "analytics/track.js": "" }, "pages/Entry.jsx -> analytics/track.js (analytics)"],
      [
        "a multi-line import",
        { "pages/Entry.jsx": 'import {\n  record,\n  flush,\n} from "../analytics/index.js";', "analytics/index.js": "" },
        "pages/Entry.jsx -> analytics/index.js (analytics)",
      ],
      [
        "a transitive dynamic import",
        {
          "pages/Entry.jsx": 'import { load } from "../lib/lazy";',
          "lib/lazy.js": 'export const load = () => import("../api");',
          "api.js": "",
        },
        "pages/Entry.jsx -> lib/lazy.js -> api.js (the API client)",
      ],
      ["axios", { "pages/Entry.jsx": 'import axios from "axios";' }, "pages/Entry.jsx -> axios (forbidden package)"],
      ["a firebase subpath", { "pages/Entry.jsx": 'import { getAuth } from "firebase/auth";' }, "pages/Entry.jsx -> firebase/auth (forbidden package)"],
      ["a Sentry SDK", { "pages/Entry.jsx": 'import * as Sentry from "@sentry/react";' }, "pages/Entry.jsx -> @sentry/react (forbidden package)"],
      [
        "an unfollowable alias",
        { "pages/Entry.jsx": 'import manifest from "@edition-manifest";' },
        'pages/Entry.jsx: "@edition-manifest" is not an installed package (alias or root-relative path?) and cannot be followed',
      ],
      ["a computed dynamic import", { "pages/Entry.jsx": "const load = (name) => import(name);" }, "pages/Entry.jsx: dynamic import with a computed specifier"],
      ["an unresolvable relative import", { "pages/Entry.jsx": 'import x from "./missing";' }, 'pages/Entry.jsx: cannot resolve "./missing"'],
      [
        "code in a translation dictionary",
        {
          "pages/Entry.jsx": 'const load = () => import("../i18n/messages/cs.js");',
          "i18n/messages/cs.js": 'import "../../analytics/track";\nexport default { "Save": "Uložit" };',
        },
        "pages/Entry.jsx -> i18n/messages/cs.js: a translation dictionary must be a plain object of strings",
      ],
    ])("catches %s", (_name, files, violation) => {
      expect(scan(files)).toContain(violation);
    });
  });
});

// ---------------------------------------------------------------------------
// Behaviour
// ---------------------------------------------------------------------------

function SettingsProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output aria-label="location">{location.pathname}{location.search}</output>
      <button type="button" onClick={() => navigate(-1)}>Back</button>
    </>
  );
}

// Stands in for AppShell's Settings page: its own <main> with the announcer.
function SettingsWithAnnouncer() {
  const mainRef = useRef(null);
  useRouteFocusAnnouncer(mainRef);
  return (
    <main ref={mainRef} tabIndex={-1}>
      <h1>Settings</h1>
      <Link to={ONBOARDING_PREVIEW_PATH}>Replay onboarding</Link>
    </main>
  );
}

function mount({ initialEntries = [ONBOARDING_PREVIEW_PATH], initialIndex, settings = <SettingsProbe /> } = {}) {
  return render(
    <MemoryRouter initialEntries={initialEntries} initialIndex={initialIndex}>
      <Routes>
        <Route path={ONBOARDING_PREVIEW_PATH} element={<OnboardingPreview />} />
        <Route path="/settings" element={settings} />
      </Routes>
    </MemoryRouter>
  );
}

// The replay starts at the language step, like the real onboarding.
function continuePastLanguage() {
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
}

describe("OnboardingPreview", () => {
  let fetchSpy;
  let xhrOpenSpy;
  let beaconSpy;

  beforeEach(() => {
    resetRouteFocusAnnouncerForTests();
    localStorage.clear();
    fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      throw new Error("preview must not fetch");
    });
    xhrOpenSpy = vi.spyOn(XMLHttpRequest.prototype, "open");
    if (!navigator.sendBeacon) navigator.sendBeacon = () => true;
    beaconSpy = vi.spyOn(navigator, "sendBeacon");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses only token-based colors", async () => {
    expect(await legacyColorClassesIn(new URL("./OnboardingPreview.jsx", import.meta.url))).toEqual([]);
  });

  it("has an outcome for every choice and the blank link", () => {
    expect(new Set(Object.keys(OUTCOMES))).toEqual(new Set([...ONBOARDING_CHOICE_KEYS, "blank"]));
  });

  it("says what the preview does not do, without promising no telemetry", () => {
    mount();

    expect(screen.getByText(/onboarding preview/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing you click here creates a portfolio\. a language you pick does apply/i)).toBeInTheDocument();
    expect(screen.queryByText(/tracked or sent/i)).not.toBeInTheDocument();
  });

  it("walks every step and choice locally without any network request or stored state", () => {
    mount();

    expect(screen.getByRole("heading", { name: "Choose your language" })).toBeInTheDocument();
    continuePastLanguage();
    expect(screen.getByRole("heading", { name: "Which broker do you use?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Trading 212/ }));
    expect(screen.getByRole("heading", { name: /add your first portfolio/i })).toBeInTheDocument();
    // The live region is mounted, and empty, before the first choice so that
    // choice is announced as a content change.
    expect(screen.getByRole("status")).toBeEmptyDOMElement();

    fireEvent.click(screen.getByRole("button", { name: "Import your Trading 212 CSV" }));
    expect(screen.getByRole("status")).toHaveTextContent(/opens the import for your trading 212 csv file/i);

    fireEvent.click(screen.getByRole("button", { name: "Explore sample portfolio" }));
    expect(screen.getByRole("status")).toHaveTextContent(/sample portfolio/i);

    fireEvent.click(screen.getByRole("button", { name: "Connect Trading 212" }));
    expect(screen.getByRole("status")).toHaveTextContent(/“Trading 212” and opens settings → connections/i);

    fireEvent.click(screen.getByRole("button", { name: /start with a blank portfolio/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/empty portfolio/i);
    expect(screen.getByRole("status")).toHaveTextContent(/nothing was created/i);

    fireEvent.click(screen.getByRole("button", { name: "Change broker" }));
    fireEvent.click(screen.getByRole("button", { name: "Robinhood" }));
    expect(screen.getByRole("heading", { name: "Portfyl doesn't support Robinhood yet" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /look around with sample data/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/sample portfolio/i);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(xhrOpenSpy).not.toHaveBeenCalled();
    expect(beaconSpy).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  });

  it("keeps a single live region and swaps only its content", () => {
    mount();
    continuePastLanguage();
    fireEvent.click(screen.getByRole("button", { name: /Interactive Brokers/ }));
    const status = screen.getByRole("status");

    fireEvent.click(screen.getByRole("button", { name: "Import your Interactive Brokers Flex XML" }));
    fireEvent.click(screen.getByRole("button", { name: "Connect Interactive Brokers" }));

    expect(screen.getAllByRole("status")).toEqual([status]);
    expect(status).toHaveTextContent(/settings → connections/i);
  });

  it("marks the chosen card as pressed", () => {
    mount();
    continuePastLanguage();
    fireEvent.click(screen.getByRole("button", { name: /Trading 212/ }));

    const buttons = ["Import your Trading 212 CSV", "Explore sample portfolio", "Connect Trading 212"]
      .map((name) => screen.getByRole("button", { name }));
    for (const button of buttons) expect(button).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(buttons[1]);

    expect(buttons[1]).toHaveAttribute("aria-pressed", "true");
    expect(buttons[1]).toHaveClass("outline-brand");
    expect(buttons[1]).toHaveTextContent("Selected");
    expect(buttons[0]).toHaveAttribute("aria-pressed", "false");
    expect(buttons[2]).toHaveAttribute("aria-pressed", "false");
  });

  it("moves focus to its heading when entered from another page", async () => {
    mount({ initialEntries: [PREVIEW_EXIT_PATH], settings: <SettingsWithAnnouncer /> });

    fireEvent.click(screen.getByRole("link", { name: /replay onboarding/i }));

    const heading = await screen.findByRole("heading", { name: "Choose your language" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("exits to Settings preferences in place of the preview's history entry", () => {
    mount({ initialEntries: [PREVIEW_EXIT_PATH, ONBOARDING_PREVIEW_PATH], initialIndex: 1 });

    fireEvent.click(screen.getByRole("link", { name: /exit preview/i }));
    expect(screen.getByLabelText("location")).toHaveTextContent(PREVIEW_EXIT_PATH);

    // Back skips the replaced preview entry and lands on the page before it.
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.queryByRole("heading", { name: "Which broker do you use?" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("location")).toHaveTextContent(PREVIEW_EXIT_PATH);
  });

  it("styles Exit preview as the shared secondary button", () => {
    mount();

    expect(screen.getByRole("link", { name: /exit preview/i })).toHaveClass("btn-ghost");
  });
});
