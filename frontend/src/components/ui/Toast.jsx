import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { AlertCircle, CheckCircle, Info, X } from "lucide-react";

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
  success: { Icon: CheckCircle, accent: "text-emerald-600", ring: "border-emerald-500/30" },
  error: { Icon: AlertCircle, accent: "text-red-600", ring: "border-red-500/30" },
  info: { Icon: Info, accent: "text-slate-500", ring: "border-surface-border" },
};

export function ToastProvider({ children }) {
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
        {toasts.map((t) => {
          const { Icon, accent, ring } = VARIANTS[t.variant] || VARIANTS.info;
          return (
            <div
              key={t.id}
              role="status"
              style={{ animation: "toast-in 0.15s ease-out" }}
              className={`card pointer-events-auto flex items-start gap-2.5 border shadow-lg ${ring}`}
            >
              <Icon size={18} className={`mt-0.5 shrink-0 ${accent}`} />
              <p className="flex-1 text-sm text-slate-700">{t.message}</p>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss notification"
                className="shrink-0 text-slate-400 transition-colors hover:text-slate-700"
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
