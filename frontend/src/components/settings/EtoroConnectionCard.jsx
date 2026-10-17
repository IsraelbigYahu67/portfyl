import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Eye, EyeOff, Info, Link as LinkIcon, Loader2, RefreshCw, Unlink } from "lucide-react";

import { connectEtoro, disconnectEtoro, fetchEtoroStatus, setEtoroAutoSync, syncEtoro } from "../../api";
import { AsyncSection } from "../ui";
import Toggle from "../ui/Toggle";
import { getApiErrorMessage } from "../../lib/apiError";
import { useBrokerPortfolio } from "../../hooks/useBrokerPortfolio";
import { splitNote } from "../../lib/brokerPortfolio";

function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

// Turns the sync response (backend/routers/etoro.py etoro_sync) into a message.
export function describeEtoroSync(result) {
  if (!result) return null;
  if (result.status === "needs_review") {
    return {
      tone: "error",
      title: "eToro positions need review — nothing was imported",
      detail: result.errors?.[0] ?? "The eToro account could not be imported as-is.",
    };
  }
  return {
    tone: "success",
    title: "eToro positions imported",
    detail: `${plural(result.imported ?? 0, "new transaction")}, ${result.already_present ?? 0} already present.`,
  };
}

const TONE_CLASS = {
  success: "border-gain/30 bg-gain/10 text-gain",
  error: "border-loss/30 bg-loss/10 text-loss",
};

function SyncOutcome({ result }) {
  const message = describeEtoroSync(result);
  if (!message) return null;
  const skipped = Object.entries(result.skipped_reasons ?? {}).filter(([, count]) => count > 0);
  const Icon = message.tone === "error" ? AlertCircle : CheckCircle2;
  return (
    <div role="status" aria-label="eToro sync result" className={`flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${TONE_CLASS[message.tone]}`}>
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      <div className="space-y-0.5">
        <div className="font-medium">{message.title}</div>
        <div className="text-xs">{message.detail}</div>
        {skipped.length > 0 && (
          <ul aria-label="Skipped eToro positions" className="text-xs text-muted">
            {skipped.map(([reason, count]) => <li key={reason}>{reason} <span className="tabular-nums">× {count}</span></li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

function KeyGuide() {
  return (
    <details className="rounded-lg bg-surface-hover p-4 text-sm">
      <summary className="cursor-pointer font-medium text-ink">How to create an eToro API key</summary>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-muted">
        <li>In eToro open <span className="text-ink">Settings → Trading → API Key Management</span>.</li>
        <li>Create a new key with the <span className="text-ink">Read</span> permission for the <span className="text-ink">Real</span> environment.</li>
        <li>Copy the key and paste it above. Portfyl can only read your account; it cannot trade.</li>
      </ol>
    </details>
  );
}

export default function EtoroConnectionCard({ portfolioId, portfolioName }) {
  const queryClient = useQueryClient();
  const brokerPortfolio = useBrokerPortfolio();
  const [userKey, setUserKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [syncResult, setSyncResult] = useState(null);

  const { data: status, isLoading, error: statusError, refetch } = useQuery({
    queryKey: ["etoro-status", portfolioId],
    queryFn: fetchEtoroStatus,
  });

  const flash = (message) => {
    setActionError(null);
    setSuccess(message);
    setTimeout(() => setSuccess(null), 4000);
  };
  const fail = (fallback) => (error) => {
    setSuccess(null);
    setActionError(getApiErrorMessage(error, fallback));
  };

  const connectMutation = useMutation({
    mutationFn: async () => {
      // A portfolio holding another broker's data gets eToro in a new one.
      const session = await brokerPortfolio.open("etoro");
      try {
        await connectEtoro(userKey.trim());
      } catch (error) {
        await brokerPortfolio.discard(session).catch(() => {});
        throw error;
      }
      return session;
    },
    onSuccess: (session) => {
      setUserKey("");
      setSyncResult(null);
      flash(`Connected to eToro. Run a sync to import your positions.${splitNote(session, "etoro")}`);
      queryClient.invalidateQueries({ queryKey: ["etoro-status"] });
    },
    onError: fail("Failed to connect"),
  });

  const disconnectMutation = useMutation({
    mutationFn: disconnectEtoro,
    onSuccess: () => {
      setSyncResult(null);
      flash("Disconnected from eToro");
      queryClient.invalidateQueries({ queryKey: ["etoro-status"] });
    },
    onError: fail("Failed to disconnect"),
  });

  const syncMutation = useMutation({
    mutationFn: syncEtoro,
    onSuccess: (data) => {
      setActionError(null);
      setSuccess(null);
      setSyncResult(data);
      // New positions change holdings everywhere; this also refetches the
      // status, which carries any review message.
      queryClient.invalidateQueries();
    },
    onError: (error) => {
      setSyncResult(null);
      fail("Sync failed")(error);
    },
  });

  const autoSyncMutation = useMutation({
    mutationFn: setEtoroAutoSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["etoro-status"] }),
    onError: fail("Failed to update auto-sync"),
  });

  const connected = status?.connected === true;
  const configured = status?.configured !== false;
  const busy = connectMutation.isPending || disconnectMutation.isPending || syncMutation.isPending;

  return (
    <AsyncSection isLoading={isLoading} error={statusError} onRetry={() => refetch()} loading={<div className="h-52 animate-pulse rounded-xl border border-surface-border bg-surface-card" />}>
      <section aria-label="eToro connection" className="space-y-5 rounded-xl border border-surface-border bg-surface-card p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">eToro</h3>
            <p className="mt-0.5 text-sm text-muted">
              Imports buys and sells of US-listed stocks, ETFs and crypto into <span className="text-ink">{portfolioName ?? "this portfolio"}</span>.
            </p>
          </div>
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${connected ? "bg-gain/10 text-gain" : "bg-surface-hover text-muted"}`}>{connected ? "Connected" : "Not connected"}</span>
        </div>

        <p className="flex items-start gap-2 text-xs text-muted">
          <Info size={14} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
          <span>Leveraged (CFD), short and copy-trading positions are counted but not imported. Dividends and cash movements are not imported yet.</span>
        </p>

        {actionError && <div role="alert" className="flex items-center gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss"><AlertCircle size={16} />{actionError}</div>}
        {success && <div role="status" className="flex items-center gap-2 rounded-lg border border-gain/30 bg-gain/10 px-4 py-3 text-sm text-gain"><CheckCircle2 size={16} />{success}</div>}

        {!connected && !configured && (
          <div className="rounded-lg bg-surface-hover px-4 py-3 text-sm text-muted">
            The eToro connection is not available on this server yet.
          </div>
        )}

        {!connected && configured && (
          <div className="space-y-3">
            <div>
              <label htmlFor="etoro-user-key" className="mb-1.5 block text-sm text-muted">eToro API key</label>
              <div className="relative">
                <input id="etoro-user-key" type={showKey ? "text" : "password"} value={userKey} onChange={(event) => setUserKey(event.target.value)} placeholder="Paste your eToro API key (Read, Real)" autoComplete="off" className="w-full rounded-lg border border-surface-border bg-surface px-4 py-2.5 pr-10 text-sm" />
                <button type="button" aria-label={showKey ? "Hide key" : "Show key"} onClick={() => setShowKey((visible) => !visible)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink">{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
            </div>
            <button type="button" onClick={() => connectMutation.mutate()} disabled={!userKey.trim() || busy} className="flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-black disabled:opacity-40">{connectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <LinkIcon size={16} />}Connect</button>
            <KeyGuide />
          </div>
        )}

        {connected && (
          <div className="space-y-4">
            {status.needs_attention && (
              <div className="flex items-start gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <div><div className="font-medium">Connection needs attention</div>{status.last_error && <div className="mt-0.5 text-xs">{status.last_error}</div>}</div>
              </div>
            )}
            <div className="space-y-2 rounded-lg bg-surface-hover p-4 text-sm">
              {status.last_synced_at && <div className="flex justify-between"><span className="text-muted">Last synced</span><span>{new Date(status.last_synced_at).toLocaleString()}</span></div>}
              <div className="flex justify-between"><span className="text-muted">Connected since</span><span>{status.connected_at ? new Date(status.connected_at).toLocaleDateString() : "—"}</span></div>
              <div className="flex items-center justify-between pt-1"><span className="text-muted">Auto-sync <span className="ml-2 text-xs">checks on the schedule below</span></span><Toggle checked={status.auto_sync} onChange={(value) => autoSyncMutation.mutate(value)} disabled={autoSyncMutation.isPending} aria-label="eToro auto-sync" /></div>
            </div>
            <SyncOutcome result={syncResult} />
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={() => syncMutation.mutate()} disabled={busy || !configured} className="flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-black disabled:opacity-40">{syncMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}{syncMutation.isPending ? "Syncing…" : "Sync now"}</button>
              <button type="button" onClick={() => disconnectMutation.mutate()} disabled={busy} className="flex items-center gap-2 rounded-lg border border-red-200 px-5 py-2.5 text-sm font-semibold text-red-600 disabled:opacity-40">{disconnectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Unlink size={16} />}Disconnect</button>
            </div>
          </div>
        )}
      </section>
    </AsyncSection>
  );
}
