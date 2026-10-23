import { ANALYTICS_COPY } from "./analyticsCopy";

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
