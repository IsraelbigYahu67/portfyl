import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { AlertCircle, CheckCircle, Info, X } from "lucide-react";
import { useT } from "../../i18n/I18nProvider";

const ToastContext = createContext(null);

/**
 * Lightweight toast notifications.
 *
 *   const toast = useToast();
 *   toast.success("Saved");
 *   toast.error("Something went wrong");
 */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

let seq = 0;

const VARIANTS = {
  success: { Icon: CheckCircle, accent: "text-gain", ring: "border-emerald-500/30" },
  error: { Icon: AlertCircle, accent: "text-loss", ring: "border-red-500/30" },
  info: { Icon: Info, accent: "text-muted", ring: "border-surface-border" },
};

export function ToastProvider({ children }) {
  const t = useT();
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (message, variant, duration = 4000) => {
      const id = ++seq;
      setToasts((list) => [...list, { id, message, variant }]);
      if (duration) setTimeout(() => dismiss(id), duration);
      return id;
    },
    [dismiss]
  );

  const toast = useMemo(
    () => ({
      success: (msg, opts) => push(msg, "success", opts?.duration),
      error: (msg, opts) => push(msg, "error", opts?.duration ?? 6000),
      info: (msg, opts) => push(msg, "info", opts?.duration),
      dismiss,
    }),
    [push, dismiss]
  );

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[70] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((item) => {
          const { Icon, accent, ring } = VARIANTS[item.variant] || VARIANTS.info;
          return (
            <div
              key={item.id}
              role="status"
              style={{ animation: "toast-in 0.15s ease-out" }}
              className={`card pointer-events-auto flex items-start gap-2.5 border shadow-lg ${ring}`}
            >
              <Icon size={18} className={`mt-0.5 shrink-0 ${accent}`} />
              <p className="flex-1 text-sm text-ink">{item.message}</p>
              <button
                type="button"
                onClick={() => dismiss(item.id)}
                aria-label={t("Dismiss notification")}
                className="shrink-0 text-muted transition-colors hover:text-ink"
              >
                <X size={15} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
