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
import { AsyncSection } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { getApiErrorMessage } from "../lib/apiError";

function NewWatchlistForm() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => createWatchlist({ name: name.trim() }),
    onSuccess: (watchlist) => { toast.success(`${watchlist.name} created`); setName(""); },
    onError: (error) => toast.error(getApiErrorMessage(error, "Could not create watchlist")),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  });
  return (
    <form className="flex items-center gap-2" onSubmit={(event) => { event.preventDefault(); if (name.trim()) create.mutate(); }}>
      <label className="sr-only" htmlFor="new-watchlist-name">New watchlist name</label>
      <input id="new-watchlist-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="New watchlist name" className="rounded-md border border-surface-border bg-surface-card px-3 py-1.5 text-sm" />
      <button type="submit" disabled={!name.trim() || create.isPending} className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-black disabled:opacity-40"><Plus size={14} />Create</button>
    </form>
  );
}

function PriceAlertsPanel({ alerts, isLoading, disabledReason, prefillTicker, onConsumePrefill }) {
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
    onError: (error) => toast.error(getApiErrorMessage(error, failureMessage)),
  });
  const add = useMutation({
    mutationFn: createAlert,
    ...mutationOptions("Price alert created", "Could not create price alert"),
    onSuccess: () => { toast.success("Price alert created"); setForm((current) => ({ ...current, target_price: "" })); invalidate(); },
  });
  const reset = useMutation({ mutationFn: (id) => updateAlert(id, { status: "active" }), ...mutationOptions("Price alert re-armed", "Could not re-arm alert") });
  const toggle = useMutation({ mutationFn: ({ id, enabled }) => updateAlert(id, { enabled }), ...mutationOptions("Price alert updated", "Could not update alert") });
  const remove = useMutation({ mutationFn: deleteAlert, ...mutationOptions("Price alert deleted", "Could not delete alert") });
  const check = useMutation({ mutationFn: checkAlerts, ...mutationOptions("Price alerts checked", "Could not check alerts") });
  const submit = (event) => {
    event.preventDefault();
    const ticker = form.ticker.trim().toUpperCase();
    const price = Number(form.target_price);
    if (!ticker || !price || disabledReason) return;
    add.mutate({ ticker, direction: form.direction, target_price: price });
  };
  return (
    <section className="mb-6 rounded-xl border border-surface-border bg-surface-card">
      <header className="flex flex-wrap items-center gap-3 border-b border-surface-border px-4 py-3">
        <Bell size={16} className="text-brand" /><h2 className="text-lg font-bold">Price Alerts</h2><span className="mr-auto text-xs text-muted">Discord notification when a price is crossed</span>
        <button type="button" onClick={() => check.mutate()} disabled={check.isPending || alerts.length === 0 || Boolean(disabledReason)} className="inline-flex items-center gap-1.5 text-xs text-muted disabled:opacity-40"><RefreshCw size={13} />Check now</button>
      </header>
      {disabledReason && <p className="border-b border-surface-border px-4 py-2 text-sm text-muted" role="status">Alerts are unavailable: {disabledReason}. <Link className="text-brand hover:underline" to="/settings?section=notifications">Configure notifications</Link></p>}
      <form onSubmit={submit} className="flex flex-wrap items-center gap-2 border-b border-surface-border px-4 py-3">
        <label className="sr-only" htmlFor="alert-ticker">Alert ticker</label><input id="alert-ticker" value={form.ticker} onChange={(event) => setForm({ ...form, ticker: event.target.value.toUpperCase() })} placeholder="Ticker" className="w-28 rounded-md border border-surface-border bg-surface px-2 py-1.5 text-sm font-mono" />
        <label className="sr-only" htmlFor="alert-direction">Alert direction</label><select id="alert-direction" value={form.direction} onChange={(event) => setForm({ ...form, direction: event.target.value })} className="rounded-md border border-surface-border bg-surface px-2 py-1.5 text-sm"><option value="above">rises to / above</option><option value="below">falls to / below</option></select>
        <label className="sr-only" htmlFor="alert-price">Target price</label><input id="alert-price" type="number" step="0.01" value={form.target_price} onChange={(event) => setForm({ ...form, target_price: event.target.value })} placeholder="Target price" className="w-32 rounded-md border border-surface-border bg-surface px-2 py-1.5 text-sm" />
        <button type="submit" disabled={add.isPending || !form.ticker.trim() || !form.target_price || Boolean(disabledReason)} className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-black disabled:opacity-40"><Plus size={14} />Add alert</button>
      </form>
      {isLoading ? <p className="px-4 py-6 text-center text-sm text-muted">Loading alerts…</p> : alerts.length === 0 ? <p className="px-4 py-6 text-center text-sm text-muted">No alerts yet.</p> : (
        <ul className="divide-y divide-surface-border">
          {alerts.map((alert) => {
            const triggered = alert.status === "triggered";
            return <li key={alert.id} className="flex items-center gap-3 px-4 py-3"><span className="w-20 font-mono font-bold">{alert.ticker}</span><span className="flex-1 text-sm text-muted">{alert.direction === "above" ? "≥" : "≤"} {alert.target_price}</span><span className="text-xs font-medium">{triggered ? "Triggered" : "Active"}</span>{triggered ? <button type="button" onClick={() => reset.mutate(alert.id)} aria-label={`Re-arm ${alert.ticker}`}><RotateCcw size={14} /></button> : <label className="text-xs text-muted"><input type="checkbox" checked={alert.enabled} onChange={(event) => toggle.mutate({ id: alert.id, enabled: event.target.checked })} /> Armed</label>}<button type="button" onClick={() => remove.mutate(alert.id)} aria-label={`Delete alert for ${alert.ticker}`}><Trash2 size={14} /></button>{triggered && <BellRing size={13} className="text-amber-500" />}</li>;
          })}
        </ul>
      )}
    </section>
  );
}

export default function Watchlists() {
  const [prefillTicker, setPrefillTicker] = useState("");
  const watchlists = useQuery({ queryKey: ["watchlists"], queryFn: fetchWatchlists, staleTime: 30_000 });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: fetchAlerts, staleTime: 15_000 });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: fetchCapabilities, staleTime: 5 * 60_000, retry: false });
  const webhook = useQuery({ queryKey: ["discord-webhook"], queryFn: fetchDiscordWebhook, staleTime: 30_000, retry: false });
  const capabilitySet = new Set(capabilities.data?.capabilities || []);
  let alertDisabledReason = "";
  if (capabilities.isError || (capabilities.data && !capabilitySet.has("notification_integrations"))) alertDisabledReason = "notification integrations are not available";
  else if (!capabilities.data) alertDisabledReason = "notification capabilities are still loading";
  else if (webhook.isError) alertDisabledReason = "Discord connection status could not be loaded";
  else if (!webhook.data) alertDisabledReason = "Discord connection status is still loading";
  else if (webhook.data.connected !== true) alertDisabledReason = "Discord is not connected";
  const alertsByTicker = useMemo(() => new Map((alerts.data || []).map((alert) => [alert.ticker, alert])), [alerts.data]);
  const lists = watchlists.data || [];
  return (
    <div className="mx-auto max-w-6xl py-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-bold">Watchlists</h1><p className="mt-0.5 text-sm text-muted">Track researched stocks without adding them to a portfolio.</p></div><NewWatchlistForm /></div>
      <PriceAlertsPanel alerts={alerts.data || []} isLoading={alerts.isLoading} disabledReason={alertDisabledReason} prefillTicker={prefillTicker} onConsumePrefill={() => setPrefillTicker("")} />
      <AsyncSection isLoading={watchlists.isLoading} error={watchlists.error} onRetry={() => watchlists.refetch()} loading={<div className="py-16 text-center text-sm text-muted">Loading watchlists…</div>} isEmpty={lists.length === 0} empty={<WatchlistEmptyState />}>
        <div className="space-y-6">{lists.map((list) => <WatchlistCard key={list.id} wl={list} onAlert={setPrefillTicker} alertsByTicker={alertsByTicker} alertDisabledReason={alertDisabledReason} />)}</div>
      </AsyncSection>
    </div>
  );
}
