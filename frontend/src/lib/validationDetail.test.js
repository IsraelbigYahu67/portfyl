import { formatValidationDetail } from "./validationDetail";

const gt = (field, n = 0) => ({
  type: "greater_than",
  loc: ["body", field],
  msg: `Input should be greater than ${n}`,
  ctx: { gt: n },
});

describe("formatValidationDetail", () => {
  it("passes a plain string through", () => {
    expect(formatValidationDetail("Portfolio not found", { lang: "en" })).toBe("Portfolio not found");
  });

  it("describes 422 entries in English with field names", () => {
    expect(formatValidationDetail([gt("shares"), gt("price")], { lang: "en" })).toBe(
      "Shares must be greater than 0; Price per share must be greater than 0",
    );
    expect(
      formatValidationDetail(
        [{ type: "string_pattern_mismatch", loc: ["body", "currency"], msg: "String should match pattern" }],
        { lang: "en" },
      ),
    ).toBe("Currency has an invalid format (currency must be 3 letters, e.g. USD)");
    expect(
      formatValidationDetail([{ type: "literal_error", loc: ["body", "type"], msg: "Input should be 'buy'" }], { lang: "en" }),
    ).toBe("Type has an unsupported value");
  });

  it("describes 422 entries in Czech", () => {
    expect(formatValidationDetail([gt("shares")], { lang: "cs" })).toBe("Počet kusů musí být větší než 0");
  });

  it("falls back to the server msg for unknown error types", () => {
    expect(
      formatValidationDetail([{ type: "value_error", loc: ["body", "notes"], msg: "Value error, Too long" }], { lang: "en" }),
    ).toBe("Notes: Too long");
    expect(formatValidationDetail([{ msg: "Something odd" }], { lang: "en" })).toBe("Something odd");
  });

  it("de-duplicates and never returns an object", () => {
    expect(formatValidationDetail([gt("shares"), gt("shares")], { lang: "en" })).toBe("Shares must be greater than 0");
    expect(formatValidationDetail({ secret: "x" }, { lang: "en" })).toBe("The server rejected the request.");
    expect(formatValidationDetail([{}, null, 5], { lang: "cs" })).toBe("Server požadavek odmítl.");
    expect(formatValidationDetail(undefined, { lang: "en", fallback: "Custom" })).toBe("Custom");
  });

  it("picks the language from the document when not given", () => {
    document.documentElement.lang = "cs";
    try {
      expect(formatValidationDetail([gt("price")])).toBe("Cena za kus musí být větší než 0");
    } finally {
      document.documentElement.lang = "";
    }
  });
});
