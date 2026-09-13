import { api } from "../api";

export const fetchLocalTaxReport = (year) =>
  api.get("/analytics/tax-report", { params: year ? { year } : {} }).then((r) => r.data);

// Backwards-compatible alias: existing local consumers/tests use fetchTaxReport.
export const fetchTaxReport = fetchLocalTaxReport;

export const fetchScreener = (params = {}) =>
  api.get("/market/screener", { params }).then((r) => r.data);

export const createScreenerJob = (body = {}) =>
  api.post("/market/screener/jobs", body).then((r) => r.data);

export const fetchScreenerJob = (jobId, { offset = 0, limit = 50 } = {}) =>
  api.get(`/market/screener/jobs/${jobId}`, { params: { offset, limit } }).then((r) => r.data);

export const cancelScreenerJob = (jobId) =>
  api.delete(`/market/screener/jobs/${jobId}`).then((r) => r.data);
