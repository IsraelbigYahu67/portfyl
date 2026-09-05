import { describe, expect, it } from "vitest";

import { editionManifestPath, resolveFrontendEdition } from "../edition.config.js";
import {
  EDITION_NAVIGATION as CLOUD_NAVIGATION,
  EDITION_ROUTES as CLOUD_ROUTES,
} from "./editions/cloud";
import {
  EDITION_NAVIGATION as LOCAL_NAVIGATION,
  EDITION_ROUTES as LOCAL_ROUTES,
} from "./editions/local";
import { enabledEditionEntries } from "./editions/filter";


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
});
