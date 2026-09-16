import { describe, expect, it, vi } from "vitest";

import { editionManifestPath, resolveFrontendEdition } from "../edition.config.js";
import {
  EDITION_NAVIGATION as CLOUD_NAVIGATION,
  EDITION_ROUTES as CLOUD_ROUTES,
  fetchEditionDashboardSignals as cloudDashboardSignals,
} from "./editions/cloud";
import cloudManifestSource from "./editions/cloud.jsx?raw";
import {
  EDITION_NAVIGATION as LOCAL_NAVIGATION,
  EDITION_ROUTES as LOCAL_ROUTES,
  fetchEditionDashboardSignals as localDashboardSignals,
} from "./editions/local";
import { enabledEditionEntries } from "./editions/filter";

vi.mock("./editions/localApi", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    fetchLocalTaxReport: vi.fn(async () => ({ summary: { fx_complete: false } })),
  };
});


describe("edition build configuration", () => {
  it("requires an explicit supported edition", () => {
    expect(() => resolveFrontendEdition({}, "production")).toThrow(
      "VITE_PORTFYL_EDITION is required"
    );
    expect(() => resolveFrontendEdition({ VITE_PORTFYL_EDITION: "preview" })).toThrow(
      "Unsupported VITE_PORTFYL_EDITION"
    );
  });

  it("maps explicit local and cloud modes to different manifests", () => {
    expect(resolveFrontendEdition({}, "edition-local")).toBe("local");
    expect(resolveFrontendEdition({}, "edition-cloud")).toBe("cloud");
    expect(editionManifestPath("local")).toMatch(/editions[\\/]local\.jsx$/);
    expect(editionManifestPath("cloud")).toMatch(/editions[\\/]cloud\.jsx$/);
  });
});

describe("edition manifests", () => {
  it('keeps every edition page lazy with a shared route/navigation loader', () => {
    for (const [routes, navigation] of [[LOCAL_ROUTES, LOCAL_NAVIGATION], [CLOUD_ROUTES, CLOUD_NAVIGATION]]) {
      for (const route of routes) {
        expect(route.Component.$$typeof).toBe(Symbol.for('react.lazy'));
        expect(navigation.find(item => item.to === route.path).preload).toBe(route.preload);
      }
    }
    expect(cloudManifestSource).not.toMatch(/TaxReport|Screener/);
  });
  it("keeps owner-only tools local and plan comparison cloud-only", () => {
    expect(LOCAL_ROUTES.map((entry) => entry.path)).toEqual(["/tax-report", "/screener"]);
    expect(LOCAL_NAVIGATION.map((entry) => entry.to)).toEqual(["/tax-report", "/screener"]);
    expect(CLOUD_ROUTES.map((entry) => entry.path)).toEqual(["/pricing"]);
    expect(CLOUD_NAVIGATION.map((entry) => entry.to)).toEqual(["/pricing"]);
    expect(CLOUD_NAVIGATION.map((entry) => entry.label)).toEqual(["Plans"]);
    expect(CLOUD_ROUTES.some((entry) => ["/tax-report", "/screener"].includes(entry.path))).toBe(false);
  });

  it("fails closed until the backend explicitly returns a capability", () => {
    expect(enabledEditionEntries(LOCAL_ROUTES, [])).toEqual([]);
    expect(enabledEditionEntries(LOCAL_ROUTES, ["tax_report"]).map((entry) => entry.path))
      .toEqual(["/tax-report"]);
  });

  it("exposes edition-safe dashboard signals without importing local API into cloud", async () => {
    await expect(localDashboardSignals()).resolves.toEqual({ taxReport: { summary: { fx_complete: false } } });
    await expect(cloudDashboardSignals()).resolves.toEqual({ taxReport: null });
    expect(cloudManifestSource).not.toContain("localApi");
  });
});
