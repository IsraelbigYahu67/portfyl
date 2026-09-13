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
