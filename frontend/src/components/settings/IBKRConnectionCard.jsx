import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, Clock, Eye, EyeOff, Info, Link as LinkIcon, Loader2, RefreshCw, Unlink } from "lucide-react";

import { connectIBKR, disconnectIBKR, fetchIBKRStatus, setIBKRAutoSync, syncIBKR } from "../../api";
import { AsyncSection } from "../ui";
import Toggle from "../ui/Toggle";
import { getApiErrorMessage } from "../../lib/apiError";

// Sections the Activity Flex Query needs for the stock/ETF/dividend/cash
// import (backend/importers/formats/ibkr_flex.py). Options only need Trades.
export const IBKR_FLEX_SECTIONS = [
  ["Trades", "Execution level"],
  ["Cash Transactions", "Detail level"],
  ["Corporate Actions", null],
  ["Transfers", null],
  ["Open Positions", null],
  ["Account Information", null],
];

function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

// Turns the sync response's `ledger` (backend/ibkr_ledger.py) into a message.
export function describeLedger(ledger) {
  if (!ledger) return null;
  switch (ledger.status) {
    case "imported":
      return {
        tone: "success",
        title: "Stocks, ETFs, dividends and cash imported",
        detail: `${plural(ledger.imported ?? 0, "new transaction")}, ${ledger.already_present ?? 0} already present.`,
      };
    case "needs_review":
      return {
        tone: "error",
        title: "Stocks and cash need review — nothing was imported",
        detail: ledger.errors?.[0] ?? "The statement could not be imported as-is.",
      };
    case "deferred":
      return {
        tone: "info",
        title: "Instrument lookup unavailable",
        detail: "Stocks, ETFs, dividends and cash will be retried automatically on the next sync.",
      };
    case "sections_missing":
      return {
        tone: "info",
        title: "Flex Query is missing sections",
        detail: "Your Flex Query has no Trades or Cash Transactions section, so only options were synced. Add the sections listed in the setup guide below.",
      };
    default:
      return null;
  }
}

const TONE_CLASS = {
  success: "border-gain/30 bg-gain/10 text-gain",
  error: "border-loss/30 bg-loss/10 text-loss",
  info: "border-surface-border bg-surface-hover text-ink",
};
const TONE_ICON = { success: CheckCircle2, error: AlertCircle, info: Clock };

export function IBKRSyncOutcome({ result }) {
  if (!result) return null;
  const ledger = describeLedger(result.ledger);
  const options = `Options: ${plural(result.imported ?? 0, "new trade")}, ${result.updated ?? 0} updated.`;
  const tone = ledger?.tone ?? "success";
  const Icon = TONE_ICON[tone];
  return (
    <div role="status" aria-label="IBKR sync result" className={`flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${TONE_CLASS[tone]}`}>
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      <div className="space-y-0.5">
        {ledger && <div className="font-medium">{ledger.title}</div>}
        {ledger && <div className="text-xs">{ledger.detail}</div>}
        <div className="text-xs text-muted">{options}</div>
      </div>
    </div>
  );
}

export function IBKRFlexGuide() {
  return (
    <details className="rounded-lg bg-surface-hover p-4 text-sm">
      <summary className="cursor-pointer font-medium text-ink">How to set up the IBKR Flex Query</summary>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-muted">
        <li>In the IBKR portal open <span className="text-ink">Performance &amp; Reports → Flex Queries</span> and create an <span className="text-ink">Activity Flex Query</span>.</li>
        <li>
          Enable these sections (select all fields in each):
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {IBKR_FLEX_SECTIONS.map(([section, level]) => (
              <li key={section}><span className="text-ink">{section}</span>{level && ` — ${level}`}</li>
            ))}
          </ul>
        </li>
        <li>
          Delivery configuration: format <span className="text-ink">XML</span>, date format <code className="font-mono text-ink">yyyyMMdd</code>,
          time format <code className="font-mono text-ink">HHmmss</code>, date/time separator <code className="font-mono text-ink">;</code> (semicolon).
          Period: <span className="text-ink">Last 365 calendar days</span>.
        </li>
        <li>Save the query and copy its <span className="text-ink">Query ID</span>. Then open <span className="text-ink">Flex Web Service Configuration</span>, enable it and generate a token.</li>
        <li>Paste the token and Query ID above. Lynx accounts use the same steps.</li>
      </ol>
      <p className="mt-3 flex items-start gap-2 text-xs text-muted">
        <Info size={14} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
        <span>
          The sync only sees the last 365 days. For older history, run the same query in the portal once per year
          and upload each XML file on the <Link to="/import" className="text-brand underline">Import page</Link>.
          Transactions already imported are recognized and skipped.
        </span>
      </p>
    </details>
  );
}

export default function IBKRConnectionCard({ portfolioId, portfolioName }) {
  const queryClient = useQueryClient();
  const [flexToken, setFlexToken] = useState("");
  const [queryId, setQueryId] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [syncResult, setSyncResult] = useState(null);

  const { data: status, isLoading, error: statusError, refetch } = useQuery({
    queryKey: ["ibkr-status", portfolioId],
    queryFn: fetchIBKRStatus,
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
    mutationFn: () => connectIBKR(flexToken.trim(), queryId.trim()),
    onSuccess: () => {
      setFlexToken("");
      setQueryId("");
      setSyncResult(null);
      flash("Connected to IBKR. Run a sync to import your statement.");
      queryClient.invalidateQueries({ queryKey: ["ibkr-status"] });
    },
    onError: fail("Failed to connect"),
  });

  const disconnectMutation = useMutation({
    mutationFn: disconnectIBKR,
    onSuccess: () => {
      setSyncResult(null);
      flash("Disconnected from IBKR");
      queryClient.invalidateQueries({ queryKey: ["ibkr-status"] });
    },
    onError: fail("Failed to disconnect"),
  });

  const syncMutation = useMutation({
    mutationFn: syncIBKR,
    onSuccess: (data) => {
      setActionError(null);
      setSuccess(null);
      setSyncResult(data);
      // The ledger import changes holdings, cash and dividends everywhere;
      // this also refetches the status, which carries any review message.
      queryClient.invalidateQueries();
    },
    onError: (error) => {
      setSyncResult(null);
      fail("Sync failed")(error);
    },
  });

  const autoSyncMutation = useMutation({
    mutationFn: setIBKRAutoSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ibkr-status"] }),
    onError: fail("Failed to update auto-sync"),
  });

  const connected = status?.connected === true;
  const busy = connectMutation.isPending || disconnectMutation.isPending || syncMutation.isPending;

  return (
    <AsyncSection isLoading={isLoading} error={statusError} onRetry={() => refetch()} loading={<div className="h-52 animate-pulse rounded-xl border border-surface-border bg-surface-card" />}>
      <section aria-label="Interactive Brokers connection" className="space-y-5 rounded-xl border border-surface-border bg-surface-card p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">Interactive Brokers</h3>
            <p className="mt-0.5 text-sm text-muted">
              The Flex Web Service sync imports stocks, ETFs, dividends and cash into <span className="text-ink">{portfolioName ?? "this portfolio"}</span>, alongside your options trades.
            </p>
          </div>
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${connected ? "bg-gain/10 text-gain" : "bg-surface-hover text-muted"}`}>{connected ? "Connected" : "Not connected"}</span>
        </div>

        {actionError && <div role="alert" className="flex items-center gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss"><AlertCircle size={16} />{actionError}</div>}
        {success && <div role="status" className="flex items-center gap-2 rounded-lg border border-gain/30 bg-gain/10 px-4 py-3 text-sm text-gain"><CheckCircle2 size={16} />{success}</div>}

        {!connected && (
          <div className="space-y-3">
            <div>
              <label htmlFor="ibkr-flex-token" className="mb-1.5 block text-sm text-muted">Flex Web Service token</label>
              <div className="relative">
                <input id="ibkr-flex-token" type={showToken ? "text" : "password"} value={flexToken} onChange={(event) => setFlexToken(event.target.value)} placeholder="Paste your Flex Web Service token" autoComplete="off" className="w-full rounded-lg border border-surface-border bg-surface px-4 py-2.5 pr-10 text-sm" />
                <button type="button" aria-label={showToken ? "Hide token" : "Show token"} onClick={() => setShowToken((visible) => !visible)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink">{showToken ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
            </div>
            <div>
              <label htmlFor="ibkr-query-id" className="mb-1.5 block text-sm text-muted">Flex Query ID</label>
              <input id="ibkr-query-id" type="text" inputMode="numeric" value={queryId} onChange={(event) => setQueryId(event.target.value)} placeholder="e.g. 123456" autoComplete="off" className="w-full rounded-lg border border-surface-border bg-surface px-4 py-2.5 text-sm" />
            </div>
            <button type="button" onClick={() => connectMutation.mutate()} disabled={!flexToken.trim() || !queryId.trim() || busy} className="flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-black disabled:opacity-40">{connectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <LinkIcon size={16} />}Connect</button>
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
              <div className="flex justify-between"><span className="text-muted">Token</span><span className="font-mono text-ink">{status.token_preview}</span></div>
              {status.last_synced_at && <div className="flex justify-between"><span className="text-muted">Last synced</span><span>{new Date(status.last_synced_at).toLocaleString()}</span></div>}
              <div className="flex justify-between"><span className="text-muted">Connected since</span><span>{status.connected_at ? new Date(status.connected_at).toLocaleDateString() : "—"}</span></div>
              <div className="flex items-center justify-between pt-1"><span className="text-muted">Auto-sync <span className="ml-2 text-xs">checks on the schedule below</span></span><Toggle checked={status.auto_sync} onChange={(value) => autoSyncMutation.mutate(value)} disabled={autoSyncMutation.isPending} aria-label="IBKR auto-sync" /></div>
            </div>
            <IBKRSyncOutcome result={syncResult} />
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={() => syncMutation.mutate()} disabled={busy} className="flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-black disabled:opacity-40">{syncMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}{syncMutation.isPending ? "Syncing… (up to a minute)" : "Sync now"}</button>
              <button type="button" onClick={() => disconnectMutation.mutate()} disabled={busy} className="flex items-center gap-2 rounded-lg border border-red-200 px-5 py-2.5 text-sm font-semibold text-red-600 disabled:opacity-40">{disconnectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Unlink size={16} />}Disconnect</button>
            </div>
          </div>
        )}

        <IBKRFlexGuide />
      </section>
    </AsyncSection>
  );
}
