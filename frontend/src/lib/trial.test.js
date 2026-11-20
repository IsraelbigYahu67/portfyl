import { afterEach, describe, expect, it, vi } from "vitest";

import { markNoticeSeen, noticeKey, noticeValue, readNoticeSeen, trialMessage, trialState } from "./trial";

const NOW = Date.parse("2026-11-20T12:00:00Z");
const HOUR = 3_600_000;
const iso = (ms) => new Date(NOW + ms).toISOString();

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("trialState", () => {
  it("counts whole days left while the trial runs", () => {
    expect(trialState({ source: "trial", effective_until: iso(10 * 24 * HOUR) }, NOW))
      .toMatchObject({ phase: "active", daysLeft: 10, endsToday: false });
  });

  it("says it ends today under 24 hours, and never shows 0 days", () => {
    expect(trialState({ source: "trial", effective_until: iso(23 * HOUR) }, NOW))
      .toMatchObject({ phase: "active", daysLeft: 1, endsToday: true });
    expect(trialState({ source: "trial", effective_until: iso(1) }, NOW).daysLeft).toBe(1);
  });

  it("treats a stale trial payload whose end has passed as no trial", () => {
    expect(trialState({ source: "trial", effective_until: iso(-HOUR) }, NOW).phase).toBe("none");
  });

  it("reports why a trial ended", () => {
    expect(trialState({ source: "free", trial_ended_reason: "expired" }, NOW))
      .toMatchObject({ phase: "ended", reason: "expired" });
    expect(trialState({ source: "test_selection", trial_ended_reason: "history_reused" }, NOW))
      .toMatchObject({ phase: "ended", reason: "history_reused" });
  });

  it("reports a withheld trial", () => {
    expect(trialState({ source: "free", trial_ended_reason: "not_eligible" }, NOW).phase).toBe("not_eligible");
  });

  it("shows nothing for a subscription, local, trials off or no status", () => {
    expect(trialState({ source: "subscription", trial_ended_reason: null }, NOW).phase).toBe("none");
    expect(trialState({ source: "local" }, NOW).phase).toBe("none");
    expect(trialState({ source: "free", trial_ended_reason: null }, NOW).phase).toBe("none");
    expect(trialState(null, NOW).phase).toBe("none");
  });
});

describe("noticeValue and trialMessage", () => {
  it("switches to the final value for the last 3 days", () => {
    expect(noticeValue({ phase: "active", daysLeft: 4 })).toBe("active");
    expect(noticeValue({ phase: "active", daysLeft: 3 })).toBe("active-final");
    expect(noticeValue({ phase: "ended", reason: "expired" })).toBe("ended:expired");
    expect(noticeValue({ phase: "not_eligible" })).toBe("not_eligible");
  });

  it("phrases each phase", () => {
    const t = (key, values) => key.replace("{days}", values?.days);
    expect(trialMessage({ phase: "active", daysLeft: 6, endsToday: false }, t)).toBe("Pro trial: 6 days left");
    expect(trialMessage({ phase: "active", daysLeft: 1, endsToday: false }, t)).toBe("Pro trial: 1 day left");
    expect(trialMessage({ phase: "active", daysLeft: 1, endsToday: true }, t)).toBe("Your Pro trial ends today");
    expect(trialMessage({ phase: "none" }, t)).toBeNull();
  });
});

describe("notice storage", () => {
  it("round-trips per workspace", () => {
    markNoticeSeen("ws-1", "active");
    expect(localStorage.getItem(noticeKey("ws-1"))).toBe("active");
    expect(readNoticeSeen("ws-1")).toBe("active");
    expect(readNoticeSeen("ws-2")).toBeNull();
  });

  it("returns null when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readNoticeSeen("ws-1")).toBeNull();
  });
});
