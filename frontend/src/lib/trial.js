// Reads the trial out of the /api/billing/status payload. The backend decides
// everything (`source`, `effective_until`, `trial_ended_reason`); this module
// only turns it into what the banner and the Pricing page show. All time maths
// is in UTC milliseconds.
const DAY_MS = 86_400_000;
const ENDED_REASONS = ["expired", "broker_account_reused", "history_reused"];
const FINAL_DAYS = 3; // a dismissed countdown comes back for the last 3 days

const NONE = { phase: "none", daysLeft: null, endsToday: false, endsAt: null, reason: null };

export function trialState(status, now = Date.now()) {
  if (!status) return NONE;
  const reason = status.trial_ended_reason ?? null;

  if (status.source === "trial" && status.effective_until) {
    const ms = Date.parse(status.effective_until) - now;
    if (!Number.isFinite(ms) || ms <= 0) return NONE; // a stale payload
    return {
      phase: "active",
      daysLeft: Math.max(1, Math.ceil(ms / DAY_MS)),
      endsToday: ms < DAY_MS,
      endsAt: status.effective_until,
      reason: null,
    };
  }
  if ((status.source === "free" || status.source === "test_selection") && ENDED_REASONS.includes(reason)) {
    return { ...NONE, phase: "ended", reason };
  }
  if (status.source === "free" && reason === "not_eligible") {
    return { ...NONE, phase: "not_eligible", reason };
  }
  return NONE;
}

// The sentence for the current phase, shared by the banner and Pricing. The
// literals are spelled out here so the i18n tests can see every key.
export function trialMessage(state, t) {
  if (state.phase === "active") {
    if (state.endsToday) return t("Your Pro trial ends today");
    if (state.daysLeft === 1) return t("Pro trial: 1 day left");
    return t("Pro trial: {days} days left", { days: state.daysLeft });
  }
  if (state.phase === "ended") {
    if (state.reason === "broker_account_reused") {
      return t("Your Pro trial ended early, because this broker account already had a free trial in another Portfyl account. Your data stays; anything over the Free limits is read-only.");
    }
    if (state.reason === "history_reused") {
      return t("Your Pro trial ended early, because the same transaction history already had a free trial in another Portfyl account. Your data stays; anything over the Free limits is read-only.");
    }
    return t("Your Pro trial has ended. The account is on the Free plan now: your data stays, and anything over the Free limits is read-only.");
  }
  if (state.phase === "not_eligible") {
    return t("This account starts on the Free plan, because a free trial was already used for this e-mail address or network.");
  }
  return null;
}

// --- dismissal, remembered per workspace on this device ----------------------

export const noticeKey = (workspaceId) => `portfyl_trial_notice:${workspaceId}`;

export function readNoticeSeen(workspaceId) {
  if (!workspaceId) return null;
  try {
    return localStorage.getItem(noticeKey(workspaceId));
  } catch {
    return null;
  }
}

export function markNoticeSeen(workspaceId, value) {
  if (!workspaceId) return;
  try {
    localStorage.setItem(noticeKey(workspaceId), value);
  } catch {
    /* Storage may be unavailable; the notice then simply shows again. */
  }
}

// A notice stays hidden only while the stored value equals the current one, so
// a dismissed countdown returns for the last days and a new end reason shows.
export function noticeValue(state) {
  if (state.phase === "active") return state.daysLeft <= FINAL_DAYS ? "active-final" : "active";
  if (state.phase === "ended") return `ended:${state.reason}`;
  if (state.phase === "not_eligible") return "not_eligible";
  return "";
}
