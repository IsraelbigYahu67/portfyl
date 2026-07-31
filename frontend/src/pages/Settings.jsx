import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchT212Status, connectT212, disconnectT212, syncT212, setT212AutoSync, fetchIBKRStatus, connectIBKR, disconnectIBKR, syncIBKR, setIBKRAutoSync, fetchPolymarketStatus, connectPolymarket, disconnectPolymarket, syncPolymarket } from "../api";
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

  // IBKR state
  const [ibkrToken, setIbkrToken] = useState("");
  const [ibkrQueryId, setIbkrQueryId] = useState("");
  const [showIbkrToken, setShowIbkrToken] = useState(false);
  const [ibkrError, setIbkrError] = useState(null);
  const [ibkrSuccess, setIbkrSuccess] = useState(null);

  // Polymarket state
  const [polyAddress, setPolyAddress] = useState("");
  const [polyError, setPolyError] = useState(null);
  const [polySuccess, setPolySuccess] = useState(null);

  const { data: status, isLoading } = useQuery({
    queryKey: ["t212-status", currentPortfolio?.id],
    queryFn: fetchT212Status,
    enabled: currentPortfolio?.id != null,
  });

  // IBKR query & mutations
  const { data: ibkrStatus, isLoading: ibkrLoading } = useQuery({
    queryKey: ["ibkr-status", currentPortfolio?.id],
    queryFn: fetchIBKRStatus,
    enabled: currentPortfolio?.id != null,
  });

  const ibkrConnectMutation = useMutation({
    mutationFn: () => connectIBKR(ibkrToken, ibkrQueryId),
    onSuccess: () => {
      setIbkrToken("");
      setIbkrQueryId("");
      setIbkrError(null);
      setIbkrSuccess("Connected to Interactive Brokers successfully");
      queryClient.invalidateQueries({ queryKey: ["ibkr-status"] });
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["holdings"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setTimeout(() => setIbkrSuccess(null), 4000);
    },
    onError: (err) => {
      setIbkrSuccess(null);
      setIbkrError(err.response?.data?.detail || "Failed to connect");
    },
  });

  const ibkrDisconnectMutation = useMutation({
    mutationFn: disconnectIBKR,
    onSuccess: () => {
      setIbkrError(null);
      setIbkrSuccess("Disconnected from Interactive Brokers");
      queryClient.invalidateQueries({ queryKey: ["ibkr-status"] });
      setTimeout(() => setIbkrSuccess(null), 4000);
    },
    onError: (err) => {
      setIbkrSuccess(null);
      setIbkrError(err.response?.data?.detail || "Failed to disconnect");
    },
  });

  const ibkrSyncMutation = useMutation({
    mutationFn: syncIBKR,
    onSuccess: (data) => {
      setIbkrError(null);
      setIbkrSuccess(
        `Synced ${data.imported} trades from Interactive Brokers${data.skipped_duplicates ? ` (${data.skipped_duplicates} duplicates skipped)` : ""}` +
          (data.balance_found === false
            ? ". No account balance found — enable the NAV in Base & Cash Report sections in your Flex Query to see it on the Options page."
            : "")
      );
      queryClient.invalidateQueries({ queryKey: ["ibkr-status"] });
      queryClient.invalidateQueries({ queryKey: ["ibkr-balance"] });
      queryClient.invalidateQueries({ queryKey: ["options-trades"] });
      queryClient.invalidateQueries({ queryKey: ["options-summary"] });
      queryClient.invalidateQueries({ queryKey: ["options-by-underlying"] });
      queryClient.invalidateQueries({ queryKey: ["options-calendar"] });
      queryClient.invalidateQueries({ queryKey: ["summary"] });
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setTimeout(() => setIbkrSuccess(null), 6000);
    },
    onError: (err) => {
      setIbkrSuccess(null);
      setIbkrError(err.response?.data?.detail || "Sync failed");
    },
  });

  const ibkrConnected = ibkrStatus?.connected;
  const ibkrBusy = ibkrConnectMutation.isPending || ibkrDisconnectMutation.isPending || ibkrSyncMutation.isPending;

  // Polymarket query & mutations
  const { data: polyStatus, isLoading: polyLoading } = useQuery({
    queryKey: ["polymarket-status", currentPortfolio?.id],
    queryFn: fetchPolymarketStatus,
    enabled: currentPortfolio?.id != null,
  });

  const polyConnectMutation = useMutation({
    mutationFn: () => connectPolymarket(polyAddress),
    onSuccess: () => {
      setPolyAddress("");
      setPolyError(null);
      setPolySuccess("Connected to Polymarket successfully");
      queryClient.invalidateQueries({ queryKey: ["polymarket-status"] });
      queryClient.invalidateQueries({ queryKey: ["polymarket-positions"] });
      queryClient.invalidateQueries({ queryKey: ["polymarket-summary"] });
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setTimeout(() => setPolySuccess(null), 4000);
    },
    onError: (err) => {
      setPolySuccess(null);
      setPolyError(err.response?.data?.detail || "Failed to connect");
    },
  });

  const polyDisconnectMutation = useMutation({
    mutationFn: disconnectPolymarket,
    onSuccess: () => {
      setPolyError(null);
      setPolySuccess("Disconnected from Polymarket");
      queryClient.invalidateQueries({ queryKey: ["polymarket-status"] });
      setTimeout(() => setPolySuccess(null), 4000);
    },
    onError: (err) => {
      setPolySuccess(null);
      setPolyError(err.response?.data?.detail || "Failed to disconnect");
    },
  });

  const polySyncMutation = useMutation({
    mutationFn: syncPolymarket,
    onSuccess: (data) => {
      setPolyError(null);
      setPolySuccess(`Synced ${data.imported} positions (${data.updated} updated)`);
      queryClient.invalidateQueries({ queryKey: ["polymarket-status"] });
      queryClient.invalidateQueries({ queryKey: ["polymarket-positions"] });
      queryClient.invalidateQueries({ queryKey: ["polymarket-summary"] });
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      setTimeout(() => setPolySuccess(null), 6000);
    },
    onError: (err) => {
      setPolySuccess(null);
      setPolyError(err.response?.data?.detail || "Sync failed");
    },
  });

  const polyConnected = polyStatus?.connected;
  const polyBusy = polyConnectMutation.isPending || polyDisconnectMutation.isPending || polySyncMutation.isPending;

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

  const ibkrAutoSyncMutation = useMutation({
    mutationFn: setIBKRAutoSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ibkr-status"] }),
    onError: (err) => setIbkrError(err.response?.data?.detail || "Failed to update auto-sync"),
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

      {/* IBKR Card */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Interactive Brokers</h2>
            <p className="text-sm text-muted mt-0.5">
              Connect your IBKR Flex Web Service to import options trades into{" "}
              <span className="text-ink">{currentPortfolio?.name ?? "this portfolio"}</span>
            </p>
          </div>
          <span
            className={`text-xs font-medium px-2.5 py-1 rounded-full ${
              ibkrConnected
                ? "bg-gain/10 text-gain"
                : "bg-surface-hover text-muted"
            }`}
          >
            {ibkrLoading ? "..." : ibkrConnected ? "Connected" : "Not connected"}
          </span>
        </div>

        {ibkrError && (
          <div className="flex items-center gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3">
            <AlertCircle size={16} className="shrink-0" />
            {ibkrError}
          </div>
        )}

        {ibkrSuccess && (
          <div className="flex items-center gap-2 text-sm text-gain bg-gain/10 border border-gain/30 rounded-lg px-4 py-3">
            <CheckCircle2 size={16} className="shrink-0" />
            {ibkrSuccess}
          </div>
        )}

        {!ibkrConnected && !ibkrLoading && (
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-muted mb-1.5">Flex Token</label>
              <div className="relative">
                <input
                  type={showIbkrToken ? "text" : "password"}
                  value={ibkrToken}
                  onChange={(e) => setIbkrToken(e.target.value)}
                  placeholder="Paste your IBKR Flex Web Service token"
                  className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-sm text-ink placeholder-muted focus:outline-none focus:border-brand pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowIbkrToken(!showIbkrToken)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                >
                  {showIbkrToken ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <p className="text-xs text-muted mt-1.5">
                Generate a token in IBKR Account Management &rarr; Reports &rarr; Flex Queries &rarr; Manage Flex Web Service
              </p>
            </div>
            <div>
              <label className="block text-sm text-muted mb-1.5">Flex Query ID</label>
              <input
                type="text"
                value={ibkrQueryId}
                onChange={(e) => setIbkrQueryId(e.target.value)}
                placeholder="Enter your Flex Query ID"
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-sm text-ink placeholder-muted focus:outline-none focus:border-brand"
              />
            </div>
            <button
              onClick={() => ibkrConnectMutation.mutate()}
              disabled={!ibkrToken.trim() || !ibkrQueryId.trim() || ibkrBusy}
              className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:bg-brand-light disabled:text-muted disabled:cursor-not-allowed"
            >
              {ibkrConnectMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Link size={16} />
              )}
              Connect
            </button>
          </div>
        )}

        {ibkrConnected && !ibkrLoading && (
          <div className="space-y-4">
            <div className="bg-surface-hover rounded-lg p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">Flex Token</span>
                <span className="text-ink font-mono">{ibkrStatus.token_preview}</span>
              </div>
              {ibkrStatus.last_synced_at && (
                <div className="flex justify-between">
                  <span className="text-muted">Last synced</span>
                  <span className="text-ink">
                    {new Date(ibkrStatus.last_synced_at).toLocaleString()}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted">Connected since</span>
                <span className="text-ink">
                  {ibkrStatus.connected_at
                    ? new Date(ibkrStatus.connected_at).toLocaleDateString()
                    : "—"}
                </span>
              </div>
              <div className="flex justify-between items-center pt-1">
                <span className="text-muted">
                  Auto-sync
                  <span className="text-xs text-muted ml-2">checks for new trades on the auto-sync schedule below</span>
                </span>
                <Toggle
                  checked={ibkrStatus.auto_sync}
                  onChange={(v) => ibkrAutoSyncMutation.mutate(v)}
                  disabled={ibkrAutoSyncMutation.isPending}
                  aria-label="IBKR auto-sync"
                />
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => ibkrSyncMutation.mutate()}
                disabled={ibkrBusy}
                className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:bg-brand-light disabled:text-muted disabled:cursor-not-allowed"
              >
                {ibkrSyncMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <RefreshCw size={16} />
                )}
                Sync now
              </button>
              <button
                onClick={() => ibkrDisconnectMutation.mutate()}
                disabled={ibkrBusy}
                className="flex items-center gap-2 bg-transparent border border-red-200 text-red-600 font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {ibkrDisconnectMutation.isPending ? (
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

      {/* Polymarket Card */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Polymarket</h2>
            <p className="text-sm text-muted mt-0.5">
              Connect your Polymarket wallet to import prediction market positions into{" "}
              <span className="text-ink">{currentPortfolio?.name ?? "this portfolio"}</span>
            </p>
          </div>
          <span
            className={`text-xs font-medium px-2.5 py-1 rounded-full ${
              polyConnected
                ? "bg-gain/10 text-gain"
                : "bg-surface-hover text-muted"
            }`}
          >
            {polyLoading ? "..." : polyConnected ? "Connected" : "Not connected"}
          </span>
        </div>

        {polyError && (
          <div className="flex items-center gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3">
            <AlertCircle size={16} className="shrink-0" />
            {polyError}
          </div>
        )}

        {polySuccess && (
          <div className="flex items-center gap-2 text-sm text-gain bg-gain/10 border border-gain/30 rounded-lg px-4 py-3">
            <CheckCircle2 size={16} className="shrink-0" />
            {polySuccess}
          </div>
        )}

        {!polyConnected && !polyLoading && (
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-muted mb-1.5">Wallet Address</label>
              <input
                type="text"
                value={polyAddress}
                onChange={(e) => setPolyAddress(e.target.value)}
                placeholder="Your Polymarket wallet address (0x...)"
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-sm text-ink placeholder-muted focus:outline-none focus:border-brand font-mono"
              />
              <p className="text-xs text-muted mt-1.5">
                Find your wallet address in your Polymarket profile. Position data is public — no API key needed.
              </p>
            </div>
            <button
              onClick={() => polyConnectMutation.mutate()}
              disabled={!polyAddress.trim() || polyBusy}
              className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:bg-brand-light disabled:text-muted disabled:cursor-not-allowed"
            >
              {polyConnectMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Link size={16} />
              )}
              Connect
            </button>
          </div>
        )}

        {polyConnected && !polyLoading && (
          <div className="space-y-4">
            <div className="bg-surface-hover rounded-lg p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted">Wallet</span>
                <span className="text-ink font-mono">{polyStatus.address_preview}</span>
              </div>
              {polyStatus.last_synced_at && (
                <div className="flex justify-between">
                  <span className="text-muted">Last synced</span>
                  <span className="text-ink">
                    {new Date(polyStatus.last_synced_at).toLocaleString()}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted">Connected since</span>
                <span className="text-ink">
                  {polyStatus.connected_at
                    ? new Date(polyStatus.connected_at).toLocaleDateString()
                    : "—"}
                </span>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => polySyncMutation.mutate()}
                disabled={polyBusy}
                className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:bg-brand-light disabled:text-muted disabled:cursor-not-allowed"
              >
                {polySyncMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <RefreshCw size={16} />
                )}
                Sync now
              </button>
              <button
                onClick={() => polyDisconnectMutation.mutate()}
                disabled={polyBusy}
                className="flex items-center gap-2 bg-transparent border border-red-200 text-red-600 font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {polyDisconnectMutation.isPending ? (
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
    </div>
  );
}
