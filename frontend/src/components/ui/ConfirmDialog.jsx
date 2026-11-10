import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";
import { AlertTriangle } from "lucide-react";
import { useFocusTrap } from "../../hooks/useFocusTrap";
import { useT } from "../../i18n/I18nProvider";

const ConfirmContext = createContext(null);

/**
 * Promise-based replacement for window.confirm().
 *
 *   const confirm = useConfirm();
 *   if (await confirm({ title: "Delete?", danger: true })) doDelete();
 */
export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used within <ConfirmProvider>");
  return ctx;
}

// Callers pass already-translated text; the default labels are translated in
// the dialog itself.
const DEFAULTS = {
  title: null,
  message: "",
  confirmLabel: null,
  cancelLabel: null,
  danger: false,
};

export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null);
  const resolverRef = useRef(null);

  const confirm = useCallback((options = {}) => {
    return new Promise((resolve) => {
      resolverRef.current = resolve;
      setState({ ...DEFAULTS, ...options });
    });
  }, []);

  const resolve = useCallback((result) => {
    setState(null);
    if (resolverRef.current) {
      resolverRef.current(result);
      resolverRef.current = null;
    }
  }, []);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && <ConfirmDialog {...state} onResolve={resolve} />}
    </ConfirmContext.Provider>
  );
}

function ConfirmDialog({ title: givenTitle, message, confirmLabel: givenConfirm, cancelLabel: givenCancel, danger, onResolve }) {
  const t = useT();
  const title = givenTitle ?? t("Are you sure?");
  const confirmLabel = givenConfirm ?? t("Confirm");
  const cancelLabel = givenCancel ?? t("Cancel");
  const cancelBtnRef = useRef(null);
  const confirmBtnRef = useRef(null);
  const titleId = "confirm-dialog-title";
  const descId = "confirm-dialog-desc";

  const containerRef = useFocusTrap({
    active: true,
    onEscape: () => onResolve(false),
    // Destructive dialogs default focus to Cancel so an accidental Enter is safe.
    initialFocusRef: danger ? cancelBtnRef : confirmBtnRef,
  });

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4"
      style={{ backdropFilter: "blur(var(--blur-overlay))" }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onResolve(false);
      }}
    >
      <div
        ref={containerRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={message ? descId : undefined}
        className="card w-full max-w-sm space-y-4"
      >
        <div className="flex items-start gap-3">
          {danger && (
            /* deliberately not --loss: destructive-action red is fixed, not tied to P&L semantics */
            <span className="shrink-0 mt-0.5 text-red-600">
              <AlertTriangle size={20} />
            </span>
          )}
          <div className="space-y-1">
            <h2 id={titleId} className="text-lg font-bold leading-snug">
              {title}
            </h2>
            {message && (
              <p id={descId} className="text-sm text-muted">
                {message}
              </p>
            )}
          </div>
        </div>
        <div className="flex gap-2 pt-1">
          <button
            ref={cancelBtnRef}
            type="button"
            onClick={() => onResolve(false)}
            className="btn-ghost flex-1"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmBtnRef}
            type="button"
            onClick={() => onResolve(true)}
            className={`flex-1 rounded-lg px-4 py-2 font-semibold text-white transition-colors ${
              danger
                ? /* deliberately not --loss: destructive-action red is fixed, not tied to P&L semantics */
                  "bg-red-600 hover:bg-red-700"
                : "bg-brand hover:bg-brand-dim"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
