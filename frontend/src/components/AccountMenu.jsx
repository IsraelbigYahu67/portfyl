import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, User } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { useT } from "../i18n/I18nProvider";

// `compact` is the phone top-bar variant: a 44px round button showing only the
// user icon, with the menu opening downward and naming the signed-in e-mail.
export default function AccountMenu({ compact = false }) {
  const t = useT();
  const { user, logout, logoutAll } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const containerRef = useRef(null);
  const triggerRef = useRef(null);
  const firstItemRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    firstItemRef.current?.focus();

    const onClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!user) return null;

  // AuthProvider only signs the browser out once the server confirmed it; on a
  // failure it rejects and the user stays signed in, so say so.
  async function runSignOut(action) {
    setOpen(false);
    setBusy(true);
    setError("");
    try {
      await action();
    } catch {
      setError(t("Could not sign out. You are still signed in. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  const handleLogout = () => runSignOut(logout);
  const handleLogoutAll = () => runSignOut(logoutAll);

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("Account menu for {email}", { email: user.email })}
        className={compact
          ? "grid h-11 w-11 place-items-center rounded-full bg-surface border border-surface-border hover:border-brand transition-colors"
          : "w-full flex items-center gap-2 bg-surface border border-surface-border rounded-lg px-3 py-2 text-left hover:border-slate-300 transition-colors"}
        disabled={busy}
      >
        <User size={compact ? 18 : 14} className="text-brand shrink-0" />
        {!compact && (
          <>
            <span className="flex-1 min-w-0 text-xs font-medium text-ink truncate" title={user.email}>
              {user.email}
            </span>
            <ChevronDown size={14} className={`text-muted transition-transform shrink-0 ${open ? "rotate-180" : ""}`} />
          </>
        )}
      </button>

      {error && (
        <p role="alert" className="mt-1 text-xs text-loss">
          {error}
        </p>
      )}

      {open && (
        <div
          role="menu"
          aria-label={t("Account")}
          className={`absolute z-40 border border-surface-border rounded-lg shadow-lg py-1 ${compact ? "right-0 top-full mt-2 w-64 max-w-[calc(100vw-1.5rem)]" : "left-0 right-0 bottom-full mb-1"}`}
          style={{ background: "linear-gradient(var(--surface-card), var(--surface-card)), var(--bg)" }}
        >
          {compact && (
            <p className="px-3 py-2 text-xs text-muted truncate border-b border-hairline" title={user.email}>
              {user.email}
            </p>
          )}
          <button
            ref={firstItemRef}
            role="menuitem"
            type="button"
            onClick={handleLogout}
            disabled={busy}
            className="w-full flex items-center gap-2 px-3 py-2 min-h-11 text-sm text-ink hover:bg-surface-hover disabled:opacity-50 transition-colors"
          >
            <LogOut size={13} />
            {t("Log out")}
          </button>
          <button
            role="menuitem"
            type="button"
            onClick={handleLogoutAll}
            disabled={busy}
            className="w-full flex items-center gap-2 px-3 py-2 min-h-11 text-sm text-loss hover:bg-surface-hover disabled:opacity-50 transition-colors"
          >
            <LogOut size={13} />
            {t("Log out everywhere")}
          </button>
        </div>
      )}
    </div>
  );
}
