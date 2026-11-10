// Turns the `detail` of a FastAPI error response into one readable sentence.
// `detail` is a string for HTTPException, but a list of
// {loc, msg, type, ctx} objects for a 422 request-validation error.
// Rendering that list straight into JSX crashes React ("Objects are not valid
// as a React child"), so every form that shows a server error goes through here.
//
// The text is English source text marked with msg()/t() and translated through
// `t` (the i18n translate function, see i18n/I18nProvider); without `t` it
// reads in English.

const msg = (text) => text;
const english = (text, vars) => text.replace(/\{(\w+)\}/g, (m, key) => (vars && key in vars ? String(vars[key]) : m));

const FIELD_LABELS = {
  ticker: msg("Ticker"),
  type: msg("Type"),
  shares: msg("Shares"),
  price: msg("Price per share"),
  currency: msg("Currency"),
  date: msg("Date"),
  notes: msg("Notes"),
};

// Pydantic v2 error `type` -> sentence about `{field}`. Anything not listed
// falls back to the server's own `msg`.
const MESSAGES = {
  greater_than: (t, field, ctx) => t("{field} must be greater than {value}", { field, value: ctx?.gt ?? 0 }),
  greater_than_equal: (t, field, ctx) => t("{field} must be at least {value}", { field, value: ctx?.ge ?? 0 }),
  literal_error: (t, field) => t("{field} has an unsupported value", { field }),
  string_pattern_mismatch: (t, field) => t("{field} has an invalid format (currency must be 3 letters, e.g. USD)", { field }),
  string_too_short: (t, field) => t("{field} is required", { field }),
  missing: (t, field) => t("{field} is required", { field }),
  finite_number: (t, field) => t("{field} must be a finite number", { field }),
  float_parsing: (t, field) => t("{field} must be a number", { field }),
  date_from_datetime_parsing: (t, field) => t("{field} must be a valid date", { field }),
  date_parsing: (t, field) => t("{field} must be a valid date", { field }),
  date_type: (t, field) => t("{field} must be a valid date", { field }),
};

function describeItem(item, t) {
  if (typeof item === "string") return item.trim();
  if (!item || typeof item !== "object") return "";

  const field = Array.isArray(item.loc)
    ? [...item.loc].reverse().find((part) => typeof part === "string" && part !== "body")
    : undefined;
  const label = field ? (FIELD_LABELS[field] ? t(FIELD_LABELS[field]) : field) : "";

  const known = MESSAGES[item.type];
  if (known) {
    // Without a field the sentence starts at the verb ("must be ..."): drop the
    // empty placeholder and the space after it.
    return known(t, label).trim();
  }

  // "Value error, ..." is pydantic's wrapper around a custom validator message.
  const text = typeof item.msg === "string" ? item.msg.replace(/^Value error,\s*/i, "").trim() : "";
  if (!text) return "";
  return label ? `${label}: ${text}` : text;
}

export function formatValidationDetail(detail, { t = english, fallback } = {}) {
  const fallbackText = fallback ?? t("The server rejected the request.");

  if (typeof detail === "string") return detail.trim() || fallbackText;

  if (Array.isArray(detail)) {
    const sentences = detail.map((item) => describeItem(item, t)).filter(Boolean);
    return sentences.length ? [...new Set(sentences)].join("; ") : fallbackText;
  }

  return fallbackText;
}
