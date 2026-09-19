export const ANALYTICS_EVENTS = Object.freeze({
  LANDING_VIEWED: "landing_viewed",
  DEMO_STARTED: "demo_started",
  DEMO_PAGE_VIEWED: "demo_page_viewed",
  DEMO_STOCK_VIEWED: "demo_stock_viewed",
  DEMO_ACTIVATION_REACHED: "demo_activation_reached",
  SIGNUP_CTA_CLICKED: "signup_cta_clicked",
  SIGNUP_STARTED: "signup_started",
  SIGNUP_COMPLETED: "signup_completed",
  PORTFOLIO_CREATED: "portfolio_created",
  PORTFOLIO_DATA_IMPORTED: "portfolio_data_imported",
  DASHBOARD_FIRST_VALUE_RENDERED: "dashboard_first_value_rendered",
  USER_ACTIVATION_REACHED: "user_activation_reached",
});

const languages = new Set(["cs", "en", "de"]);
const referrerClasses = new Set(["direct", "search", "social", "referral", "internal", "unknown"]);
const sourceTypes = new Set(["demo", "csv", "broker"]);
const creationPaths = new Set(["blank", "demo", "csv", "broker"]);
const sourceSurfaces = new Set(["landing_hero", "landing_closing", "demo", "direct"]);
const entryPoints = new Set(["landing_hero", "landing_closing", "direct"]);
const demoPages = new Set(["overview", "allocation", "analytics", "dividends", "stock"]);
const demoSymbols = new Set(["VUAA", "MSFT", "JPM", "JNJ", "XOM", "PG", "AMZN", "CAT", "NEE", "PLD"]);
const activationPaths = new Set(["three_pages", "stock_after_page"]);

function stringField(value, { max = 80, values } = {}) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  if (!normalized || normalized.length > max) return null;
  return values && !values.has(normalized) ? null : normalized;
}

function integerField(value, { min, max }) {
  return Number.isFinite(value) && Number.isInteger(value) && value >= min && value <= max ? value : null;
}

const fields = Object.freeze({
  language: (value) => stringField(value, { values: languages }),
  referrer_class: (value) => stringField(value, { values: referrerClasses }),
  utm_source: (value) => stringField(value, { max: 120 }),
  utm_medium: (value) => stringField(value, { max: 120 }),
  utm_campaign: (value) => stringField(value, { max: 120 }),
  entry_point: (value) => stringField(value, { values: entryPoints }),
  demo_page: (value) => stringField(value, { values: demoPages }),
  demo_symbol: (value) => stringField(value, { values: demoSymbols }),
  activation_path: (value) => stringField(value, { values: activationPaths }),
  distinct_demo_pages: (value) => integerField(value, { min: 2, max: 5 }),
  source_surface: (value) => stringField(value, { values: sourceSurfaces }),
  creation_path: (value) => stringField(value, { values: creationPaths }),
  source_type: (value) => stringField(value, { values: sourceTypes }),
});

const schemas = Object.freeze({
  [ANALYTICS_EVENTS.LANDING_VIEWED]: ["language", "referrer_class", "utm_source", "utm_medium", "utm_campaign"],
  [ANALYTICS_EVENTS.DEMO_STARTED]: ["language", "entry_point"],
  [ANALYTICS_EVENTS.DEMO_PAGE_VIEWED]: ["demo_page", "language"],
  [ANALYTICS_EVENTS.DEMO_STOCK_VIEWED]: ["demo_symbol"],
  [ANALYTICS_EVENTS.DEMO_ACTIVATION_REACHED]: ["activation_path", "distinct_demo_pages"],
  [ANALYTICS_EVENTS.SIGNUP_CTA_CLICKED]: ["source_surface", "language"],
  [ANALYTICS_EVENTS.SIGNUP_STARTED]: ["source_surface", "language"],
  [ANALYTICS_EVENTS.SIGNUP_COMPLETED]: ["source_surface"],
  [ANALYTICS_EVENTS.PORTFOLIO_CREATED]: ["creation_path"],
  [ANALYTICS_EVENTS.PORTFOLIO_DATA_IMPORTED]: ["source_type"],
  [ANALYTICS_EVENTS.DASHBOARD_FIRST_VALUE_RENDERED]: ["source_type"],
  [ANALYTICS_EVENTS.USER_ACTIVATION_REACHED]: ["source_type"],
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
