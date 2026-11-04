import { ONBOARDING_PREVIEW_PATH, isOnboardingPreviewPath } from "./routes";

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
