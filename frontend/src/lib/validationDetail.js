// Turns the `detail` of a FastAPI error response into one readable sentence.
// `detail` is a string for HTTPException, but a list of
// {loc, msg, type, ctx} objects for a 422 request-validation error.
// Rendering that list straight into JSX crashes React ("Objects are not valid
// as a React child"), so every form that shows a server error goes through here.

const FIELD_LABELS = {
  en: {
    ticker: "Ticker", type: "Type", shares: "Shares", price: "Price per share",
    currency: "Currency", date: "Date", notes: "Notes",
  },
  cs: {
    ticker: "Ticker", type: "Typ", shares: "Počet kusů", price: "Cena za kus",
    currency: "Měna", date: "Datum", notes: "Poznámka",
  },
};

// Pydantic v2 error `type` -> sentence. Anything not listed falls back to the
// server's own `msg`.
const MESSAGES = {
  en: {
    greater_than: (ctx) => `must be greater than ${ctx?.gt ?? 0}`,
    greater_than_equal: (ctx) => `must be at least ${ctx?.ge ?? 0}`,
    literal_error: () => "has an unsupported value",
    string_pattern_mismatch: () => "has an invalid format (currency must be 3 letters, e.g. USD)",
    string_too_short: () => "is required",
    missing: () => "is required",
    finite_number: () => "must be a finite number",
    float_parsing: () => "must be a number",
    date_from_datetime_parsing: () => "must be a valid date",
    date_parsing: () => "must be a valid date",
    date_type: () => "must be a valid date",
  },
  cs: {
    greater_than: (ctx) => `musí být větší než ${ctx?.gt ?? 0}`,
    greater_than_equal: (ctx) => `musí být alespoň ${ctx?.ge ?? 0}`,
    literal_error: () => "má nepodporovanou hodnotu",
    string_pattern_mismatch: () => "má neplatný formát (měna musí mít 3 písmena, např. USD)",
    string_too_short: () => "je povinné",
    missing: () => "je povinné",
    finite_number: () => "musí být konečné číslo",
    float_parsing: () => "musí být číslo",
    date_from_datetime_parsing: () => "musí být platné datum",
    date_parsing: () => "musí být platné datum",
    date_type: () => "musí být platné datum",
  },
};

const FALLBACKS = {
  en: "The server rejected the request.",
  cs: "Server požadavek odmítl.",
};

export function uiLanguage() {
  const lang = typeof document !== "undefined" ? document.documentElement?.lang : "";
  return typeof lang === "string" && lang.toLowerCase().startsWith("cs") ? "cs" : "en";
}

function describeItem(item, lang) {
  if (typeof item === "string") return item.trim();
  if (!item || typeof item !== "object") return "";

  const field = Array.isArray(item.loc)
    ? [...item.loc].reverse().find((part) => typeof part === "string" && part !== "body")
    : undefined;
  const label = field ? (FIELD_LABELS[lang][field] ?? field) : "";

  const known = MESSAGES[lang][item.type];
  if (known) {
    const text = known(item.ctx);
    return label ? `${label} ${text}` : text;
  }

  // "Value error, ..." is pydantic's wrapper around a custom validator message.
  const msg = typeof item.msg === "string" ? item.msg.replace(/^Value error,\s*/i, "").trim() : "";
  if (!msg) return "";
  return label ? `${label}: ${msg}` : msg;
}

export function formatValidationDetail(detail, { lang = uiLanguage(), fallback } = {}) {
  const language = lang === "cs" ? "cs" : "en";
  const fallbackText = fallback ?? FALLBACKS[language];

  if (typeof detail === "string") return detail.trim() || fallbackText;

  if (Array.isArray(detail)) {
    const sentences = detail.map((item) => describeItem(item, language)).filter(Boolean);
    return sentences.length ? [...new Set(sentences)].join("; ") : fallbackText;
  }

  return fallbackText;
}
