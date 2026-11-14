// The dashboard's "Getting started" checklist: which steps a new workspace has
// finished, and what the visitor has dismissed or opened. Step state comes from
// data (portfolios, preferences); only the dividends visit and the dismissal
// are remembered, per workspace, on this device. Storage may be unavailable
// (private browsing): reads then report "nothing stored" and writes are
// ignored, never thrown.
export const GETTING_STARTED_IDS = ["first_portfolio", "second_broker", "preferences", "dividends"];

const DEMO_BROKER = "demo";
const storageKey = (workspaceId) => `portfyl_getting_started:${workspaceId}`;

function realBrokers(portfolios = []) {
  const brokers = new Set();
  for (const portfolio of portfolios ?? []) {
    for (const broker of portfolio?.brokers ?? []) {
      if (broker && broker !== DEMO_BROKER) brokers.add(broker);
    }
  }
  return brokers;
}

export function gettingStartedItems({ portfolios, preferencesConfirmed, visited = [] }) {
  const brokers = realBrokers(portfolios);
  const done = {
    first_portfolio: brokers.size >= 1,
    second_broker: brokers.size >= 2,
    preferences: Boolean(preferencesConfirmed),
    dividends: visited.includes("dividends"),
  };
  const destination = {
    first_portfolio: "/import",
    second_broker: "/import",
    preferences: "/settings?section=preferences",
    dividends: "/dividends",
  };
  return GETTING_STARTED_IDS.map((id) => ({ id, done: done[id], to: destination[id] }));
}

const DEFAULTS = () => ({ dismissed: false, visited: [] });

export function readGettingStarted(workspaceId) {
  if (!workspaceId) return DEFAULTS();
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey(workspaceId)));
    if (!stored || typeof stored !== "object") return DEFAULTS();
    return {
      dismissed: stored.dismissed === true,
      visited: Array.isArray(stored.visited)
        ? stored.visited.filter((id) => GETTING_STARTED_IDS.includes(id))
        : [],
    };
  } catch {
    return DEFAULTS();
  }
}

function write(workspaceId, state) {
  if (!workspaceId) return;
  try {
    localStorage.setItem(storageKey(workspaceId), JSON.stringify(state));
  } catch {
    /* Storage may be unavailable; the checklist then simply shows again. */
  }
}

export function markGettingStartedVisited(workspaceId, id) {
  const state = readGettingStarted(workspaceId);
  if (!GETTING_STARTED_IDS.includes(id) || state.visited.includes(id)) return;
  write(workspaceId, { ...state, visited: [...state.visited, id] });
}

export function dismissGettingStarted(workspaceId) {
  write(workspaceId, { ...readGettingStarted(workspaceId), dismissed: true });
}
