import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchT212Status, connectT212, disconnectT212, syncT212, setT212AutoSync } from "../api";
import { Loader2, Link, Unlink, RefreshCw, CheckCircle2, AlertCircle, Eye, EyeOff, Briefcase } from "lucide-react";
import { usePortfolio } from "../App";
import DiscordSettings from "../components/DiscordSettings";
import SyncScheduleSettings from "../components/SyncScheduleSettings";
import Toggle from "../components/ui/Toggle";

export default function Settings() {
  const queryClient = useQueryClient();
  const { current: currentPortfolio } = usePortfolio();
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const { data: status, isLoading } = useQuery({
    queryKey: ["t212-status", currentPortfolio?.id],
    queryFn: fetchT212Status,
    enabled: currentPortfolio?.id != null,
  });

  const connectMutation = useMutation({
    mutationFn: () => connectT212(apiKey, apiSecret),
    onSuccess: () => {
      setApiKey("");
      setApiSecret("");
      setError(null);
      setSuccess("Connected to Trading 212 successfully");
      queryClient.invalidateQueries({ queryKey: ["t212-status"] });
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["holdings"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (err) => {
      setSuccess(null);
      setError(err.response?.data?.detail || "Failed to connect");
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: disconnectT212,
    onSuccess: () => {
      setError(null);
      setSuccess("Disconnected from Trading 212");
      queryClient.invalidateQueries({ queryKey: ["t212-status"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (err) => {
      setSuccess(null);
      setError(err.response?.data?.detail || "Failed to disconnect");
    },
  });

  const syncMutation = useMutation({
    mutationFn: syncT212,
    onSuccess: (data) => {
      setError(null);
      setSuccess(
        `Synced ${data.total_imported} transactions (${data.imported_orders} orders, ${data.imported_dividends} dividends)`
      );
      ["t212-status", "transactions", "holdings", "summary", "portfolios",
       "heatmap", "performance", "movers", "earnings", "dividends", "insider-buys"]
        .forEach((k) => queryClient.invalidateQueries({ queryKey: [k] }));
      setTimeout(() => setSuccess(null), 6000);
    },
    onError: (err) => {
      setSuccess(null);
      setError(err.response?.data?.detail || "Sync failed");
    },
  });

  const autoSyncMutation = useMutation({
    mutationFn: setT212AutoSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["t212-status"] }),
    onError: (err) => setError(err.response?.data?.detail || "Failed to update auto-sync"),
  });

  const connected = status?.connected;
  const busy = connectMutation.isPending || disconnectMutation.isPending || syncMutation.isPending;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {currentPortfolio && (
        <div className="flex items-center gap-2 text-sm text-muted bg-surface-card border border-surface-border rounded-lg px-4 py-2.5">
          <Briefcase size={14} className="text-brand" />
          <span>Managing connection for portfolio</span>
          <span className="text-ink font-medium">{currentPortfolio.name}</span>
          <span className="text-xs text-muted ml-auto">
            Each portfolio holds its own Trading 212 API key — data is never mixed.
          </span>
        </div>
      )}

      <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Trading 212</h2>
            <p className="text-sm text-muted mt-0.5">
              Connect your Trading 212 account to automatically import transactions into{" "}
              <span className="text-ink">{currentPortfolio?.name ?? "this portfolio"}</span>
            </p>
          </div>
          <span
            className={`text-xs font-medium px-2.5 py-1 rounded-full ${
              connected
                ? "bg-gain/10 text-gain"
                : "bg-surface-hover text-muted"
            }`}
          >
            {isLoading ? "..." : connected ? "Connected" : "Not connected"}
          </span>
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

        {!connected && !isLoading && (
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-muted mb-1.5">API Key</label>
              <div className="relative">
                <input
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Paste your Trading 212 API key"
                  className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-sm text-ink placeholder-muted focus:outline-none focus:border-brand pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                >
                  {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <p className="text-xs text-muted mt-1.5">
                Generate an API key in Trading 212 &rarr; Settings &rarr; API (beta)
              </p>
            </div>
            <div>
              <label className="block text-sm text-muted mb-1.5">API Secret</label>
              <input
                type="password"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
                placeholder="Paste your Trading 212 API secret"
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-sm text-ink placeholder-muted focus:outline-none focus:border-brand"
              />
            </div>
            <button
              onClick={() => connectMutation.mutate()}
              disabled={!apiKey.trim() || !apiSecret.trim() || busy}
              className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:bg-brand-light disabled:text-muted disabled:cursor-not-allowed"
            >
              {connectMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Link size={16} />
              )}
              Connect
            </button>
          </div>
        )}

        {connected && !isLoading && (
          <div className="space-y-4">
            {status.needs_attention && (
              <div className="flex items-start gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3">
                <AlertCircle size={16} className="shrink-0 mt-0.5" />
                <div>
                  <div className="font-medium">Auto-sync paused after repeated failures</div>
                  {status.last_error && (
                    <div className="text-loss/80 text-xs mt-0.5">{status.last_error}</div>
                  )}
                  <div className="text-loss/80 text-xs mt-0.5">
                    Turn auto-sync back on below to retry.
                  </div>
                </div>
              </div>
            )}
            <div className="bg-surface-hover rounded-lg p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">API Key</span>
                <span className="text-ink font-mono">{status.api_key_preview}</span>
              </div>
              {status.last_synced_at && (
                <div className="flex justify-between">
                  <span className="text-muted">Last synced</span>
                  <span className="text-ink">
                    {new Date(status.last_synced_at).toLocaleString()}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted">Connected since</span>
                <span className="text-ink">
                  {status.connected_at
                    ? new Date(status.connected_at).toLocaleDateString()
                    : "—"}
                </span>
              </div>
              <div className="flex justify-between items-center pt-1">
                <span className="text-muted">
                  Auto-sync
                  <span className="text-xs text-muted ml-2">checks for new trades on the auto-sync schedule below</span>
                </span>
                <Toggle
                  checked={status.auto_sync}
                  onChange={(v) => autoSyncMutation.mutate(v)}
                  disabled={autoSyncMutation.isPending}
                  aria-label="T212 auto-sync"
                />
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => syncMutation.mutate()}
                disabled={busy}
                className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:bg-brand-light disabled:text-muted disabled:cursor-not-allowed"
              >
                {syncMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <RefreshCw size={16} />
                )}
                Sync now
              </button>
              <button
                onClick={() => disconnectMutation.mutate()}
                disabled={busy}
                className="flex items-center gap-2 bg-transparent border border-red-200 text-red-600 font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {disconnectMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Unlink size={16} />
                )}
                Disconnect
              </button>
            </div>
          </div>
        )}
      </div>

      <SyncScheduleSettings />

      <DiscordSettings />
    </div>
  );
}
