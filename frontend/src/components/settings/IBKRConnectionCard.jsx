import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, Clock, Eye, EyeOff, Info, Link as LinkIcon, Loader2, RefreshCw, Unlink } from "lucide-react";

import { connectIBKR, disconnectIBKR, fetchIBKRStatus, setIBKRAutoSync, syncIBKR } from "../../api";
import { AsyncSection } from "../ui";
import Toggle from "../ui/Toggle";
import { Badge } from "../ui/Badge";
import { getApiErrorMessage } from "../../lib/apiError";
import { useBrokerPortfolio } from "../../hooks/useBrokerPortfolio";
import { splitNote } from "../../lib/brokerPortfolio";
import { rich, translate, useT } from "../../i18n/I18nProvider";

import { IBKR_FLEX_SECTIONS } from "../../lib/ibkrFlex";

export { IBKR_FLEX_SECTIONS };

// Without `t` the messages read in English (tests, non-component callers).
const english = (text, vars) => translate(null, text, vars);

function newTransactions(count, t) {
  return count === 1 ? t("{count} new transaction", { count }) : t("{count} new transactions", { count });
}

function newTrades(count, t) {
  return count === 1 ? t("{count} new trade", { count }) : t("{count} new trades", { count });
}

// Turns the sync response's `ledger` (backend/ibkr_ledger.py) into a message.
export function describeLedger(ledger, t = english) {
  if (!ledger) return null;
  switch (ledger.status) {
    case "imported":
      return {
        tone: "success",
        title: t("Stocks, ETFs, dividends and cash imported"),
        detail: t("{imported}, {present} already present.", {
          imported: newTransactions(ledger.imported ?? 0, t),
          present: ledger.already_present ?? 0,
        }),
      };
    case "needs_review":
      return {
        tone: "error",
        title: t("Stocks and cash need review — nothing was imported"),
        detail: ledger.errors?.[0] ?? t("The statement could not be imported as-is."),
      };
    case "deferred":
      return {
        tone: "info",
        title: t("Instrument lookup unavailable"),
        detail: t("Stocks, ETFs, dividends and cash will be retried automatically on the next sync."),
      };
    case "sections_missing":
      return {
        tone: "info",
        title: t("Flex Query is missing sections"),
        detail: t("Your Flex Query has no Trades or Cash Transactions section, so only options were synced. Add the sections listed in the setup guide below."),
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
  const t = useT();
  if (!result) return null;
  const ledger = describeLedger(result.ledger, t);
  const options = t("Options: {trades}, {updated} updated.", {
    trades: newTrades(result.imported ?? 0, t),
    updated: result.updated ?? 0,
  });
  const tone = ledger?.tone ?? "success";
  const Icon = TONE_ICON[tone];
  return (
    <div role="status" aria-label={t("IBKR sync result")} className={`flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${TONE_CLASS[tone]}`}>
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
  const t = useT();
  // IBKR's menu and option names stay as IBKR shows them, in <b> / <code>.
  const ink = (text) => rich(text, {
    b: (words) => <span className="text-ink">{words}</span>,
    code: (words) => <code className="font-mono text-ink">{words}</code>,
  });
  return (
    <details className="rounded-lg bg-surface-hover p-4 text-sm">
      <summary className="cursor-pointer font-medium text-ink">{t("How to set up the IBKR Flex Query")}</summary>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-muted">
        <li>{ink(t("In the IBKR portal open <b>Performance & Reports → Flex Queries</b> and create an <b>Activity Flex Query</b>."))}</li>
        <li>
          {t("Enable these sections (select all fields in each):")}
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {IBKR_FLEX_SECTIONS.map(([section, level]) => (
              <li key={section}><span className="text-ink">{section}</span>{level && ` — ${t(level)}`}</li>
            ))}
          </ul>
        </li>
        <li>
          {ink(t("Delivery configuration: format <b>XML</b>, date format <code>yyyyMMdd</code>, time format <code>HHmmss</code>, date/time separator <code>;</code> (semicolon)."))}{" "}
          {ink(t("Period: <b>Last 365 calendar days</b>."))}
        </li>
        <li>{ink(t("Save the query and copy its <b>Query ID</b>. Then open <b>Flex Web Service Configuration</b>, enable it and generate a token."))}</li>
        <li>{t("Paste the token and Query ID above. Lynx accounts use the same steps.")}</li>
      </ol>
      <p className="mt-3 flex items-start gap-2 text-xs text-muted">
        <Info size={14} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
        <span>
          {rich(t("The sync only sees the last 365 days. For older history, run the same query in the portal once per year and upload each XML file on the <link>Import page</link>. Transactions already imported are recognized and skipped."), {
            link: (words) => <Link to="/import" className="text-brand underline">{words}</Link>,
          })}
        </span>
      </p>
    </details>
  );
}

export default function IBKRConnectionCard({ portfolioId, portfolioName }) {
  const t = useT();
  const queryClient = useQueryClient();
  const brokerPortfolio = useBrokerPortfolio();
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
    setActionError(getApiErrorMessage(error, fallback, t));
  };

  const connectMutation = useMutation({
    mutationFn: async () => {
      // A portfolio holding another broker's data gets IBKR in a new one.
      const session = await brokerPortfolio.open("ibkr");
      try {
        await connectIBKR(flexToken.trim(), queryId.trim());
      } catch (error) {
        await brokerPortfolio.discard(session).catch(() => {});
        throw error;
      }
      return session;
    },
    onSuccess: (session) => {
      setFlexToken("");
      setQueryId("");
      setSyncResult(null);
      flash(`${t("Connected to IBKR. Run a sync to import your statement.")}${splitNote(session, "ibkr", t)}`);
      queryClient.invalidateQueries({ queryKey: ["ibkr-status"] });
    },
    onError: fail(t("Failed to connect")),
  });

  const disconnectMutation = useMutation({
    mutationFn: disconnectIBKR,
    onSuccess: () => {
      setSyncResult(null);
      flash(t("Disconnected from IBKR"));
      queryClient.invalidateQueries({ queryKey: ["ibkr-status"] });
    },
    onError: fail(t("Failed to disconnect")),
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
      fail(t("Sync failed"))(error);
    },
  });

  const autoSyncMutation = useMutation({
    mutationFn: setIBKRAutoSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ibkr-status"] }),
    onError: fail(t("Failed to update auto-sync")),
  });

  const connected = status?.connected === true;
  const busy = connectMutation.isPending || disconnectMutation.isPending || syncMutation.isPending;

  return (
    <AsyncSection isLoading={isLoading} error={statusError} onRetry={() => refetch()} loading={<div className="h-52 animate-pulse rounded-xl border border-surface-border bg-surface-card" />}>
      <section aria-label={t("Interactive Brokers connection")} className="space-y-5 rounded-xl border border-surface-border bg-surface-card p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">Interactive Brokers</h3>
            <p className="mt-0.5 text-sm text-muted">
              {rich(t("The Flex Web Service sync imports stocks, ETFs, dividends and cash into <b>{portfolio}</b>, alongside your options trades.", { portfolio: portfolioName ?? t("this portfolio") }), {
                b: (name) => <span className="text-ink">{name}</span>,
              })}
            </p>
          </div>
          <Badge tone={connected ? "gain" : "neutral"} className="shrink-0">{connected ? t("Connected") : t("Not connected")}</Badge>
        </div>

        {actionError && <div role="alert" className="flex items-center gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss"><AlertCircle size={16} />{actionError}</div>}
        {success && <div role="status" className="flex items-center gap-2 rounded-lg border border-gain/30 bg-gain/10 px-4 py-3 text-sm text-gain"><CheckCircle2 size={16} />{success}</div>}

        {!connected && (
          <div className="space-y-3">
            <div>
              <label htmlFor="ibkr-flex-token" className="mb-1.5 block text-sm text-muted">{t("Flex Web Service token")}</label>
              <div className="relative">
                <input id="ibkr-flex-token" type={showToken ? "text" : "password"} value={flexToken} onChange={(event) => setFlexToken(event.target.value)} placeholder={t("Paste your Flex Web Service token")} autoComplete="off" className="input pr-10 text-sm" />
                <button type="button" aria-label={showToken ? t("Hide token") : t("Show token")} onClick={() => setShowToken((visible) => !visible)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink">{showToken ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
            </div>
            <div>
              <label htmlFor="ibkr-query-id" className="mb-1.5 block text-sm text-muted">{t("Flex Query ID")}</label>
              <input id="ibkr-query-id" type="text" inputMode="numeric" value={queryId} onChange={(event) => setQueryId(event.target.value)} placeholder={t("e.g. 123456")} autoComplete="off" className="input text-sm" />
            </div>
            <button type="button" onClick={() => connectMutation.mutate()} disabled={!flexToken.trim() || !queryId.trim() || busy} className="btn-primary flex items-center gap-2 text-sm min-h-11 md:min-h-0 disabled:opacity-40">{connectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <LinkIcon size={16} />}{t("Connect")}</button>
          </div>
        )}

        {connected && (
          <div className="space-y-4">
            {status.needs_attention && (
              <div className="flex items-start gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <div><div className="font-medium">{t("Connection needs attention")}</div>{status.last_error && <div className="mt-0.5 text-xs">{status.last_error}</div>}</div>
              </div>
            )}
            <div className="space-y-2 rounded-lg bg-surface-hover p-4 text-sm">
              <div className="flex justify-between"><span className="text-muted">{t("Token")}</span><span className="font-mono text-ink">{status.token_preview}</span></div>
              {status.last_synced_at && <div className="flex justify-between"><span className="text-muted">{t("Last synced")}</span><span>{new Date(status.last_synced_at).toLocaleString()}</span></div>}
              <div className="flex justify-between"><span className="text-muted">{t("Connected since")}</span><span>{status.connected_at ? new Date(status.connected_at).toLocaleDateString() : "—"}</span></div>
              <div className="flex items-center justify-between pt-1"><span className="text-muted">{t("Auto-sync")} <span className="ml-2 text-xs">{t("checks on the schedule below")}</span></span><Toggle checked={status.auto_sync} onChange={(value) => autoSyncMutation.mutate(value)} disabled={autoSyncMutation.isPending} aria-label={t("IBKR auto-sync")} /></div>
            </div>
            <IBKRSyncOutcome result={syncResult} />
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={() => syncMutation.mutate()} disabled={busy} className="btn-primary flex items-center gap-2 text-sm min-h-11 md:min-h-0 disabled:opacity-40">{syncMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}{syncMutation.isPending ? t("Syncing… (up to a minute)") : t("Sync now")}</button>
              <button type="button" onClick={() => disconnectMutation.mutate()} disabled={busy} className="btn-ghost text-loss flex items-center gap-2 text-sm font-semibold min-h-11 md:min-h-0 disabled:opacity-40">{disconnectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Unlink size={16} />}{t("Disconnect")}</button>
            </div>
          </div>
        )}

        <IBKRFlexGuide />
      </section>
    </AsyncSection>
  );
}
