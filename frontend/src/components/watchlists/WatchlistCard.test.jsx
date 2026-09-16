import { sortWatchlistItems } from "./WatchlistCard";

const items = [
  { id: "z", ticker: "ZZZ", quote: { name: "Zulu", change_percent: null, market_cap: null } },
  { id: "b", ticker: "BBB", quote: { name: "Beta", change_percent: -2, market_cap: 20 } },
  { id: "a", ticker: "AAA", quote: { name: "Alpha", change_percent: 5, market_cap: 10 } },
  { id: "c", ticker: "CCC", quote: { name: "Charlie", change_percent: 5, market_cap: 30 } },
];

it("sorts deterministically with null quote values last", () => {
  expect(sortWatchlistItems(items, "ticker").map((item) => item.ticker)).toEqual(["AAA", "BBB", "CCC", "ZZZ"]);
  expect(sortWatchlistItems(items, "change_desc").map((item) => item.ticker)).toEqual(["AAA", "CCC", "BBB", "ZZZ"]);
  expect(sortWatchlistItems(items, "change_asc").map((item) => item.ticker)).toEqual(["BBB", "AAA", "CCC", "ZZZ"]);
  expect(sortWatchlistItems(items, "market_cap_desc").map((item) => item.ticker)).toEqual(["CCC", "BBB", "AAA", "ZZZ"]);
});
