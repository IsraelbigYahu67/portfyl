import { describe, expect, it } from "vitest";
import {
  ANALYTICS_CONSENT_COOKIE,
  CONSENT_STATES,
  clearAnalyticsConsent,
  getAnalyticsConsent,
  setAnalyticsConsent,
} from "./consent";

function cookieDocument(initial = "") {
  return { cookie: initial };
}

describe("analytics consent cookie", () => {
  it("defaults missing and invalid cookies to pending", () => {
    expect(getAnalyticsConsent(cookieDocument())).toBe(CONSENT_STATES.PENDING);
    expect(getAnalyticsConsent(cookieDocument(`${ANALYTICS_CONSENT_COOKIE}=unexpected`))).toBe(CONSENT_STATES.PENDING);
    expect(getAnalyticsConsent(cookieDocument(`other=value; ${ANALYTICS_CONSENT_COOKIE}=accepted`))).toBe(CONSENT_STATES.ACCEPTED);
  });

  it.each([CONSENT_STATES.ACCEPTED, CONSENT_STATES.REJECTED])("round-trips %s", (consent) => {
    const documentRef = cookieDocument();
    setAnalyticsConsent(consent, { documentRef, hostname: "localhost" });
    expect(getAnalyticsConsent(documentRef)).toBe(consent);
  });

  it("writes the production cross-subdomain cookie attributes", () => {
    const documentRef = cookieDocument();
    setAnalyticsConsent(CONSENT_STATES.ACCEPTED, { documentRef, hostname: "app.portfyl.com" });
    expect(documentRef.cookie).toBe(`${ANALYTICS_CONSENT_COOKIE}=accepted; Domain=.portfyl.com; Path=/; Max-Age=15552000; SameSite=Lax; Secure`);
  });

  it("omits Domain and Secure on localhost", () => {
    const documentRef = cookieDocument();
    setAnalyticsConsent(CONSENT_STATES.REJECTED, { documentRef, hostname: "localhost" });
    expect(documentRef.cookie).toBe(`${ANALYTICS_CONSENT_COOKIE}=rejected; Path=/; Max-Age=15552000; SameSite=Lax`);
  });

  it("clears the choice with matching scope attributes", () => {
    const documentRef = cookieDocument();
    clearAnalyticsConsent({ documentRef, hostname: "portfyl.com" });
    expect(documentRef.cookie).toBe(`${ANALYTICS_CONSENT_COOKIE}=; Domain=.portfyl.com; Path=/; Max-Age=0; SameSite=Lax; Secure`);
  });

  it("rejects attempts to write a non-decision state", () => {
    expect(() => setAnalyticsConsent(CONSENT_STATES.PENDING, { documentRef: cookieDocument(), hostname: "localhost" })).toThrow(/consent/i);
  });
});
