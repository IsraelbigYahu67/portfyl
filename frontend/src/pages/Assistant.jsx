import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Send,
  Loader2,
  Settings as SettingsIcon,
  Eye,
  EyeOff,
  Trash2,
  AlertCircle,
  Sparkles,
} from "lucide-react";
import {
  fetchAssistantConfig,
  saveAssistantConfig,
  deleteAssistantConfig,
  sendAssistantMessage,
} from "../api";
import { AsyncSection } from "../components/ui";
import { getApiErrorMessage } from "../lib/apiError";
import AssistantContextDialog from "../components/AssistantContextDialog";
import { formatDateTime } from "../lib/format";

const MODELS = [
  { value: "deepseek-chat", label: "DeepSeek Chat (V3) — fast" },
  { value: "deepseek-reasoner", label: "DeepSeek Reasoner (R1) — deeper, slower" },
];

const SUGGESTIONS = [
  "How concentrated is my portfolio?",
  "Summarize my recent transactions",
  "What are my largest positions?",
];

export default function Assistant() {
  const queryClient = useQueryClient();

  const {
    data: config,
    isLoading: configLoading,
    error: configQueryError,
    refetch: refetchConfig,
  } = useQuery({
    queryKey: ["assistant-config"],
    queryFn: fetchAssistantConfig,
    staleTime: 60 * 1000,
  });

  const configured = !!config?.configured;

  // Config form
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [modelInput, setModelInput] = useState("deepseek-chat");
  const [showKey, setShowKey] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [configError, setConfigError] = useState(null);

  // Keep the model selector in sync with the stored model once it loads.
  useEffect(() => {
    if (config?.model) setModelInput(config.model);
  }, [config?.model]);

  // Chat
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [chatError, setChatError] = useState(null);
  const [requestedMode, setRequestedMode] = useState("none");
  const [consentedToPortfolioSummary, setConsentedToPortfolioSummary] = useState(false);
  const [pendingText, setPendingText] = useState(null);
  const scrollRef = useRef(null);

  const chatMutation = useMutation({
    mutationFn: ({ history, mode }) => sendAssistantMessage(history, mode),
    onSuccess: (data) => {
      setMessages((prev) => [...prev, { ...data.reply, metadata: {
        provider: data.provider, model: data.model, context_mode: data.context_mode, context_as_of: data.context_as_of,
      } }]);
    },
    onError: (err) => {
      setChatError(getApiErrorMessage(err, "The assistant request failed. Try again."));
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => saveAssistantConfig(apiKeyInput.trim(), modelInput),
    onSuccess: () => {
      setApiKeyInput("");
      setShowConfig(false);
      setConfigError(null);
      queryClient.invalidateQueries({ queryKey: ["assistant-config"] });
    },
    onError: (err) => setConfigError(getApiErrorMessage(err, "Failed to save settings")),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAssistantConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assistant-config"] });
    },
  });

  // Auto-scroll to newest message.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, chatMutation.isPending]);

  const panelOpen = showConfig || (!configured && !configLoading);

  function send(text) {
    const content = (text ?? input).trim();
    if (!content || chatMutation.isPending || pendingText !== null || !configured) return;
    if (requestedMode === "portfolio_summary" && !consentedToPortfolioSummary) {
      setPendingText(content);
      return;
    }
    submit(content, requestedMode);
  }

  function submit(content, mode) {
    const next = [...messages, { role: "user", content }];
    setMessages(next);
    setInput("");
    setChatError(null);
    chatMutation.mutate({ history: next.map(({ role, content }) => ({ role, content })), mode });
  }

  function resolveConsent(share) {
    if (pendingText === null) return;
    const content = pendingText;
    setPendingText(null);
    const mode = share ? "portfolio_summary" : "none";
    setRequestedMode(mode);
    if (share) setConsentedToPortfolioSummary(true);
    submit(content, mode);
  }

  function newConversation() {
    setMessages([]);
    setInput("");
    setChatError(null);
    setPendingText(null);
    setConsentedToPortfolioSummary(false);
    setRequestedMode("none");
    chatMutation.reset();
  }

  function onInputKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="max-w-3xl mx-auto flex flex-col min-h-[32rem] h-[calc(100dvh-8rem)]">
      <AssistantContextDialog open={pendingText !== null} provider="DeepSeek" model={config?.model || "deepseek-chat"} onWithoutContext={() => resolveConsent(false)} onShare={() => resolveConsent(true)} />
      {/* Header */}
      <div className="flex flex-wrap gap-3 items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Bot size={20} className="text-brand" />
            <h1 className="text-xl font-semibold">AI Assistant</h1>
          </div>
          <p className="text-sm text-muted">
            Powered by DeepSeek · choose whether to share a portfolio summary
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={newConversation} disabled={chatMutation.isPending} className="btn-secondary min-h-11 px-3 text-sm">New conversation</button>
          {configured && (
            <span className="text-xs text-muted font-mono hidden sm:inline">
              {config.model}
            </span>
          )}
          <button
            onClick={() => setShowConfig((s) => !s)}
            className="flex items-center gap-1.5 text-sm text-muted hover:text-brand border border-surface-border rounded-lg px-3 py-1.5 transition-colors"
          >
            <SettingsIcon size={15} />
            Settings
          </button>
        </div>
      </div>

      <AsyncSection
        isLoading={configLoading}
        error={configQueryError}
        onRetry={() => refetchConfig()}
        loading={<div className="card h-48 animate-pulse" />}
      >
      <>
      {/* Config panel */}
      {panelOpen && (
        <div className="card mb-4 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-ink">DeepSeek connection</h2>
            <p className="text-xs text-muted mt-0.5">
              Create a key at{" "}
              <a
                href="https://platform.deepseek.com/api_keys"
                target="_blank"
                rel="noreferrer"
                className="text-brand hover:underline"
              >
                platform.deepseek.com
              </a>
              . It's encrypted on your backend and used for requests to DeepSeek.
            </p>
          </div>

          {configError && (
            <div className="flex items-start gap-2 text-sm text-loss bg-loss/10 rounded-lg px-3 py-2">
              <AlertCircle size={15} className="mt-0.5 shrink-0" />
              <span>{configError}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted">API key</label>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={
                  configured ? `Saved (${config.key_preview}) — enter a new key to replace` : "sk-..."
                }
                className="input pr-10 text-sm"
              />
              <button
                type="button"
                onClick={() => setShowKey((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
              >
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted">Model</label>
            <select
              value={modelInput}
              onChange={(e) => setModelInput(e.target.value)}
              className="input text-sm"
            >
              {MODELS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => saveMutation.mutate()}
              disabled={(!apiKeyInput.trim() && !configured) || saveMutation.isPending}
              className="flex items-center gap-2 bg-brand text-white font-semibold text-sm px-5 py-2.5 rounded-lg hover:bg-brand/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : null}
              {configured ? "Save changes" : "Connect"}
            </button>
            {configured && (
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="flex items-center gap-2 text-red-600 border border-red-200 font-semibold text-sm px-4 py-2.5 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-40"
              >
                {deleteMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Trash2 size={16} />
                )}
                Remove key
              </button>
            )}
          </div>
        </div>
      )}

      {/* Chat area */}
      <div className="flex-1 min-h-0 rounded-xl border border-surface-border bg-surface-card flex flex-col overflow-hidden">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && !chatMutation.isPending && (
            <div className="h-full flex flex-col items-center justify-center text-center px-6">
              <div className="w-12 h-12 rounded-full bg-brand/10 flex items-center justify-center mb-3">
                <Sparkles size={22} className="text-brand" />
              </div>
              <p className="text-sm text-ink font-medium mb-1">
                Ask an investing question
              </p>
              <p className="text-xs text-muted mb-5 max-w-sm">
                Portfolio data is shared only when you choose a summary and consent for this conversation.
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    disabled={!configured}
                    className="text-xs text-muted border border-hairline rounded-full px-3 py-1.5 hover:border-brand hover:text-brand transition-colors disabled:cursor-not-allowed"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <MessageBubble key={i} role={m.role} content={m.content} metadata={m.metadata} />
          ))}

          {chatMutation.isPending && (
            <div className="flex items-center gap-2 text-sm text-muted">
              <Loader2 size={15} className="animate-spin" />
              Thinking…
            </div>
          )}

          {chatError && (
            <div className="flex items-start gap-2 text-sm text-loss bg-loss/10 rounded-lg px-3 py-2">
              <AlertCircle size={15} className="mt-0.5 shrink-0" />
              <span>{chatError}</span>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-surface-border p-3">
          <label className="flex flex-wrap items-center gap-2 text-xs text-muted mb-2">
            Portfolio context
            <select aria-label="Portfolio context" className="input text-sm w-auto max-w-full" value={requestedMode} disabled={chatMutation.isPending || pendingText !== null} onChange={event => setRequestedMode(event.target.value)}>
              <option value="none">No portfolio data</option>
              <option value="portfolio_summary">Portfolio summary</option>
            </select>
          </label>
          {!configured && !configLoading ? (
            <p className="text-xs text-muted text-center py-2">
              Add a DeepSeek API key above to start chatting.
            </p>
          ) : (
            <div className="flex items-end gap-2">
              <textarea
                aria-label="Message"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onInputKeyDown}
                rows={1}
                placeholder="Ask an investing question…"
                disabled={chatMutation.isPending}
                className="input flex-1 resize-none max-h-40 text-sm disabled:opacity-60"
              />
              <button
                aria-label="Send message"
                onClick={() => send()}
                disabled={!input.trim() || chatMutation.isPending}
                className="flex items-center justify-center bg-brand text-white rounded-lg w-11 h-11 shrink-0 hover:bg-brand/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {chatMutation.isPending ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <Send size={18} />
                )}
              </button>
            </div>
          )}
        </div>
      </div>
      </>
      </AsyncSection>
    </div>
  );
}

function MessageBubble({ role, content, metadata }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
          isUser
            ? "bg-brand text-white rounded-br-sm"
            : "bg-surface-card-elevated text-ink rounded-bl-sm"
        }`}
      >
        {content}
        {!isUser && metadata && <details className="mt-2 text-xs text-muted whitespace-normal">
          <summary className="cursor-pointer">Response details</summary>
          <p>{metadata.provider === "deepseek" ? "DeepSeek" : metadata.provider} · {metadata.model}</p>
          <p>{metadata.context_mode === "portfolio_summary" ? "Portfolio summary shared" : "No portfolio data shared"}</p>
          {metadata.context_as_of && <p>Context as of {formatDateTime(metadata.context_as_of)}</p>}
        </details>}
      </div>
    </div>
  );
}
