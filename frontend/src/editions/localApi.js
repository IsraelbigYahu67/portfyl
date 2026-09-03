import { api } from "../api";

export const fetchTaxReport = (year) =>
  api.get("/analytics/tax-report", { params: year ? { year } : {} }).then((r) => r.data);

export const fetchScreener = (params = {}) =>
  api.get("/market/screener", { params }).then((r) => r.data);
