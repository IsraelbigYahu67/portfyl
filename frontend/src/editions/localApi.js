import { api } from "../api";

export const fetchLocalTaxReport = (year) =>
  api.get("/analytics/tax-report", { params: year ? { year } : {} }).then((r) => r.data);

// Backwards-compatible alias: existing local consumers/tests use fetchTaxReport.
export const fetchTaxReport = fetchLocalTaxReport;
