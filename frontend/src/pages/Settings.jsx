import { Fragment, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { AlertCircle, Briefcase, CheckCircle2, ExternalLink, Eye, EyeOff, History, Link as LinkIcon, Loader2, RefreshCw, Unlink } from "lucide-react";

import { connectT212, disconnectT212, setT212AutoSync } from "../api";
import { useCurrency, usePortfolio } from "../App";
import BrokerPositionSnapshot from "../components/BrokerPositionSnapshot";
import DataPrivacySettings from "../components/DataPrivacySettings";
import DiscordSettings from "../components/DiscordSettings";
import EtoroConnectionCard from "../components/settings/EtoroConnectionCard";
import IBKRConnectionCard from "../components/settings/IBKRConnectionCard";
import PreferencesSettings from "../components/settings/PreferencesSettings";
import PortfolioDataManagement from "../components/settings/PortfolioDataManagement";
import T212ApiGuide from "../components/settings/T212ApiGuide";
import SettingsSectionNav, { SETTINGS_SECTIONS } from "../components/settings/SettingsSectionNav";
import SyncScheduleSettings from "../components/SyncScheduleSettings";
import { AsyncSection } from "../components/ui";
import Toggle from "../components/ui/Toggle";
import { Badge } from "../components/ui/Badge";
import { getApiErrorMessage } from "../lib/apiError";
import { msg, rich, useT } from "../i18n/I18nProvider";
import { useBrokerPortfolio } from "../hooks/useBrokerPortfolio";
import { splitNote } from "../lib/brokerPortfolio";
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
  pending: msg("Queued"),
  fetching: msg("Downloading history…"),
  waiting_rate_limit: msg("Waiting for Trading 212…"),
  finalizing: msg("Finalizing history…"),
  completed: msg("History imported"),
  needs_review: msg("Needs review"),
  failed: msg("Import failed"),
  cancelled: msg("Cancelled"),
};

const FILL_TYPE_LABEL = {
  STOCK_SPLIT: msg("Stock split"),
  STOCK_DISTRIBUTION: msg("Stock distribution"),
  SPIN_OFF: msg("Spin-off"),
  STOCK_ACQUISITION: msg("Acquisition"),
  FOP: msg("Free-of-payment transfer"),
  FOP_CORRECTION: msg("Transfer correction"),
};

function loadedSoFar(run, t) {
  const orders = run.orders_loaded === 1 ? t("{count} order", { count: run.orders_loaded }) : t("{count} orders", { count: run.orders_loaded });
  const dividends = run.dividends_loaded === 1 ? t("{count} dividend", { count: run.dividends_loaded }) : t("{count} dividends", { count: run.dividends_loaded });
  const cashCount = run.cash_loaded ?? 0;
  const cash = cashCount === 1 ? t("{count} cash transaction", { count: cashCount }) : t("{count} cash transactions", { count: cashCount });
  return t("{orders}, {dividends} and {cash} loaded so far.", { orders, dividends, cash });
}

export function HistoryBackfillStatus({ run, onRetry, retryPending = false }) {
  const t = useT();
  if (!run) return null;

  const active = T212_HISTORY_ACTIVE_STATES.has(run.state);
  const label = HISTORY_STATE_LABEL[run.state] ? t(HISTORY_STATE_LABEL[run.state]) : run.state;

  return (
    <div className="space-y-2 rounded-lg bg-surface-hover p-4 text-sm">
      <div className="flex items-center gap-2">
        {active ? <Loader2 size={14} className="animate-spin text-brand" aria-hidden="true" /> : <History size={14} className="text-muted" aria-hidden="true" />}
        <span className="font-medium text-ink">{label}</span>
      </div>
      <p className="text-xs text-muted">
        {loadedSoFar(run, t)}
        {active && ` ${t("Continuing in the background — this page can be closed.")}`}
      </p>
      {run.state === "completed" && (
        <p className="text-xs text-muted">{t("The history import is complete and historical analytics are up to date.")}</p>
      )}
      {run.state === "waiting_rate_limit" && run.resume_at && (
        <p className="text-xs text-muted">
          {rich(t("Continuing automatically after <time>{when}</time>.", { when: new Date(run.resume_at).toLocaleString() }), {
            time: (when) => <time dateTime={run.resume_at}>{when}</time>,
          })}
        </p>
      )}
      {run.last_error && (
        <p className="flex items-center gap-1.5 text-xs text-loss"><AlertCircle size={12} aria-hidden="true" />{run.last_error}</p>
      )}
      {run.state === "needs_review" && run.review && (
        <div className="space-y-2 text-xs text-muted">
          <ul className="space-y-0.5 text-ink">
            {run.review.items.map((item) => (
              <li key={`${item.fill_type}-${item.cash_type}-${item.ticker}-${item.date}`}>
                {item.cash_type !== undefined
                  ? t("Cash transaction ({type}) · {date}", { type: item.cash_type ?? t("unknown type"), date: item.date ?? t("unknown date") })
                  : t("{type} · {ticker} · {date}", {
                    type: FILL_TYPE_LABEL[item.fill_type] ? t(FILL_TYPE_LABEL[item.fill_type]) : item.fill_type,
                    ticker: item.ticker ?? t("unknown"),
                    date: item.date ?? t("unknown date"),
                  })}
              </li>
            ))}
          </ul>
          {run.review.csv_covers_all ? (
            <p>{t("Your imported Trading 212 CSV already covers this history, so a retry can import it.")}</p>
          ) : run.review.csv_needed_through && (
            <p>
              {rich(t("To import this history now, import a <link>Trading 212 CSV export</link> that covers at least through {date}, then retry.", { date: run.review.csv_needed_through }), {
                link: (words) => <Link to="/import" className="text-brand underline">{words}</Link>,
              })}
            </p>
          )}
          <button
            type="button"
            onClick={onRetry}
            disabled={retryPending}
            className="btn-ghost flex items-center gap-2 text-sm font-semibold min-h-11 md:min-h-0 disabled:opacity-40"
          >
            {retryPending ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <RefreshCw size={16} aria-hidden="true" />}
            {t("Retry history import")}
          </button>
        </div>
      )}
    </div>
  );
}

// Order of the broker cards; the broker picked during onboarding
// (?broker=, see pages/Onboarding.jsx) moves to the top.
const CONNECTION_ORDER = ["trading212", "ibkr", "etoro"];

function ConnectionsSettings({ headingRef }) {
  const t = useT();
  const [searchParams] = useSearchParams();
  const requestedBroker = searchParams.get("broker");
  const connectionOrder = CONNECTION_ORDER.includes(requestedBroker)
    ? [requestedBroker, ...CONNECTION_ORDER.filter((key) => key !== requestedBroker)]
    : CONNECTION_ORDER;
  const queryClient = useQueryClient();
  const { current: currentPortfolio } = usePortfolio();
  const brokerPortfolio = useBrokerPortfolio();
  const currency = useCurrency()?.currency ?? "USD";
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [success, setSuccess] = useState(null);

  const t212 = useT212Sync({ portfolioId: currentPortfolio?.id, currency });
  const { data: status, isLoading, error: statusError, refetch: refetchStatus } = t212.statusQuery;

  const connectMutation = useMutation({
    mutationFn: async () => {
      // A portfolio holding another broker's data gets Trading 212 in a new one.
      const session = await brokerPortfolio.open("trading212");
      try {
        await connectT212(apiKey, apiSecret);
      } catch (error) {
        await brokerPortfolio.discard(session).catch(() => {});
        throw error;
      }
      return session;
    },
    onSuccess: (session) => {
      setApiKey("");
      setApiSecret("");
      setActionError(null);
      setSuccess(`${t("Connected to Trading 212 successfully.")}${splitNote(session, "trading212", t)}`);
      // Connecting can also remove onboarding demo data (and demo portfolios),
      // which every portfolio-derived query may still be showing — including
      // long-cached ones such as insider buys, since the holdings changed.
      // Unlike Dashboard's Refresh, this is deliberate: only the few queries
      // active on Settings refetch now, the rest when their page next mounts.
      queryClient.invalidateQueries();
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (error) => {
      setSuccess(null);
      setActionError(getApiErrorMessage(error, t("Failed to connect"), t));
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: disconnectT212,
    onSuccess: () => {
      setActionError(null);
      setSuccess(t("Disconnected from Trading 212"));
      queryClient.invalidateQueries({ queryKey: ["t212-status"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (error) => {
      setSuccess(null);
      setActionError(getApiErrorMessage(error, t("Failed to disconnect"), t));
    },
  });

  const syncMutation = t212.syncMutation;
  const handleSync = () => {
    t212.sync(undefined, {
      onSuccess: (data) => {
        setActionError(null);
        setSuccess(data.snapshot?.status === "ready"
          ? t("Snapshot refreshed. History continues in the background.")
          : t("Snapshot partially refreshed. History continues in the background."));
        setTimeout(() => setSuccess(null), 6000);
      },
      onError: (error) => {
        setSuccess(null);
        setActionError(getApiErrorMessage(error, t("Sync failed"), t));
      },
    });
  };

  const handleRetry = () => {
    t212.retryHistory(undefined, {
      onSuccess: () => setActionError(null),
      onError: (error) => {
        setSuccess(null);
        setActionError(getApiErrorMessage(error, t("Retry failed"), t));
      },
    });
  };

  const autoSyncMutation = useMutation({
    mutationFn: setT212AutoSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["t212-status"] }),
    onError: (error) => setActionError(getApiErrorMessage(error, t("Failed to update auto-sync"), t)),
  });

  const connected = status?.connected === true;
  const busy = connectMutation.isPending || disconnectMutation.isPending || syncMutation.isPending;

  const t212Card = (
      <AsyncSection isLoading={isLoading} error={statusError} onRetry={() => refetchStatus()} loading={<div className="h-52 animate-pulse rounded-xl border border-surface-border bg-surface-card" />}>
        <div className="space-y-5 rounded-xl border border-surface-border bg-surface-card p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold">Trading 212</h3>
              <p className="mt-0.5 text-sm text-muted">{rich(t("Connect your account to import transactions into <b>{portfolio}</b>.", { portfolio: currentPortfolio?.name ?? t("this portfolio") }), {
                b: (name) => <span className="text-ink">{name}</span>,
              })}</p>
            </div>
            <Badge tone={connected ? "gain" : "neutral"} className="shrink-0">{connected ? t("Connected") : t("Not connected")}</Badge>
          </div>

          {actionError && <div role="alert" className="flex items-center gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss"><AlertCircle size={16} />{actionError}</div>}
          {success && <div role="status" className="flex items-center gap-2 rounded-lg border border-gain/30 bg-gain/10 px-4 py-3 text-sm text-gain"><CheckCircle2 size={16} />{success}</div>}

          {!connected && (
            <div className="space-y-3">
              <T212ApiGuide />
              <div>
                <label htmlFor="t212-api-key" className="mb-1.5 block text-sm text-muted">{t("API key ID")}</label>
                <div className="relative">
                  <input id="t212-api-key" type={showKey ? "text" : "password"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={t("Paste API key ID here")} className="input pr-10 text-sm" />
                  <button type="button" aria-label={showKey ? t("Hide API key") : t("Show API key")} onClick={() => setShowKey((visible) => !visible)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink">{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button>
                </div>
              </div>
              <div>
                <label htmlFor="t212-api-secret" className="mb-1.5 block text-sm text-muted">{t("Secret key")}</label>
                <input id="t212-api-secret" type="password" value={apiSecret} onChange={(event) => setApiSecret(event.target.value)} placeholder={t("Paste Secret Key here")} className="input text-sm" />
              </div>
              <button type="button" onClick={() => connectMutation.mutate()} disabled={!apiKey.trim() || !apiSecret.trim() || busy} className="btn-primary flex items-center gap-2 text-sm min-h-11 md:min-h-0 disabled:opacity-40">{connectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <LinkIcon size={16} />}{t("Connect")}</button>
            </div>
          )}

          {connected && (
            <div className="space-y-4">
              {status.needs_attention && <div className="flex items-start gap-2 rounded-lg border border-loss/30 bg-loss/10 px-4 py-3 text-sm text-loss"><AlertCircle size={16} className="mt-0.5 shrink-0" /><div><div className="font-medium">{t("Connection needs attention")}</div>{status.last_error && <div className="mt-0.5 text-xs">{status.last_error}</div>}</div></div>}
              <div className="space-y-2 rounded-lg bg-surface-hover p-4 text-sm">
                <div className="flex justify-between"><span className="text-muted">{t("API Key")}</span><span className="font-mono text-ink">{status.api_key_preview}</span></div>
                {status.last_synced_at && <div className="flex justify-between"><span className="text-muted">{t("Last synced")}</span><span>{new Date(status.last_synced_at).toLocaleString()}</span></div>}
                <div className="flex justify-between"><span className="text-muted">{t("Connected since")}</span><span>{status.connected_at ? new Date(status.connected_at).toLocaleDateString() : "—"}</span></div>
                <div className="flex items-center justify-between pt-1"><span className="text-muted">{t("Auto-sync")} <span className="ml-2 text-xs">{t("checks on the schedule below")}</span></span><Toggle checked={status.auto_sync} onChange={(value) => autoSyncMutation.mutate(value)} disabled={autoSyncMutation.isPending} aria-label={t("T212 auto-sync")} /></div>
              </div>
              <BrokerPositionSnapshot query={t212.positionsQuery} variant="summary" />
              <HistoryBackfillStatus run={t212.historyRun} onRetry={handleRetry} retryPending={t212.retryPending} />
              <div className="flex gap-3">
                <button type="button" onClick={handleSync} disabled={busy} className="btn-primary flex items-center gap-2 text-sm min-h-11 md:min-h-0 disabled:opacity-40">{syncMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}{t("Sync now")}</button>
                <button type="button" onClick={() => disconnectMutation.mutate()} disabled={busy} className="btn-ghost text-loss flex items-center gap-2 text-sm font-semibold min-h-11 md:min-h-0 disabled:opacity-40">{disconnectMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Unlink size={16} />}{t("Disconnect")}</button>
              </div>
            </div>
          )}
        </div>
      </AsyncSection>
  );
  const connectionCards = {
    trading212: t212Card,
    ibkr: <IBKRConnectionCard portfolioId={currentPortfolio?.id} portfolioName={currentPortfolio?.name} />,
    etoro: <EtoroConnectionCard portfolioId={currentPortfolio?.id} portfolioName={currentPortfolio?.name} />,
  };

  return (
    <section aria-labelledby="settings-connections-heading" className="space-y-6">
      <SectionHeading id="settings-connections-heading" headingRef={headingRef} description={t("Connect providers and control how portfolio data is synchronized.")}>{t("Connections")}</SectionHeading>

      {currentPortfolio && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-surface-border bg-surface-card px-4 py-2.5 text-sm text-muted">
          <Briefcase size={14} className="text-brand" aria-hidden="true" />
          <span>{t("Managing connection for portfolio")}</span>
          <span className="font-medium text-ink">{currentPortfolio.name}</span>
          <span className="ml-auto text-xs">{t("Each portfolio holds its own broker connections — data is never mixed.")}</span>
        </div>
      )}

      {connectionOrder.map((key) => <Fragment key={key}>{connectionCards[key]}</Fragment>)}

      <SyncScheduleSettings />
    </section>
  );
}

function NotificationsSettings({ headingRef }) {
  const t = useT();
  return (
    <section aria-labelledby="settings-notifications-heading" className="space-y-6">
      <SectionHeading id="settings-notifications-heading" headingRef={headingRef} description={t("Choose where price alerts and other enabled notifications are delivered.")}>{t("Notifications")}</SectionHeading>
      <DiscordSettings />
    </section>
  );
}

export function DataSettings({ headingRef, children }) {
  const t = useT();
  return (
    <section aria-labelledby="settings-data-heading" className="space-y-6">
      <SectionHeading id="settings-data-heading" headingRef={headingRef} description={t("Manage portfolio data, exports, and workspace privacy.")}>{t("Data & Privacy")}</SectionHeading>
      <LegalDocuments />
      {children}
      <DataPrivacySettings />
    </section>
  );
}

// Cloud only: the public /terms and /privacy pages render outside the app's
// router (Root.jsx), so these are plain links that open a new tab. The
// documents exist in English and Czech only, so each link names its language.
function LegalDocuments() {
  const t = useT();
  const links = [["/terms?lang=en", "Terms of Service"], ["/privacy?lang=en", "Privacy Policy"], ["/terms?lang=cs", "Obchodní podmínky"], ["/privacy?lang=cs", "Zásady ochrany osobních údajů"]];
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-3">
      <div>
        <h3 className="text-lg font-semibold">{t("Legal documents")}</h3>
        <p className="text-sm text-muted mt-0.5">{t("The terms and privacy policy that apply to your Portfyl account.")}</p>
      </div>
      <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        {links.map(([href, label]) => (
          <li key={href}>
            <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-brand hover:underline">
              {label}<ExternalLink size={14} aria-hidden="true" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Settings({ dataManagement = <PortfolioDataManagement /> }) {
  const t = useT();
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
        <h1 className="text-2xl font-bold">{t("Settings")}</h1>
        <p className="mt-1 text-sm text-muted">{t("Manage connections, device preferences, notifications, and your data.")}</p>
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
