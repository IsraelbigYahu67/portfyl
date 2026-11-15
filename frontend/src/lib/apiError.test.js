import { getApiErrorMessage } from "./apiError";

it.each([
  [{ response: { data: { detail: "Portfolio unavailable" } } }, "Portfolio unavailable"],
  [{ response: { data: { detail: [{ loc: ["query", "limit"], msg: "Invalid value" }] } } }, "Invalid value"],
  [{ code: "ECONNABORTED" }, "The request timed out. Please try again."],
  [{ request: {} }, "We couldn't reach Portfyl. Check your connection and try again."],
  [new Error("Readable failure"), "Readable failure"],
])("normalizes %o", (error, expected) => {
  expect(getApiErrorMessage(error)).toBe(expected);
});

it("never exposes stack text or object coercion", () => {
  expect(
    getApiErrorMessage(
      { response: { data: { detail: { secret: "x" } } } },
      "Safe fallback",
    ),
  ).toBe("Safe fallback");
});

it("trims useful messages and drops empty validation entries", () => {
  expect(getApiErrorMessage({
    response: { data: { detail: [{ msg: " First " }, {}, { msg: "Second" }] } },
  })).toBe("First; Second");
  expect(getApiErrorMessage({ message: "   " }, "Safe fallback")).toBe("Safe fallback");
});

describe("known broker connection errors", () => {
  const fakeT = (text) => `CS:${text}`;
  const withDetail = (detail) => ({ response: { data: { detail } } });

  it("translates a known broker detail through t", () => {
    expect(getApiErrorMessage(withDetail("Invalid API key"), "Fallback", fakeT)).toBe("CS:Invalid API key");
  });

  it("still matches a known detail with whitespace around it", () => {
    expect(getApiErrorMessage(withDetail("  Invalid API key \n"), "Fallback", fakeT)).toBe("CS:Invalid API key");
  });

  it("leaves an unknown detail untouched and untranslated", () => {
    expect(getApiErrorMessage(withDetail("Could not reach Trading 212: boom"), "Fallback", fakeT))
      .toBe("Could not reach Trading 212: boom");
  });
});
