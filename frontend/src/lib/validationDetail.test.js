import { formatValidationDetail } from "./validationDetail";
import { translate } from "../i18n/I18nProvider";
import cs from "../i18n/messages/cs.js";

const czech = (text, vars) => translate(cs, text, vars);

const gt = (field, n = 0) => ({
  type: "greater_than",
  loc: ["body", field],
  msg: `Input should be greater than ${n}`,
  ctx: { gt: n },
});

describe("formatValidationDetail", () => {
  it("passes a plain string through", () => {
    expect(formatValidationDetail("Portfolio not found")).toBe("Portfolio not found");
  });

  it("describes 422 entries in English with field names", () => {
    expect(formatValidationDetail([gt("shares"), gt("price")])).toBe(
      "Shares must be greater than 0; Price per share must be greater than 0",
    );
    expect(
      formatValidationDetail(
        [{ type: "string_pattern_mismatch", loc: ["body", "currency"], msg: "String should match pattern" }],
        { lang: "en" },
      ),
    ).toBe("Currency has an invalid format (currency must be 3 letters, e.g. USD)");
    expect(
      formatValidationDetail([{ type: "literal_error", loc: ["body", "type"], msg: "Input should be 'buy'" }]),
    ).toBe("Type has an unsupported value");
  });

  it("describes 422 entries in Czech", () => {
    expect(formatValidationDetail([gt("shares")], { t: czech })).toBe("Kusy musí být větší než 0");
  });

  it("falls back to the server msg for unknown error types", () => {
    expect(
      formatValidationDetail([{ type: "value_error", loc: ["body", "notes"], msg: "Value error, Too long" }]),
    ).toBe("Notes: Too long");
    expect(formatValidationDetail([{ msg: "Something odd" }])).toBe("Something odd");
  });

  it("de-duplicates and never returns an object", () => {
    expect(formatValidationDetail([gt("shares"), gt("shares")])).toBe("Shares must be greater than 0");
    expect(formatValidationDetail({ secret: "x" })).toBe("The server rejected the request.");
    expect(formatValidationDetail([{}, null, 5], { t: czech })).toBe("Server požadavek odmítl.");
    expect(formatValidationDetail(undefined, { fallback: "Custom" })).toBe("Custom");
  });

  it("words a sentence without a field from the verb", () => {
    expect(formatValidationDetail([{ type: "missing", loc: ["body"] }])).toBe("is required");
  });
});
