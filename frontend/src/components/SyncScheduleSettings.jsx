import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import { fetchSyncSchedule, updateSyncSchedule } from "../api";

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
        <p className="text-sm text-slate-500 mt-0.5">
          When connected brokers with auto-sync enabled check for new trades.
          {schedule?.timezone && <> Times are in {schedule.timezone}.</>}
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <AlertCircle size={16} className="shrink-0" />
          {error}
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 text-sm text-emerald-600 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
          <CheckCircle2 size={16} className="shrink-0" />
          {success}
        </div>
      )}

      {isError ? (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <AlertCircle size={16} className="shrink-0" />
          Failed to load sync schedule
        </div>
      ) : isLoading || mode === null ? (
        <Loader2 size={18} className="animate-spin text-slate-400" />
      ) : (
        <div className="space-y-4">
          <div className="space-y-3">
            <label className="flex items-center gap-3 text-sm text-slate-700">
              <input
                type="radio"
                name="sync-mode"
                checked={mode === "daily"}
                onChange={() => setMode("daily")}
              />
              <span>Daily at</span>
              <input
                type="time"
                value={dailyTime}
                onChange={(e) => setDailyTime(e.target.value)}
                disabled={mode !== "daily"}
                className="bg-surface border border-surface-border rounded-lg px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:border-brand disabled:opacity-40"
              />
            </label>
            <label className="flex items-center gap-3 text-sm text-slate-700">
              <input
                type="radio"
                name="sync-mode"
                checked={mode === "interval"}
                onChange={() => setMode("interval")}
              />
              <span>Every</span>
              <input
                type="number"
                min="1"
                max="168"
                value={intervalHours}
                onChange={(e) => setIntervalHours(e.target.value)}
                disabled={mode !== "interval"}
                className="w-20 bg-surface border border-surface-border rounded-lg px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:border-brand disabled:opacity-40"
              />
              <span>hours</span>
            </label>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saveMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Clock size={16} />
              )}
              Save schedule
            </button>
            <div className="text-xs text-slate-400 space-y-0.5">
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
