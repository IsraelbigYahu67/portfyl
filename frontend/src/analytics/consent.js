export const CONSENT_STATES = Object.freeze({
  PENDING: "pending",
  ACCEPTED: "accepted",
  REJECTED: "rejected",
});

export const ANALYTICS_CONSENT_COOKIE = "portfyl_analytics_consent";

function isProductionHost(hostname) {
  return hostname === "portfyl.com" || hostname.endsWith(".portfyl.com");
}

function cookieAttributes(hostname, maxAge) {
  const attributes = [];
  if (isProductionHost(hostname)) attributes.push("Domain=.portfyl.com");
  attributes.push("Path=/", `Max-Age=${maxAge}`, "SameSite=Lax");
  if (isProductionHost(hostname)) attributes.push("Secure");
  return attributes.join("; ");
}

export function getAnalyticsConsent(documentRef = document) {
  const value = documentRef.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${ANALYTICS_CONSENT_COOKIE}=`))
    ?.split("=")[1];
  return value === CONSENT_STATES.ACCEPTED || value === CONSENT_STATES.REJECTED
    ? value
    : CONSENT_STATES.PENDING;
}

export function setAnalyticsConsent(consent, { documentRef = document, hostname = window.location.hostname } = {}) {
  if (consent !== CONSENT_STATES.ACCEPTED && consent !== CONSENT_STATES.REJECTED) {
    throw new TypeError("Analytics consent must be accepted or rejected");
  }
  documentRef.cookie = `${ANALYTICS_CONSENT_COOKIE}=${consent}; ${cookieAttributes(hostname, 15_552_000)}`;
  return consent;
}

export function clearAnalyticsConsent({ documentRef = document, hostname = window.location.hostname } = {}) {
  documentRef.cookie = `${ANALYTICS_CONSENT_COOKIE}=; ${cookieAttributes(hostname, 0)}`;
}
