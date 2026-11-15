import { PLAN_PRICES_CENTS, formatPlanPrice } from "./planPrices";

const plain = (text) => text.replace(/ /g, " ");

it("holds the monthly prices in euro cents, VAT included", () => {
  expect(PLAN_PRICES_CENTS).toEqual({ investor: 599, pro: 999 });
});

it("writes the euro after the number for Czech and German, before it for English", () => {
  expect(plain(formatPlanPrice(599, "cs"))).toBe("5,99 €");
  expect(plain(formatPlanPrice(999, "de"))).toBe("9,99 €");
  expect(formatPlanPrice(599, "en")).toBe("€5.99");
});

it("shows a free plan as a plain zero", () => {
  expect(plain(formatPlanPrice(0, "cs"))).toBe("0 €");
  expect(formatPlanPrice(0, "en")).toBe("€0");
});

it("never breaks a price across lines", () => {
  expect(formatPlanPrice(599, "cs")).toContain(" ");
});
