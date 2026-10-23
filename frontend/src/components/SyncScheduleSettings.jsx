import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import { fetchSyncSchedule, updateSyncSchedule } from "../api";
import SegmentedControl from "./ui/SegmentedControl";

const MODE_OPTIONS = [
  { value: "daily", label: "Daily at" },
  { value: "interval", label: "Every N hours" },
];

// Global card on the Settings page: when do brokers with auto-sync enabled
// check for new trades. Mirrors GET/PUT /api/settings/sync-schedule.
export default function SyncScheduleSettings() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState(null); // null = form not seeded from the server yet
  const [dailyTime, setDailyTime] = useState("02:00");
  const [intervalHours, setIntervalHours] = useState(6);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const { data: schedule, isLoading, isError } = useQuery({
    queryKey: ["sync-schedule"],
    queryFn: fetchSyncSchedule,
  });

  useEffect(() => {
    if (schedule && mode === null) {
      setMode(schedule.mode);
      setDailyTime(schedule.daily_time);
      setIntervalHours(schedule.interval_hours);
    }
  }, [schedule, mode]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateSyncSchedule({ mode, daily_time: dailyTime, interval_hours: Number(intervalHours) }),
    onSuccess: () => {
      setError(null);
      setSuccess("Schedule saved");
      queryClient.invalidateQueries({ queryKey: ["sync-schedule"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (err) => {
      setSuccess(null);
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to save schedule");
    },
  });

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Auto-sync schedule</h2>
        <p className="text-sm text-muted mt-0.5">
          When connected brokers with auto-sync enabled check for new trades.
          {schedule?.timezone && <> Times are in {schedule.timezone}.</>}
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3">
          <AlertCircle size={16} className="shrink-0" />
          {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 text-sm text-gain bg-gain/10 border border-gain/30 rounded-lg px-4 py-3">
          <CheckCircle2 size={16} className="shrink-0" />
          {success}
        </div>
      )}

      {isError ? (
        <div className="flex items-center gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3">
          <AlertCircle size={16} className="shrink-0" />
          Failed to load sync schedule
        </div>
      ) : isLoading || mode === null ? (
        <Loader2 size={18} className="animate-spin text-muted" />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SegmentedControl aria-label="Sync mode" value={mode} onChange={setMode} options={MODE_OPTIONS} />
            {mode === "daily" ? (
              <input
                type="time"
                aria-label="Sync time"
                value={dailyTime}
                onChange={(e) => setDailyTime(e.target.value)}
                className="input w-auto min-h-11 md:min-h-0"
              />
            ) : (
              <span className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="number"
                  min="1"
                  max="168"
                  aria-label="Hours between syncs"
                  value={intervalHours}
                  onChange={(e) => setIntervalHours(e.target.value)}
                  className="input w-24 min-h-11 md:min-h-0"
                />
                <span>hours</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="btn-primary flex items-center gap-2 text-sm min-h-11 md:min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saveMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Clock size={16} />
              )}
              Save schedule
            </button>
            <div className="text-xs text-muted space-y-0.5">
              <div>
                Last sync:{" "}
                {schedule?.last_run ? new Date(schedule.last_run).toLocaleString() : "never"}
              </div>
              <div>
                Next sync:{" "}
                {schedule?.next_run
                  ? new Date(schedule.next_run).toLocaleString()
                  : "at the next check (within a minute)"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
