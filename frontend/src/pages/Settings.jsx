import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { AlertCircle, Briefcase, CheckCircle2, Eye, EyeOff, History, Link as LinkIcon, Loader2, RefreshCw, Unlink } from "lucide-react";

import { connectT212, disconnectT212, setT212AutoSync } from "../api";
import { useCurrency, usePortfolio } from "../App";
import BrokerPositionSnapshot from "../components/BrokerPositionSnapshot";
import DataPrivacySettings from "../components/DataPrivacySettings";
import DiscordSettings from "../components/DiscordSettings";
import PreferencesSettings from "../components/settings/PreferencesSettings";
import PortfolioDataManagement from "../components/settings/PortfolioDataManagement";
import SettingsSectionNav, { SETTINGS_SECTIONS } from "../components/settings/SettingsSectionNav";
import SyncScheduleSettings from "../components/SyncScheduleSettings";
import { AsyncSection } from "../components/ui";
import Toggle from "../components/ui/Toggle";
import { getApiErrorMessage } from "../lib/apiError";
import { T212_HISTORY_ACTIVE_STATES, useT212Sync } from "../hooks/useT212Sync";

const VALID_SECTIONS = new Set(SETTINGS_SECTIONS.map(({ value }) => value));

function SectionHeading({ id, headingRef, children, description }) {
  return (
    <div>
      <h2 id={id} ref={headingRef} tabIndex={-1} className="text-xl font-semibold outline-none">{children}</h2>
      <p className="mt-1 text-sm text-muted">{description}</p>
    </div>
  );
}

// A T212 sync now returns a resumable history-backfill run (see
// docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md, Task 3) that
// a background job keeps advancing after this request returns. This polls
// its progress while active and stops once it reaches a terminal state.
const HISTORY_STATE_LABEL = {
  pending: "Queued",
  fetching: "Downloading history…",
  waiting_rate_limit: "Waiting for Trading 212…",
  finalizing: "Finalizing history…",
  completed: "History imported",
  needs_review: "Needs review",
  failed: "Import failed",
  cancelled: "Cancelled",
};

const FILL_TYPE_LABEL = {
  STOCK_SPLIT: "Stock split",
  STOCK_DISTRIBUTION: "Stock distribution",
  SPIN_OFF: "Spin-off",
  STOCK_ACQUISITION: "Acquisition",
  FOP: "Free-of-payment transfer",
  FOP_CORRECTION: "Transfer correction",
};

export function HistoryBackfillStatus({ run, onRetry, retryPending = false }) {
  if (!run) return null;

  const active = T212_HISTORY_ACTIVE_STATES.has(run.state);
  const label = HISTORY_STATE_LABEL[run.state] ?? run.state;

  return (
    <div className="space-y-2 rounded-lg bg-surface-hover p-4 text-sm">
      <div className="flex items-center gap-2">
        {active ? <Loader2 size={14} className="animate-spin text-brand" aria-hidden="true" /> : <History size={14} className="text-muted" aria-hidden="true" />}
        <span className="font-medium text-ink">{label}</span>
      </div>
      <p className="text-xs text-muted">
        {run.orders_loaded} order{run.orders_loaded === 1 ? "" : "s"} and {run.dividends_loaded} dividend{run.dividends_loaded === 1 ? "" : "s"} loaded so far.
        {active && " Continuing in the background — this page can be closed."}
      </p>
      {run.state === "completed" && (
        <p className="text-xs text-muted">The history import is complete and historical analytics are up to date.</p>
      )}
      {run.state === "waiting_rate_limit" && run.resume_at && (
        <p className="text-xs text-muted">Continuing automatically after <time dateTime={run.resume_at}>{new Date(run.resume_at).toLocaleString()}</time>.</p>
      )}
      {run.last_error && (
        <p className="flex items-center gap-1.5 text-xs text-loss"><AlertCircle size={12} aria-hidden="true" />{run.last_error}</p>
      )}
      {run.state === "needs_review" && run.review && (
        <div className="space-y-2 text-xs text-muted">
          <ul className="space-y-0.5 text-ink">
            {run.review.items.map((item) => (
              <li key={`${item.fill_type}-${item.ticker}-${item.date}`}>
                {FILL_TYPE_LABEL[item.fill_type] ?? item.fill_type} · {item.ticker ?? "unknown"} · {item.date ?? "unknown date"}
              </li>
            ))}
          </ul>
          {run.review.csv_covers_all ? (
            <p>Your imported Trading 212 CSV already covers this history, so a retry can import it.</p>
          ) : run.review.csv_needed_through && (
            <p>
              To import this history now, import a <Link to="/import" className="text-brand underline">Trading 212 CSV export</Link> that
              covers at least through {run.review.csv_needed_through}, then retry.
            </p>
          )}
          <button
            type="button"
            onClick={onRetry}
            disabled={retryPending}
            className="flex items-center gap-2 rounded-lg border border-surface-border px-3 py-1.5 text-xs font-semibold text-ink disabled:opacity-40"
          >
            {retryPending ? <Loader2 size={12} className="animate-spin" aria-hidden="true" /> : <RefreshCw size={12} aria-hidden="true" />}
            Retry history import
          </button>
        </div>
      )}
    </div>
  );
}

function ConnectionsSettings({ headingRef }) {
  const queryClient = useQueryClient();
  const { current: currentPortfolio } = usePortfolio();
  const currency = useCurrency()?.currency ?? "USD";
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [success, setSuccess] = useState(null);

  const t212 = useT212Sync({ portfolioId: currentPortfolio?.id, currency });
  const { data: status, isLoading, error: statusError, refetch: refetchStatus } = t212.statusQuery;

  const connectMutation = useMutation({
    mutationFn: () => connectT212(apiKey, apiSecret),
    onSuccess: () => {
      setApiKey("");
      setApiSecret("");
      setActionError(null);
      setSuccess("Connected to Trading 212 successfully");
      ["t212-status", "t212-history-status", "transactions", "holdings", "summary", "portfolios"].forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (error) => {
      setSuccess(null);
      setActionError(getApiErrorMessage(error, "Failed to connect"));
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: disconnectT212,
    onSuccess: () => {
      setActionError(null);
      setSuccess("Disconnected from Trading 212");
      queryClient.invalidateQueries({ queryKey: ["t212-status"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (error) => {
      setSuccess(null);
      setActionError(getApiErrorMessage(error, "Failed to disconnect"));
    },
  });

  const syncMutation = t212.syncMutation;
  const handleSync = () => {
    t212.sync(undefined, {
      onSuccess: (data) => {
        setActionError(null);
        const snapshotMessage = data.snapshot?.status === "ready"
          ? "Snapshot refreshed."
          : "Snapshot partially refreshed.";
        setSuccess(`${snapshotMessage} History continues in the background.`);
        setTimeout(() => setSuccess(null), 6000);
      },
      onError: (error) => {
        setSuccess(null);
        setActionError(getApiErrorMessage(error, "Sync failed"));
      },
    });
  };

  const handleRetry = () => {
    t212.retryHistory(undefined, {
      onSuccess: () => setActionError(null),
      onError: (error) => {
        setSuccess(null);
        setActionError(getApiErrorMessage(error, "Retry failed"));
      },
    });
  };

  const autoSyncMutation = useMutation({
    mutationFn: setT212AutoSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["t212-status"] }),
    onError: (error) => setActionError(getApiErrorMessage(error, "Failed to update auto-sync")),
  });

  const connected = status?.connected === true;
  const busy = connectMutation.isPending || disconnectMutation.isPending || syncMutation.isPending;

  return (
    <section aria-labelledby="settings-connections-heading" className="space-y-6">
      <SectionHeading id="settings-connections-heading" headingRef={headingRef} description="Connect providers and control how portfolio data is synchronized.">Connections</SectionHeading>

      {currentPortfolio && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-surface-border bg-surface-card px-4 py-2.5 text-sm text-muted">
          <Briefcase size={14} className="text-brand" aria-hidden="true" />
          <span>Managing connection for portfolio</span>
          <span className="font-medium text-ink">{currentPortfolio.name}</span>
          <span className="ml-auto text-xs">Each portfolio holds its own Trading 212 API key — data is never mixed.</span>
        </div>
      )}

      <AsyncSection isLoading={isLoading} error={statusError} onRetry={() => refetchStatus()} loading={<div className="h-52 animate-pulse rounded-xl border border-surface-border bg-surface-card" />}>
        <div className="space-y-5 rounded-xl border border-surface-border bg-surface-card p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold">Trading 212</h3>
              <p className="mt-0.5 text-sm text-muted">Connect your account to import transactions into <span className="text-ink">{currentPortfolio?.name ?? "this portfolio"}</span>.</p>
            </div>
            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${connected ? "bg-gain/10 text-gain" : "bg-surface-hover text-muted"}`}>{connected ? "Connected" : "Not connected"}</span>
          </div>

          {actionError && <div role="alert" className="flex items-center gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss"><AlertCircle size={16} />{actionError}</div>}
          {success && <div role="status" className="flex items-center gap-2 rounded-lg border border-gain/30 bg-gain/10 px-4 py-3 text-sm text-gain"><CheckCircle2 size={16} />{success}</div>}

          {!connected && (
            <div className="space-y-3">
              <div>
                <label htmlFor="t212-api-key" className="mb-1.5 block text-sm text-muted">API Key</label>
                <div className="relative">
                  <input id="t212-api-key" type={showKey ? "text" : "password"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Paste your Trading 212 API key" className="w-full rounded-lg border border-surface-border bg-surface px-4 py-2.5 pr-10 text-sm" />
                  <button type="button" aria-label={showKey ? "Hide API key" : "Show API key"} onClick={() => setShowKey((visible) => !visible)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink">{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
                </div>
                <p className="mt-1.5 text-xs text-muted">Generate an API key in Trading 212 → Settings → API (beta)</p>
              </div>
              <div>
                <label htmlFor="t212-api-secret" className="mb-1.5 block text-sm text-muted">API Secret</label>
                <input id="t212-api-secret" type="password" value={apiSecret} onChange={(event) => setApiSecret(event.target.value)} placeholder="Paste your Trading 212 API secret" className="w-full rounded-lg border border-surface-border bg-surface px-4 py-2.5 text-sm" />
              </div>
              <button type="button" onClick={() => connectMutation.mutate()} disabled={!apiKey.trim() || !apiSecret.trim() || busy} className="flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-black disabled:opacity-40">{connectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <LinkIcon size={16} />}Connect</button>
            </div>
          )}

          {connected && (
            <div className="space-y-4">
              {status.needs_attention && <div className="flex items-start gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss"><AlertCircle size={16} className="mt-0.5 shrink-0" /><div><div className="font-medium">Connection needs attention</div>{status.last_error && <div className="mt-0.5 text-xs">{status.last_error}</div>}</div></div>}
              <div className="space-y-2 rounded-lg bg-surface-hover p-4 text-sm">
                <div className="flex justify-between"><span className="text-muted">API Key</span><span className="font-mono text-ink">{status.api_key_preview}</span></div>
                {status.last_synced_at && <div className="flex justify-between"><span className="text-muted">Last synced</span><span>{new Date(status.last_synced_at).toLocaleString()}</span></div>}
                <div className="flex justify-between"><span className="text-muted">Connected since</span><span>{status.connected_at ? new Date(status.connected_at).toLocaleDateString() : "—"}</span></div>
                <div className="flex items-center justify-between pt-1"><span className="text-muted">Auto-sync <span className="ml-2 text-xs">checks on the schedule below</span></span><Toggle checked={status.auto_sync} onChange={(value) => autoSyncMutation.mutate(value)} disabled={autoSyncMutation.isPending} aria-label="T212 auto-sync" /></div>
              </div>
              <BrokerPositionSnapshot query={t212.positionsQuery} />
              <HistoryBackfillStatus run={t212.historyRun} onRetry={handleRetry} retryPending={t212.retryPending} />
              <div className="flex gap-3">
                <button type="button" onClick={handleSync} disabled={busy} className="flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-black disabled:opacity-40">{syncMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}Sync now</button>
                <button type="button" onClick={() => disconnectMutation.mutate()} disabled={busy} className="flex items-center gap-2 rounded-lg border border-red-200 px-5 py-2.5 text-sm font-semibold text-red-600 disabled:opacity-40">{disconnectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Unlink size={16} />}Disconnect</button>
              </div>
            </div>
          )}
        </div>
      </AsyncSection>

      <SyncScheduleSettings />
    </section>
  );
}

function NotificationsSettings({ headingRef }) {
  return (
    <section aria-labelledby="settings-notifications-heading" className="space-y-6">
      <SectionHeading id="settings-notifications-heading" headingRef={headingRef} description="Choose where price alerts and other enabled notifications are delivered.">Notifications</SectionHeading>
      <DiscordSettings />
    </section>
  );
}

export function DataSettings({ headingRef, children }) {
  return (
    <section aria-labelledby="settings-data-heading" className="space-y-6">
      <SectionHeading id="settings-data-heading" headingRef={headingRef} description="Manage portfolio data, exports, and workspace privacy.">Data & Privacy</SectionHeading>
      {children}
      <DataPrivacySettings />
    </section>
  );
}

export default function Settings({ dataManagement = <PortfolioDataManagement /> }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const headingRef = useRef(null);
  const focusAfterNavigation = useRef(false);
  const requestedSection = searchParams.get("section");
  const section = VALID_SECTIONS.has(requestedSection) ? requestedSection : "connections";

  useEffect(() => {
    if (requestedSection === section) return;
    const normalized = new URLSearchParams(searchParams);
    normalized.set("section", section);
    setSearchParams(normalized, { replace: true });
  }, [requestedSection, searchParams, section, setSearchParams]);

  useEffect(() => {
    if (!focusAfterNavigation.current) return;
    focusAfterNavigation.current = false;
    headingRef.current?.focus();
  }, [section]);

  const selectSection = (nextSection, navigate) => {
    focusAfterNavigation.current = true;
    if (navigate) {
      const next = new URLSearchParams(searchParams);
      next.set("section", nextSection);
      setSearchParams(next);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="mt-1 text-sm text-muted">Manage connections, device preferences, notifications, and your data.</p>
      </div>

      <div className="space-y-5 lg:flex lg:items-start lg:gap-8 lg:space-y-0">
        <SettingsSectionNav value={section} searchParams={searchParams} onSelect={selectSection} />
        <div className="min-w-0 flex-1">
          {section === "connections" && <ConnectionsSettings headingRef={headingRef} />}
          {section === "preferences" && <PreferencesSettings headingRef={headingRef} />}
          {section === "notifications" && <NotificationsSettings headingRef={headingRef} />}
          {section === "data" && <DataSettings headingRef={headingRef}>{dataManagement}</DataSettings>}
        </div>
      </div>
    </div>
  );
}
