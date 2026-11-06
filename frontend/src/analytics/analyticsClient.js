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
    person_profiles: "identified_only",
    cross_subdomain_cookie: true,
    persistence: "localStorage+cookie",
    secure_cookie: true,
  };
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
