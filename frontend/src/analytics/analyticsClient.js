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

function buildOptions({ host, consent }) {
  return {
    api_host: host,
    ui_host: "https://eu.posthog.com",
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    disable_session_recording: true,
    person_profiles: "identified_only",
    cross_subdomain_cookie: true,
    persistence: consent === "rejected" ? "memory" : "localStorage+cookie",
    secure_cookie: true,
    cookieless_mode: "on_reject",
  };
}

export function loadPostHogAdapter(config, { importPostHog = () => import("posthog-js") } = {}) {
  if (!config?.key || config.consent === "pending") return createNoopAdapter();

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
        if (config.consent === "rejected") client.opt_out_capturing();
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
    identify: (id) => config.consent === "accepted" ? call("identify", id) : falseAsync(),
    reset: () => call("reset"),
    shutdown: async () => {
      const result = await call("shutdown");
      initialized = false;
      return result;
    },
  };
}
