import { ANALYTICS_COPY, getAnalyticsLanguage } from "./analyticsCopy";

describe("getAnalyticsLanguage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("follows the browser language like the app does when nothing is saved", () => {
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["cs-CZ", "en"]);
    expect(getAnalyticsLanguage()).toBe("cs");
  });

  it("lets a saved app language win over the browser's", () => {
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["cs-CZ"]);
    localStorage.setItem("portfyl_language", "de");
    expect(getAnalyticsLanguage()).toBe("de");
  });

  it("falls back to English for a browser language it has no copy for", () => {
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["fr-FR"]);
    expect(getAnalyticsLanguage()).toBe("en");
  });
});

describe("analytics consent copy", () => {
  it("uses em dashes, not double hyphens, in every language", () => {
    for (const [lang, copy] of Object.entries(ANALYTICS_COPY)) {
      for (const [key, text] of Object.entries(copy)) {
        if (typeof text !== "string") continue;
        expect(`${lang}.${key}: ${text}`).not.toMatch(/ -- /);
      }
    }
    expect(ANALYTICS_COPY.en.essential).toContain("working — sign-in");
  });
});
