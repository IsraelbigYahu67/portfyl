import { fetchBillingStatus } from "../api";

// One shared query for /api/billing/status: the trial banner reads it, and
// anything that changes the plan invalidates it.
export const BILLING_STATUS_KEY = ["billing-status"];

export const billingStatusQuery = {
  queryKey: BILLING_STATUS_KEY,
  // Read the export when the query runs, not when this module loads.
  queryFn: () => fetchBillingStatus(),
  staleTime: 60_000,
  retry: false,
};
