import { useCallback, useEffect, useRef, useState } from "react";
import { createScreenerJob, fetchScreenerJob, cancelScreenerJob } from "../editions/localApi";

const SESSION_KEY = "sb_screener_job_id";
const POLL_MS = 1000;
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

export function useScreenerJob() {
  const [job, setJob] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  const lastRequestRef = useRef(null);
  const intervalRef = useRef(null);
  const pageRef = useRef({ offset: 0, limit: 50 });
  const cancelledJobIdsRef = useRef(new Set());

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const pollOnce = useCallback(async (jobId) => {
    try {
      const data = await fetchScreenerJob(jobId, { ...pageRef.current });
      if (cancelledJobIdsRef.current.has(jobId)) return null;
      setJob(data);
      if (TERMINAL_STATUSES.has(data.status)) {
        stopPolling();
        sessionStorage.removeItem(SESSION_KEY);
      }
      return data;
    } catch {
      // A 404 means the job expired or is gone; stop polling and let the
      // caller decide to retry via createJob again.
      stopPolling();
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
  }, [stopPolling]);

  const startPolling = useCallback((jobId) => {
    stopPolling();
    setIsPolling(true);
    intervalRef.current = setInterval(() => {
      if (document.hidden) return;
      pollOnce(jobId);
    }, POLL_MS);
  }, [pollOnce, stopPolling]);

  const createJob = useCallback(async (params) => {
    lastRequestRef.current = params;
    pageRef.current = { ...pageRef.current, offset: 0 };
    const data = await createScreenerJob(params);
    cancelledJobIdsRef.current.delete(data.job_id);
    setJob(data);
    sessionStorage.setItem(SESSION_KEY, data.job_id);
    if (!TERMINAL_STATUSES.has(data.status)) {
      startPolling(data.job_id);
    }
    return data;
  }, [startPolling]);

  const retry = useCallback(async () => {
    if (!lastRequestRef.current) return null;
    return createJob(lastRequestRef.current);
  }, [createJob]);

  const cancel = useCallback(async () => {
    if (!job?.job_id) return;
    await cancelScreenerJob(job.job_id);
    cancelledJobIdsRef.current.add(job.job_id);
    stopPolling();
    sessionStorage.removeItem(SESSION_KEY);
    setJob((prev) => (prev ? { ...prev, status: "cancelled" } : prev));
  }, [job, stopPolling]);

  // Re-fetch the completed job's requested page. While the scan is running this
  // just updates the page the next poll will read.
  const setPage = useCallback((offset, limit = pageRef.current.limit) => {
    pageRef.current = { offset, limit };
    if (job?.job_id) pollOnce(job.job_id);
  }, [job, pollOnce]);

  useEffect(() => {
    const storedId = sessionStorage.getItem(SESSION_KEY);
    if (storedId) {
      pollOnce(storedId).then((data) => {
        if (data && !TERMINAL_STATUSES.has(data.status)) {
          startPolling(storedId);
        }
      });
    }
    // Intentionally runs once on mount only, to reconnect to a job created
    // before a navigation away and back within the TTL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onVisibility = () => {
      if (!document.hidden && job && !TERMINAL_STATUSES.has(job.status)) {
        pollOnce(job.job_id);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [job, pollOnce]);

  useEffect(() => stopPolling, [stopPolling]);

  return { job, isPolling, createJob, cancel, retry, setPage };
}
