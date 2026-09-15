import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useScreenerJob } from "./useScreenerJob";
import * as localApi from "../editions/localApi";

const SESSION_KEY = "sb_screener_job_id";

describe("useScreenerJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    vi.spyOn(localApi, "createScreenerJob");
    vi.spyOn(localApi, "fetchScreenerJob");
    vi.spyOn(localApi, "cancelScreenerJob");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("creates a job, stores its id in sessionStorage, and polls every second", async () => {
    localApi.createScreenerJob.mockResolvedValue({ job_id: "j1", status: "queued", progress: { completed: 0, total: 0, percent: 0 }, result: null, error: null });
    localApi.fetchScreenerJob.mockResolvedValue({ job_id: "j1", status: "running", progress: { completed: 5, total: 10, percent: 50 }, result: null, error: null });

    const { result } = renderHook(() => useScreenerJob());

    await act(async () => {
      await result.current.createJob({ universe: "sp500" });
    });

    expect(sessionStorage.getItem(SESSION_KEY)).toBe("j1");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(localApi.fetchScreenerJob).toHaveBeenCalledWith("j1", expect.any(Object));
  });

  it("pauses polling while the tab is hidden and resumes on visibility", async () => {
    localApi.createScreenerJob.mockResolvedValue({ job_id: "j2", status: "queued", progress: { completed: 0, total: 0, percent: 0 }, result: null, error: null });
    localApi.fetchScreenerJob.mockResolvedValue({ job_id: "j2", status: "running", progress: { completed: 1, total: 10, percent: 10 }, result: null, error: null });

    const { result } = renderHook(() => useScreenerJob());
    await act(async () => {
      await result.current.createJob({ universe: "sp500" });
    });

    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));

    const callsWhileHidden = localApi.fetchScreenerJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(localApi.fetchScreenerJob.mock.calls.length).toBe(callsWhileHidden);

    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(localApi.fetchScreenerJob.mock.calls.length).toBeGreaterThan(callsWhileHidden);
  });

  it("reconnects to a job id already in sessionStorage on mount", async () => {
    sessionStorage.setItem(SESSION_KEY, "j3");
    localApi.fetchScreenerJob.mockResolvedValue({ job_id: "j3", status: "completed", progress: { completed: 10, total: 10, percent: 100 }, result: { items: [], total: 0, offset: 0, limit: 50 }, error: null });

    const { result } = renderHook(() => useScreenerJob());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.job?.job_id).toBe("j3");
    expect(localApi.createScreenerJob).not.toHaveBeenCalled();
  });

  it("clears sessionStorage and stops polling once status is a terminal state", async () => {
    localApi.createScreenerJob.mockResolvedValue({ job_id: "j4", status: "queued", progress: { completed: 0, total: 0, percent: 0 }, result: null, error: null });
    localApi.fetchScreenerJob.mockResolvedValue({ job_id: "j4", status: "completed", progress: { completed: 5, total: 5, percent: 100 }, result: { items: [], total: 0, offset: 0, limit: 50 }, error: null });

    const { result } = renderHook(() => useScreenerJob());
    await act(async () => {
      await result.current.createJob({ universe: "sp500" });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.job.status).toBe("completed");

    const callsAfterCompletion = localApi.fetchScreenerJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(localApi.fetchScreenerJob.mock.calls.length).toBe(callsAfterCompletion);
  });

  it("cancel() calls the cancel endpoint with the current job id", async () => {
    localApi.createScreenerJob.mockResolvedValue({ job_id: "j5", status: "running", progress: { completed: 1, total: 10, percent: 10 }, result: null, error: null });
    localApi.cancelScreenerJob.mockResolvedValue({ job_id: "j5", status: "cancelled" });

    const { result } = renderHook(() => useScreenerJob());
    await act(async () => {
      await result.current.createJob({ universe: "sp500" });
    });
    await act(async () => {
      await result.current.cancel();
    });
    expect(localApi.cancelScreenerJob).toHaveBeenCalledWith("j5");
    expect(result.current.job.status).toBe("cancelled");
  });
});
