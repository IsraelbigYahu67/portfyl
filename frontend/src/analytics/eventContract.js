import { SUPPORTED_BROKERS } from "../lib/onboardingBrokers";

export const ANALYTICS_EVENTS = Object.freeze({
  LANDING_VIEWED: "landing_viewed",
  LANDING_MINIDEMO_USED: "landing_minidemo_used",
  SIGNUP_CTA_CLICKED: "signup_cta_clicked",
  SIGNUP_STARTED: "signup_started",
  SIGNUP_COMPLETED: "signup_completed",
  PORTFOLIO_CREATED: "portfolio_created",
  PORTFOLIO_DATA_IMPORTED: "portfolio_data_imported",
  DASHBOARD_FIRST_VALUE_RENDERED: "dashboard_first_value_rendered",
  USER_ACTIVATION_REACHED: "user_activation_reached",
  ONBOARDING_STEP_VIEWED: "onboarding_step_viewed",
  ONBOARDING_BROKER_PICKED: "onboarding_broker_picked",
  BROKER_CHECK_USED: "broker_check_used",
  BROKER_REQUEST_SENT: "broker_request_sent",
});

const languages = new Set(["cs", "en", "de"]);
const miniDemoKinds = new Set(["allocation", "stock", "performance", "dividends", "portfolios"]);
const referrerClasses = new Set(["direct", "search", "social", "referral", "internal", "unknown"]);
const sourceTypes = new Set(["demo", "csv", "broker"]);
const creationPaths = new Set(["blank", "demo", "csv", "broker"]);
const sourceSurfaces = new Set(["landing_hero", "landing_closing", "landing_broker_check", "direct"]);
const authMethods = new Set(["password", "google"]);
const onboardingSteps = new Set(["broker", "choices", "connect", "unsupported"]);
// Supported broker keys come from the registry, never a typed name; an
// unsupported pick is reported as the fixed marker only.
const brokerKeys = new Set([...SUPPORTED_BROKERS.map((broker) => broker.key), "unsupported"]);
const brokerCheckResults = new Set(["supported", "unsupported"]);

function stringField(value, { max = 80, values } = {}) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  if (!normalized || normalized.length > max) return null;
  return values && !values.has(normalized) ? null : normalized;
}

const fields = Object.freeze({
  language: (value) => stringField(value, { values: languages }),
  minidemo: (value) => stringField(value, { values: miniDemoKinds }),
  referrer_class: (value) => stringField(value, { values: referrerClasses }),
  utm_source: (value) => stringField(value, { max: 120 }),
  utm_medium: (value) => stringField(value, { max: 120 }),
  utm_campaign: (value) => stringField(value, { max: 120 }),
  source_surface: (value) => stringField(value, { values: sourceSurfaces }),
  creation_path: (value) => stringField(value, { values: creationPaths }),
  source_type: (value) => stringField(value, { values: sourceTypes }),
  auth_method: (value) => stringField(value, { values: authMethods }),
  step: (value) => stringField(value, { values: onboardingSteps }),
  broker_key: (value) => stringField(value, { values: brokerKeys }),
  result: (value) => stringField(value, { values: brokerCheckResults }),
});

const schemas = Object.freeze({
  [ANALYTICS_EVENTS.LANDING_VIEWED]: ["language", "referrer_class", "utm_source", "utm_medium", "utm_campaign"],
  [ANALYTICS_EVENTS.LANDING_MINIDEMO_USED]: ["minidemo", "language"],
  [ANALYTICS_EVENTS.SIGNUP_CTA_CLICKED]: ["source_surface", "language"],
  [ANALYTICS_EVENTS.SIGNUP_STARTED]: ["source_surface", "language"],
  [ANALYTICS_EVENTS.SIGNUP_COMPLETED]: ["source_surface", "auth_method"],
  [ANALYTICS_EVENTS.PORTFOLIO_CREATED]: ["creation_path"],
  [ANALYTICS_EVENTS.PORTFOLIO_DATA_IMPORTED]: ["source_type"],
  [ANALYTICS_EVENTS.DASHBOARD_FIRST_VALUE_RENDERED]: ["source_type"],
  [ANALYTICS_EVENTS.USER_ACTIVATION_REACHED]: ["source_type"],
  [ANALYTICS_EVENTS.ONBOARDING_STEP_VIEWED]: ["step"],
  [ANALYTICS_EVENTS.ONBOARDING_BROKER_PICKED]: ["broker_key"],
  [ANALYTICS_EVENTS.BROKER_CHECK_USED]: ["result", "language"],
  [ANALYTICS_EVENTS.BROKER_REQUEST_SENT]: [],
});

function fail(strict, message) {
  if (strict) throw new TypeError(message);
  return null;
}

export function sanitizeEvent(
  name,
  properties,
  { strict = import.meta.env.DEV || import.meta.env.MODE === "test" } = {},
) {
  const schema = schemas[name];
  if (!schema) return fail(strict, `Unknown analytics event: ${String(name)}`);
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) {
    return fail(strict, `Invalid properties for ${name}`);
  }

  const propertyNames = Object.keys(properties);
  const unknown = propertyNames.find((property) => !schema.includes(property));
  if (unknown && strict) return fail(true, `Unknown analytics property: ${unknown}`);

  const sanitized = {};
  for (const property of schema) {
    if (!(property in properties)) return fail(strict, `Missing analytics property: ${property}`);
    const value = fields[property](properties[property]);
    if (value === null) return fail(strict, `Invalid analytics property: ${property}`);
    sanitized[property] = value;
  }

  return { name, properties: sanitized };
}
