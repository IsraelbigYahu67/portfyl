import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchDiscordWebhook, createDiscordWebhook, updateDiscordWebhook, deleteDiscordWebhook, testDiscordWebhook } from "../api";
import { Loader2, Unlink, CheckCircle2, AlertCircle, Send, Bell, BellOff } from "lucide-react";
import { Badge } from "./ui/Badge";
import Toggle from "./ui/Toggle";
import { useT } from "../i18n/I18nProvider";

export default function DiscordSettings() {
  const t = useT();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const { data: webhook, isLoading } = useQuery({
    queryKey: ["discord-webhook"],
    queryFn: fetchDiscordWebhook,
  });

  const connectMut = useMutation({
    mutationFn: () => createDiscordWebhook({ webhook_url: url }),
    onSuccess: () => {
      setUrl("");
      setError(null);
      setSuccess(t("Discord webhook connected"));
      queryClient.invalidateQueries({ queryKey: ["discord-webhook"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (err) => {
      setSuccess(null);
      setError(err.response?.data?.detail || t("Failed to connect"));
    },
  });

  const disconnectMut = useMutation({
    mutationFn: deleteDiscordWebhook,
    onSuccess: () => {
      setError(null);
      setSuccess(t("Webhook removed"));
      queryClient.invalidateQueries({ queryKey: ["discord-webhook"] });
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (err) => {
      setSuccess(null);
      setError(err.response?.data?.detail || t("Failed to disconnect"));
    },
  });

  const testMut = useMutation({
    mutationFn: () => testDiscordWebhook(t("Test notification from Portfyl")),
    onSuccess: () => {
      setSuccess(t("Test message sent! Check your Discord channel."));
      setTimeout(() => setSuccess(null), 4000);
    },
    onError: (err) => {
      setError(err.response?.data?.detail || t("Failed to send test"));
    },
  });

  const toggleMut = useMutation({
    mutationFn: (data) => updateDiscordWebhook(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["discord-webhook"] }),
    onError: (err) => {
      setSuccess(null);
      setError(err.response?.data?.detail || t("Failed to update settings"));
    },
  });

  const connected = webhook?.connected;
  // Webhooks saved before URLs were validated may not be Discord URLs; the
  // backend never sends to them, so the user has to enter a new one.
  const invalidStored = connected && webhook?.valid === false;
  const busy = connectMut.isPending || disconnectMut.isPending || testMut.isPending;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <svg width="20" height="16" viewBox="0 0 71 55" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M60.1 4.9A58.5 58.5 0 0045.4.2a.2.2 0 00-.2.1 40.8 40.8 0 00-1.8 3.7 54 54 0 00-16.2 0A37.4 37.4 0 0025.4.3a.2.2 0 00-.2-.1 58.4 58.4 0 00-14.7 4.6.2.2 0 00-.1 0C1.5 18.7-.9 32 .3 45.2v.1a58.7 58.7 0 0017.9 9.1.2.2 0 00.3-.1 42 42 0 003.6-5.9.2.2 0 00-.1-.3 38.7 38.7 0 01-5.5-2.7.2.2 0 01 0-.4l1.1-.9a.2.2 0 01.2 0 41.9 41.9 0 0035.6 0 .2.2 0 01.2 0l1.1.9a.2.2 0 010 .3 36.4 36.4 0 01-5.5 2.7.2.2 0 00-.1.3 47.1 47.1 0 003.6 5.9.2.2 0 00.2.1A58.5 58.5 0 0070.7 45.3v-.1c1.4-15-2.3-28-9.8-39.6a.2.2 0 00-.1-.1zM23.7 37c-3.4 0-6.2-3.2-6.2-7s2.7-7 6.2-7 6.3 3.1 6.2 7-2.8 7-6.2 7zm23 0c-3.4 0-6.2-3.2-6.2-7s2.7-7 6.2-7 6.3 3.1 6.2 7-2.8 7-6.2 7z" fill="#5865F2"/>
            </svg>
            {t("Discord Notifications")}
          </h2>
          <p className="text-sm text-muted mt-0.5">
            {t("Get notified in Discord when trades execute, dividends arrive, or you hit milestones")}
          </p>
        </div>
        <Badge tone={invalidStored ? "loss" : connected ? "gain" : "neutral"}>
          {isLoading ? "..." : invalidStored ? t("Needs attention") : connected ? t("Active") : t("Not configured")}
        </Badge>
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

      {invalidStored && !isLoading && (
        <div role="alert" className="flex items-center gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3">
          <AlertCircle size={16} className="shrink-0" />
          {t("The saved webhook is not a valid Discord webhook URL, so no notifications are being sent.")}{" "}
          {t("Enter a new URL below.")}
        </div>
      )}

      {(!connected || invalidStored) && !isLoading && (
        <div className="space-y-3">
          <div>
            <label className="block text-sm text-muted mb-1.5">{t("Webhook URL")}</label>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://discord.com/api/webhooks/..."
              className="input text-sm"
            />
            <p className="text-xs text-muted mt-1.5">
              {t("Create a webhook in Discord:")} Server Settings &rarr; Integrations &rarr; Webhooks &rarr; New Webhook
            </p>
          </div>
          <button
            onClick={() => connectMut.mutate()}
            disabled={!url.trim() || busy}
            className="btn-primary flex items-center gap-2 text-sm min-h-11 md:min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {connectMut.isPending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            {t("Connect")}
          </button>
        </div>
      )}

      {connected && !isLoading && (
        <div className="space-y-4">
          <div className="bg-surface-hover rounded-lg p-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted">{t("Webhook")}</span>
              <span className="text-ink font-mono text-xs">{webhook.webhook_url_preview}</span>
            </div>
            {webhook.created_at && (
              <div className="flex justify-between">
                <span className="text-muted">{t("Connected since")}</span>
                <span className="text-ink">{new Date(webhook.created_at).toLocaleDateString()}</span>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <p className="text-xs text-muted font-medium">{t("Notification preferences")}</p>
            {[
              { key: "notify_trades", label: t("Trade executions"), desc: t("Buy/sell notifications") },
              { key: "notify_dividends", label: t("Dividends"), desc: t("When dividends are received") },
              { key: "notify_milestones", label: t("Milestones"), desc: t("Portfolio value milestones") },
            ].map(({ key, label, desc }) => (
              <label key={key} className="flex items-center justify-between p-3 rounded-lg hover:bg-surface-hover cursor-pointer">
                <div>
                  <span className="text-sm text-ink font-medium">{label}</span>
                  <span className="text-xs text-muted ml-2">{desc}</span>
                </div>
                <Toggle
                  checked={webhook[key]}
                  onChange={(v) => toggleMut.mutate({ [key]: v })}
                  aria-label={label}
                />
              </label>
            ))}
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => testMut.mutate()}
              disabled={busy || invalidStored}
              className="btn-primary flex items-center gap-2 text-sm min-h-11 md:min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {testMut.isPending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              {t("Send test")}
            </button>
            <button
              onClick={() => disconnectMut.mutate()}
              disabled={busy}
              className="btn-ghost text-loss flex items-center gap-2 text-sm font-semibold min-h-11 md:min-h-0 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {disconnectMut.isPending ? <Loader2 size={16} className="animate-spin" /> : <Unlink size={16} />}
              {t("Remove")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
