import { BROKER_LABELS, describeSplit, needsOwnPortfolio, splitNote, uniquePortfolioName } from "./brokerPortfolio";

test("an empty portfolio or one from the same broker is reused", () => {
  expect(needsOwnPortfolio({ brokers: [] }, "xtb")).toBe(false);
  expect(needsOwnPortfolio({}, "xtb")).toBe(false);
  expect(needsOwnPortfolio({ brokers: ["xtb"] }, "xtb")).toBe(false);
});

test("data from another broker, own entries or samples need a new portfolio", () => {
  expect(needsOwnPortfolio({ brokers: ["trading212"] }, "xtb")).toBe(true);
  expect(needsOwnPortfolio({ brokers: ["own"] }, "ibkr")).toBe(true);
  expect(needsOwnPortfolio({ brokers: ["demo"] }, "etoro")).toBe(true);
  expect(needsOwnPortfolio({ brokers: ["xtb", "own"] }, "xtb")).toBe(true);
});

test("native CSV (no broker) never splits", () => {
  expect(needsOwnPortfolio({ brokers: ["trading212"] }, null)).toBe(false);
  expect(needsOwnPortfolio(null, "xtb")).toBe(false);
});

test("new portfolio names follow the broker and stay unique", () => {
  expect(uniquePortfolioName([], "xtb")).toBe("XTB");
  expect(uniquePortfolioName([{ name: "XTB" }], "xtb")).toBe("XTB 2");
  expect(uniquePortfolioName([{ name: "xtb" }, { name: "XTB 2" }], "xtb")).toBe("XTB 3");
  expect(BROKER_LABELS.ibkr).toBe("Interactive Brokers");
});

test("describes why a new portfolio was opened", () => {
  expect(describeSplit({ name: "Main", brokers: ["trading212", "own"] }, { name: "XTB" }, "xtb")).toBe(
    "“Main” already holds Trading 212 data and your own transactions, so XTB goes into its own portfolio “XTB”.",
  );
});

test("splitNote explains a new or a blocked portfolio and is empty otherwise", () => {
  const previous = { name: "Main", brokers: ["trading212"] };
  expect(splitNote({ created: { name: "eToro" }, previous }, "etoro")).toContain("own portfolio “eToro”");
  expect(splitNote({ blocked: "Portfolio limit reached", previous }, "etoro")).toContain("could not be created (Portfolio limit reached)");
  expect(splitNote(null, "etoro")).toBe("");
});
