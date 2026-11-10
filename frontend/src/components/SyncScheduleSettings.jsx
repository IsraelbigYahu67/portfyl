import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import { fetchSyncSchedule, updateSyncSchedule } from "../api";
import SegmentedControl from "./ui/SegmentedControl";
import { msg, useT } from "../i18n/I18nProvider";

const MODE_OPTIONS = [
  { value: "daily", label: msg("Daily at") },
  { value: "interval", label: msg("Every N hours") },
];

// Global card on the Settings page: when do brokers with auto-sync enabled
// check for new trades. Mirrors GET/PUT /api/settings/sync-schedule.
export default function SyncScheduleSettings() {
  const t = useT();
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
      setSuccess(t("Schedule saved"));
      queryClient.invalidateQueries({ queryKey: ["sync-schedule"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (err) => {
      setSuccess(null);
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("Failed to save schedule"));
    },
  });

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
      <div>
        <h2 className="text-lg font-semibold">{t("Auto-sync schedule")}</h2>
        <p className="text-sm text-muted mt-0.5">
          {t("When connected brokers with auto-sync enabled check for new trades.")}
          {schedule?.timezone && <> {t("Times are in {timezone}.", { timezone: schedule.timezone })}</>}
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
          {t("Failed to load sync schedule")}
        </div>
      ) : isLoading || mode === null ? (
        <Loader2 size={18} className="animate-spin text-muted" />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SegmentedControl
              aria-label={t("Sync mode")}
              value={mode}
              onChange={setMode}
              options={MODE_OPTIONS.map((option) => ({ ...option, label: t(option.label) }))}
            />
            {mode === "daily" ? (
              <input
                type="time"
                aria-label={t("Sync time")}
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
                  aria-label={t("Hours between syncs")}
                  value={intervalHours}
                  onChange={(e) => setIntervalHours(e.target.value)}
                  className="input w-24 min-h-11 md:min-h-0"
                />
                <span>{t("hours")}</span>
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
              {t("Save schedule")}
            </button>
            <div className="text-xs text-muted space-y-0.5">
              <div>
                {schedule?.last_run
                  ? t("Last sync: {time}", { time: new Date(schedule.last_run).toLocaleString() })
                  : t("Last sync: never")}
              </div>
              <div>
                {schedule?.next_run
                  ? t("Next sync: {time}", { time: new Date(schedule.next_run).toLocaleString() })
                  : t("Next sync: at the next check (within a minute)")}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
