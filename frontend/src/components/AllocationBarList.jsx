import { allocationRows } from "../lib/allocationBreakdown";
import AllocationBreakdownList from "./AllocationBreakdownList";

// Backwards-compatible Position composition wrapper. Sorting/bounding lives in
// allocationBreakdown.js and rendering in AllocationBreakdownList, so there is
// exactly one implementation of each.
export default function AllocationBarList({ holdings, currency }) {
  const rows = allocationRows({ category: "position", holdings });
  return <AllocationBreakdownList rows={rows} currency={currency} />;
}
