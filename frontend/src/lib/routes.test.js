import * as routes from "./routes";
import { HAS_PUBLIC_HOME, ONBOARDING_PREVIEW_PATH, isOnboardingPreviewPath, isRetiredDemoPath, legalPage } from "./routes";

describe("legalPage", () => {
  it("matches the terms, privacy and security pages with an optional trailing slash", () => {
    expect(legalPage("/terms")).toBe("terms");
    expect(legalPage("/privacy/")).toBe("privacy");
    expect(legalPage("/security")).toBe("security");
    expect(legalPage("/security/")).toBe("security");
  });

  it("does not match similar paths", () => {
    for (const pathname of ["/", "/securityx", "/security/x", "/en/security", "/.well-known/security.txt", "/Security"]) {
      expect(legalPage(pathname), pathname).toBeNull();
    }
  });
});

describe("isRetiredDemoPath", () => {
  it("no longer exports the old isDemoPath", () => {
    expect(routes.isDemoPath).toBeUndefined();
  });

  it("matches /demo and everything below it, but only in the cloud edition", () => {
    for (const pathname of ["/demo", "/demo/", "/demo/x", "/demo/allocation", "/demo/stock/MSFT"]) {
      expect(isRetiredDemoPath(pathname), pathname).toBe(HAS_PUBLIC_HOME);
    }
  });

  it("does not match similar paths", () => {
    for (const pathname of ["/demolition", "/demos", "/en/demo", "/", "/en/", "/xdemo", "/demo.png"]) {
      expect(isRetiredDemoPath(pathname), pathname).toBe(false);
    }
  });
});

describe("isOnboardingPreviewPath", () => {
  it("matches the preview path with or without one trailing slash", () => {
    expect(isOnboardingPreviewPath(ONBOARDING_PREVIEW_PATH)).toBe(true);
    expect(isOnboardingPreviewPath(`${ONBOARDING_PREVIEW_PATH}/`)).toBe(true);
  });

  it("rejects other paths", () => {
    for (const pathname of ["/onboarding", "/onboarding/preview//", "/onboarding/preview/x", "/xonboarding/preview"]) {
      expect(isOnboardingPreviewPath(pathname)).toBe(false);
    }
  });
});
