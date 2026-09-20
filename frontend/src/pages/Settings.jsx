import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { AlertCircle, Briefcase, CheckCircle2, Eye, EyeOff, Link as LinkIcon, Loader2, RefreshCw, Unlink } from "lucide-react";

import { connectT212, disconnectT212, fetchT212Status, setT212AutoSync, syncT212 } from "../api";
import { usePortfolio } from "../App";
import DataPrivacySettings from "../components/DataPrivacySettings";
import DiscordSettings from "../components/DiscordSettings";
import PreferencesSettings from "../components/settings/PreferencesSettings";
import PortfolioDataManagement from "../components/settings/PortfolioDataManagement";
import SettingsSectionNav, { SETTINGS_SECTIONS } from "../components/settings/SettingsSectionNav";
import SyncScheduleSettings from "../components/SyncScheduleSettings";
import { AsyncSection } from "../components/ui";
import Toggle from "../components/ui/Toggle";
import { getApiErrorMessage } from "../lib/apiError";
import { useRegisteredActivation } from "../analytics/useRegisteredActivation";

const VALID_SECTIONS = new Set(SETTINGS_SECTIONS.map(({ value }) => value));

function SectionHeading({ id, headingRef, children, description }) {
  return (
    <div>
      <h2 id={id} ref={headingRef} tabIndex={-1} className="text-xl font-semibold outline-none">{children}</h2>
      <p className="mt-1 text-sm text-muted">{description}</p>
    </div>
  );
}

function ConnectionsSettings({ headingRef }) {
  const queryClient = useQueryClient();
  const { current: currentPortfolio } = usePortfolio();
  const { recordPortfolioDataImported } = useRegisteredActivation();
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [success, setSuccess] = useState(null);

  const { data: status, isLoading, error: statusError, refetch: refetchStatus } = useQuery({
    queryKey: ["t212-status", currentPortfolio?.id],
    queryFn: fetchT212Status,
    enabled: currentPortfolio?.id != null,
  });

  const connectMutation = useMutation({
    mutationFn: () => connectT212(apiKey, apiSecret),
    onSuccess: () => {
      setApiKey("");
      setApiSecret("");
      setActionError(null);
      setSuccess("Connected to Trading 212 successfully");
      ["t212-status", "transactions", "holdings", "summary", "portfolios"].forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
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

  const syncMutation = useMutation({
    mutationFn: syncT212,
    onSuccess: (data) => {
      setActionError(null);
      setSuccess(`Synced ${data.total_imported} transactions (${data.imported_orders} orders, ${data.imported_dividends} dividends)`);
      ["t212-status", "transactions", "holdings", "summary", "portfolios", "heatmap", "performance", "movers", "earnings", "dividends", "insider-buys"]
        .forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
      setTimeout(() => setSuccess(null), 6000);
      if (data.total_imported > 0) recordPortfolioDataImported("broker");
    },
    onError: (error) => {
      setSuccess(null);
      setActionError(getApiErrorMessage(error, "Sync failed"));
    },
  });

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
              {status.needs_attention && <div className="flex items-start gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss"><AlertCircle size={16} className="mt-0.5 shrink-0" /><div><div className="font-medium">Auto-sync paused after repeated failures</div>{status.last_error && <div className="mt-0.5 text-xs">{status.last_error}</div>}</div></div>}
              <div className="space-y-2 rounded-lg bg-surface-hover p-4 text-sm">
                <div className="flex justify-between"><span className="text-muted">API Key</span><span className="font-mono text-ink">{status.api_key_preview}</span></div>
                {status.last_synced_at && <div className="flex justify-between"><span className="text-muted">Last synced</span><span>{new Date(status.last_synced_at).toLocaleString()}</span></div>}
                <div className="flex justify-between"><span className="text-muted">Connected since</span><span>{status.connected_at ? new Date(status.connected_at).toLocaleDateString() : "—"}</span></div>
                <div className="flex items-center justify-between pt-1"><span className="text-muted">Auto-sync <span className="ml-2 text-xs">checks on the schedule below</span></span><Toggle checked={status.auto_sync} onChange={(value) => autoSyncMutation.mutate(value)} disabled={autoSyncMutation.isPending} aria-label="T212 auto-sync" /></div>
              </div>
              <div className="flex gap-3">
                <button type="button" onClick={() => syncMutation.mutate()} disabled={busy} className="flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-black disabled:opacity-40">{syncMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}Sync now</button>
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
