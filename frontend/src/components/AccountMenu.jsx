import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut, User } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";

export default function AccountMenu() {
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
      setError("Could not sign out. You are still signed in. Please try again.");
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
        aria-label={`Account menu for ${user.email}`}
        className="w-full flex items-center gap-2 bg-surface border border-surface-border rounded-lg px-3 py-2 text-left hover:border-slate-300 transition-colors"
        disabled={busy}
      >
        <User size={14} className="text-brand shrink-0" />
        <span className="flex-1 min-w-0 text-xs font-medium text-ink truncate" title={user.email}>
          {user.email}
        </span>
        <ChevronDown size={14} className={`text-muted transition-transform shrink-0 ${open ? "rotate-180" : ""}`} />
      </button>

      {error && (
        <p role="alert" className="mt-1 text-xs text-loss">
          {error}
        </p>
      )}

      {open && (
        <div
          role="menu"
          aria-label="Account"
          className="absolute z-40 left-0 right-0 bottom-full mb-1 bg-surface-card border border-surface-border rounded-lg shadow-lg py-1"
        >
          <button
            ref={firstItemRef}
            role="menuitem"
            type="button"
            onClick={handleLogout}
            disabled={busy}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-ink hover:bg-surface-hover disabled:opacity-50 transition-colors"
          >
            <LogOut size={13} />
            Log out
          </button>
          <button
            role="menuitem"
            type="button"
            onClick={handleLogoutAll}
            disabled={busy}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-loss hover:bg-surface-hover disabled:opacity-50 transition-colors"
          >
            <LogOut size={13} />
            Log out everywhere
          </button>
        </div>
      )}
    </div>
  );
}
