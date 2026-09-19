const STORAGE_PREFIX = "portfyl_activation_v1:";
const VALID_SOURCE_TYPES = new Set(["demo", "csv", "broker"]);

function buildKey(userId, workspaceId) {
  return `${STORAGE_PREFIX}${userId}:${workspaceId}`;
}

function emptyState() {
  return { sourceType: null, dataImported: false, dashboardRendered: false, activated: false };
}

function isValidState(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    (value.sourceType === null || VALID_SOURCE_TYPES.has(value.sourceType)) &&
    typeof value.dataImported === "boolean" &&
    typeof value.dashboardRendered === "boolean" &&
    typeof value.activated === "boolean"
  );
}

// Rejected/pending sessions never touch localStorage; this Map is the only
// place their activation progress lives, and it is intentionally scoped to
// the module (one browser tab), not to any single hook instance, so that
// Onboarding and Dashboard -- separate mounts -- see the same in-session state.
const memoryStore = new Map();

export function readActivationState(userId, workspaceId, { persist }) {
  const key = buildKey(userId, workspaceId);
  if (!persist) {
    return memoryStore.has(key) ? memoryStore.get(key) : emptyState();
  }
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return emptyState();
    const parsed = JSON.parse(raw);
    return isValidState(parsed) ? parsed : emptyState();
  } catch {
    return emptyState();
  }
}

export function writeActivationState(userId, workspaceId, state, { persist }) {
  const key = buildKey(userId, workspaceId);
  if (!persist) {
    memoryStore.set(key, state);
    return;
  }
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch {
    /* Storage may be unavailable (private browsing, blocked cookies); the
       session simply loses persistence, which is safe to drop silently. */
  }
}
