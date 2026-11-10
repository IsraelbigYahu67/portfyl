import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellRing, Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import {
  checkAlerts,
  createAlert,
  createWatchlist,
  deleteAlert,
  fetchAlerts,
  fetchCapabilities,
  fetchDiscordWebhook,
  fetchWatchlists,
  updateAlert,
} from "../api";
import { WatchlistCard } from "../components/watchlists/WatchlistCard";
import { WatchlistEmptyState } from "../components/watchlists/WatchlistEmptyState";
import { AsyncSection, Badge, SectionHeader } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { getApiErrorMessage } from "../lib/apiError";
import { useT } from "../i18n/I18nProvider";

function NewWatchlistForm() {
  const t = useT();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => createWatchlist({ name: name.trim() }),
    onSuccess: (watchlist) => { toast.success(t("{name} created", { name: watchlist.name })); setName(""); },
    onError: (error) => toast.error(getApiErrorMessage(error, t("Could not create watchlist"), t)),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  });
  return (
    <form className="flex flex-wrap items-center gap-2" onSubmit={(event) => { event.preventDefault(); if (name.trim()) create.mutate(); }}>
      <label className="sr-only" htmlFor="new-watchlist-name">{t("New watchlist name")}</label>
      <input id="new-watchlist-name" value={name} onChange={(event) => setName(event.target.value)} placeholder={t("New watchlist name")} className="input !w-auto min-h-[44px] text-sm md:min-h-0" />
      <button type="submit" disabled={!name.trim() || create.isPending} className="btn-primary inline-flex min-h-[44px] items-center gap-1.5 text-sm disabled:opacity-40 md:min-h-0"><Plus size={14} />{t("Create")}</button>
    </form>
  );
}

function PriceAlertsPanel({ alerts, isLoading, disabledReason, prefillTicker, onConsumePrefill }) {
  const t = useT();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ ticker: "", direction: "above", target_price: "" });
  useEffect(() => {
    if (!prefillTicker) return;
    setForm((current) => ({ ...current, ticker: prefillTicker }));
    onConsumePrefill?.();
  }, [onConsumePrefill, prefillTicker]);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["alerts"] });
  const mutationOptions = (successMessage, failureMessage) => ({
    onSuccess: () => { toast.success(successMessage); invalidate(); },
    onError: (error) => toast.error(getApiErrorMessage(error, failureMessage, t)),
  });
  const add = useMutation({
    mutationFn: createAlert,
    ...mutationOptions(t("Price alert created"), t("Could not create price alert")),
    onSuccess: () => { toast.success(t("Price alert created")); setForm((current) => ({ ...current, target_price: "" })); invalidate(); },
  });
  const reset = useMutation({ mutationFn: (id) => updateAlert(id, { status: "active" }), ...mutationOptions(t("Price alert re-armed"), t("Could not re-arm alert")) });
  const toggle = useMutation({ mutationFn: ({ id, enabled }) => updateAlert(id, { enabled }), ...mutationOptions(t("Price alert updated"), t("Could not update alert")) });
  const remove = useMutation({ mutationFn: deleteAlert, ...mutationOptions(t("Price alert deleted"), t("Could not delete alert")) });
  const check = useMutation({ mutationFn: checkAlerts, ...mutationOptions(t("Price alerts checked"), t("Could not check alerts")) });
  const submit = (event) => {
    event.preventDefault();
    const ticker = form.ticker.trim().toUpperCase();
    const price = Number(form.target_price);
    if (!ticker || !price || disabledReason) return;
    add.mutate({ ticker, direction: form.direction, target_price: price });
  };
  return (
    <section aria-label={t("Price Alerts")} className="card mt-6 !p-0">
      <header className="border-b border-surface-border px-4 pt-4">
        <SectionHeader
          icon={Bell}
          className="!mb-3"
          action={(
            <>
              <span className="text-xs text-muted">{t("Discord notification when a price is crossed")}</span>
              <button type="button" onClick={() => check.mutate()} disabled={check.isPending || alerts.length === 0 || Boolean(disabledReason)} className="btn-ghost inline-flex min-h-[44px] items-center gap-1.5 !px-3 !py-1.5 text-xs disabled:opacity-40 md:min-h-0"><RefreshCw size={13} />{t("Check now")}</button>
            </>
          )}
        >
          {t("Price Alerts")}
        </SectionHeader>
      </header>
      {disabledReason && <p className="border-b border-surface-border px-4 py-2 text-sm text-muted" role="status">{t("Alerts are unavailable: {reason}.", { reason: disabledReason })} <Link className="text-brand hover:underline" to="/settings?section=notifications">{t("Configure notifications")}</Link></p>}
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2 border-b border-surface-border px-4 py-3">
        <label className="sr-only" htmlFor="alert-ticker">{t("Alert ticker")}</label><input id="alert-ticker" value={form.ticker} onChange={(event) => setForm({ ...form, ticker: event.target.value.toUpperCase() })} placeholder={t("Ticker")} className="input !w-28 min-h-[44px] font-mono text-sm md:min-h-0" />
        <label className="sr-only" htmlFor="alert-direction">{t("Alert direction")}</label><select id="alert-direction" value={form.direction} onChange={(event) => setForm({ ...form, direction: event.target.value })} className="input !w-auto min-h-[44px] text-sm md:min-h-0"><option value="above">{t("rises to / above")}</option><option value="below">{t("falls to / below")}</option></select>
        <label className="sr-only" htmlFor="alert-price">{t("Target price")}</label><input id="alert-price" type="number" step="0.01" value={form.target_price} onChange={(event) => setForm({ ...form, target_price: event.target.value })} placeholder={t("Target price")} className="input !w-32 min-h-[44px] text-sm md:min-h-0" />
        <button type="submit" disabled={add.isPending || !form.ticker.trim() || !form.target_price || Boolean(disabledReason)} className="btn-primary inline-flex min-h-[44px] items-center gap-1.5 text-sm disabled:opacity-40 md:min-h-0"><Plus size={14} />{t("Add alert")}</button>
      </form>
      {isLoading ? <p className="px-4 py-6 text-center text-sm text-muted">{t("Loading alerts…")}</p> : alerts.length === 0 ? <p className="px-4 py-6 text-center text-sm text-muted">{t("No alerts yet.")}</p> : (
        <ul className="divide-y divide-surface-border">
          {alerts.map((alert) => {
            const triggered = alert.status === "triggered";
            return <li key={alert.id} className="flex items-center gap-3 px-4 py-3"><span className="w-20 font-mono font-bold">{alert.ticker}</span><span className="flex-1 text-sm text-muted">{alert.direction === "above" ? "≥" : "≤"} {alert.target_price}</span><Badge tone={triggered ? "warn" : "gain"}>{triggered ? t("Triggered") : t("Active")}</Badge>{triggered ? <button type="button" className="grid min-h-[44px] min-w-[44px] place-items-center md:min-h-0 md:min-w-0" onClick={() => reset.mutate(alert.id)} aria-label={t("Re-arm {ticker}", { ticker: alert.ticker })}><RotateCcw size={14} /></button> : <label className="inline-flex min-h-[44px] items-center gap-1 text-xs text-muted md:min-h-0"><input type="checkbox" checked={alert.enabled} onChange={(event) => toggle.mutate({ id: alert.id, enabled: event.target.checked })} /> {t("Armed")}</label>}<button type="button" className="grid min-h-[44px] min-w-[44px] place-items-center md:min-h-0 md:min-w-0" onClick={() => remove.mutate(alert.id)} aria-label={t("Delete alert for {ticker}", { ticker: alert.ticker })}><Trash2 size={14} /></button>{triggered && <BellRing size={13} className="text-[color:var(--chart-3)]" />}</li>;
          })}
        </ul>
      )}
    </section>
  );
}

export default function Watchlists() {
  const t = useT();
  const [prefillTicker, setPrefillTicker] = useState("");
  const watchlists = useQuery({ queryKey: ["watchlists"], queryFn: fetchWatchlists, staleTime: 30_000 });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: fetchAlerts, staleTime: 15_000 });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: fetchCapabilities, staleTime: 5 * 60_000, retry: false });
  const webhook = useQuery({ queryKey: ["discord-webhook"], queryFn: fetchDiscordWebhook, staleTime: 30_000, retry: false });
  const capabilitySet = new Set(capabilities.data?.capabilities || []);
  let alertDisabledReason = "";
  if (capabilities.isError || (capabilities.data && !capabilitySet.has("notification_integrations"))) alertDisabledReason = t("notification integrations are not available");
  else if (!capabilities.data) alertDisabledReason = t("notification capabilities are still loading");
  else if (webhook.isError) alertDisabledReason = t("Discord connection status could not be loaded");
  else if (!webhook.data) alertDisabledReason = t("Discord connection status is still loading");
  else if (webhook.data.connected !== true) alertDisabledReason = t("Discord is not connected");
  const alertsByTicker = useMemo(() => new Map((alerts.data || []).map((alert) => [alert.ticker, alert])), [alerts.data]);
  const lists = watchlists.data || [];
  return (
    <div className="mx-auto max-w-6xl py-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-bold">{t("Watchlists")}</h1><p className="mt-0.5 text-sm text-muted">{t("Track researched stocks without adding them to a portfolio.")}</p></div><NewWatchlistForm /></div>
      <AsyncSection isLoading={watchlists.isLoading} error={watchlists.error} onRetry={() => watchlists.refetch()} loading={<div className="py-16 text-center text-sm text-muted">{t("Loading watchlists…")}</div>} isEmpty={lists.length === 0} empty={<WatchlistEmptyState />}>
        <div className="space-y-6">{lists.map((list) => <WatchlistCard key={list.id} wl={list} onAlert={setPrefillTicker} alertsByTicker={alertsByTicker} alertDisabledReason={alertDisabledReason} />)}</div>
      </AsyncSection>
      <PriceAlertsPanel alerts={alerts.data || []} isLoading={alerts.isLoading} disabledReason={alertDisabledReason} prefillTicker={prefillTicker} onConsumePrefill={() => setPrefillTicker("")} />
    </div>
  );
}
