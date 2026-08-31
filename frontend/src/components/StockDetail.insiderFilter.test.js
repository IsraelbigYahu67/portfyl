import { toggleSetValue } from "./StockDetail";

describe("toggleSetValue", () => {
  it("isolates to just the clicked value when starting from All (empty set)", () => {
    const result = toggleSetValue(new Set(), "buy", 3);
    expect(result).toEqual(new Set(["buy"]));
  });

  it("adds a second value to an existing isolated selection", () => {
    const result = toggleSetValue(new Set(["buy"]), "sell", 3);
    expect(result).toEqual(new Set(["buy", "sell"]));
  });

  it("removes a value from the selection when clicked again", () => {
    const result = toggleSetValue(new Set(["buy", "sell"]), "sell", 3);
    expect(result).toEqual(new Set(["buy"]));
  });

  it("resets to All (empty set) when the last active value is deselected", () => {
    const result = toggleSetValue(new Set(["buy"]), "buy", 3);
    expect(result).toEqual(new Set());
  });

  it("resets to All (empty set) when every option ends up selected", () => {
    const result = toggleSetValue(new Set(["buy", "sell"]), "other", 3);
    expect(result).toEqual(new Set());
  });
});
