function falseAsync() {
  return Promise.resolve(false);
}

export function createNoopAdapter() {
  return Object.freeze({
    init: falseAsync,
    capture: falseAsync,
    identify: falseAsync,
    reset: falseAsync,
    shutdown: falseAsync,
  });
}

export function createMemoryAdapter() {
  const events = [];
  let identifiedId = null;
  let resetCount = 0;
  let initialized = false;

  return {
    get events() { return events; },
    get identifiedId() { return identifiedId; },
    get resetCount() { return resetCount; },
    async init() {
      initialized = true;
      return true;
    },
    async capture(name, properties) {
      if (!initialized) return false;
      events.push([name, properties]);
      return true;
    },
    async identify(id) {
      if (!initialized) return false;
      identifiedId = id;
      return true;
    },
    async reset() {
      identifiedId = null;
      resetCount += 1;
      return true;
    },
    async shutdown() {
      initialized = false;
      return true;
    },
    clear() {
      events.length = 0;
      identifiedId = null;
      resetCount = 0;
      initialized = false;
    },
  };
}

function buildOptions({ host }) {
  return {
    api_host: host,
    ui_host: "https://eu.posthog.com",
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    disable_session_recording: true,
    // The SDK would fetch /array/<key>/config.js from eu-assets.i.posthog.com,
    // which our CSP (script-src 'self') blocks on every load. Recording,
    // autocapture and surveys are off, so that script is not needed.
    disable_external_dependency_loading: true,
    // Feature flags are not used (runbook: "flags stay disabled"). Without this
    // the SDK POSTs /flags/ on every load, sending the anonymous id, timezone and
    // initial URL for nothing.
    advanced_disable_flags: true,
    person_profiles: "identified_only",
    cross_subdomain_cookie: true,
    persistence: "localStorage+cookie",
    secure_cookie: true,
  };
}

const POSTHOG_STORAGE_KEY = /^ph_.+_posthog$/;
const POSTHOG_OPT_KEY_PREFIX = "__ph_opt_in_out_";

// Removes everything the PostHog SDK persisted in this browser (its identity
// in localStorage/sessionStorage and the cookie, which cross_subdomain_cookie
// scopes to the parent domain). Called whenever consent is not "accepted", so
// withdrawing consent leaves no analytics identifier behind, not even the
// fresh random one the SDK writes on reset(). Never throws.
export function clearPostHogStorage() {
  for (const getStore of [() => localStorage, () => sessionStorage]) {
    try {
      const store = getStore();
      for (const key of Object.keys(store)) {
        if (POSTHOG_STORAGE_KEY.test(key) || key.startsWith(POSTHOG_OPT_KEY_PREFIX)) store.removeItem(key);
      }
    } catch {
      /* Storage may be unavailable (private browsing, blocked cookies). */
    }
  }
  try {
    const labels = String(globalThis.location?.hostname || "").split(".");
    const domains = [""];
    for (let i = 0; i < labels.length - 1; i += 1) domains.push(`.${labels.slice(i).join(".")}`);
    for (const pair of document.cookie.split("; ")) {
      const name = pair.split("=")[0];
      if (!POSTHOG_STORAGE_KEY.test(name)) continue;
      for (const domain of domains) {
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${domain ? `; domain=${domain}` : ""}`;
      }
    }
  } catch {
    /* Cookies may be unavailable. */
  }
}

// PostHog is loaded only after an explicit "accepted" decision. A rejected or
// pending choice gets the no-op adapter: the SDK is never imported or
// initialized, so nothing (not even cookieless events) leaves the browser.
// Privacy review 2026-11-06, finding A1.
export function loadPostHogAdapter(config, { importPostHog = () => import("posthog-js") } = {}) {
  if (!config?.key || config.consent !== "accepted") return createNoopAdapter();

  let client = null;
  let initialized = false;
  let initPromise = null;

  async function init() {
    if (initialized) return true;
    if (initPromise) return initPromise;
    initPromise = (async () => {
      try {
        const module = await importPostHog();
        client = module.default || module;
        client.init(config.key, buildOptions(config));
        initialized = true;
        return true;
      } catch {
        return false;
      }
    })();
    return initPromise;
  }

  async function call(method, ...args) {
    if (!initialized || !client || typeof client[method] !== "function") return false;
    try {
      client[method](...args);
      return true;
    } catch {
      return false;
    }
  }

  return {
    init,
    capture: (name, properties) => call("capture", name, properties),
    identify: (id) => call("identify", id),
    reset: () => call("reset"),
    shutdown: async () => {
      const result = await call("shutdown");
      initialized = false;
      return result;
    },
  };
}
