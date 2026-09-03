import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  configureRequestContext,
  exchangeSession,
  fetchMe,
  logoutAllSessions,
  logoutSession,
} from "../api";
import { signOutFirebaseClient } from "./firebase";

const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth() must be used within an <AuthProvider>");
  }
  return ctx;
}

function pickWorkspace(workspaces, preferredId) {
  if (!workspaces?.length) return null;
  if (preferredId) {
    const match = workspaces.find((w) => w.id === preferredId);
    if (match) return match;
  }
  return workspaces[0];
}

/**
 * Owns the Portfyl user/workspace/CSRF state: `/api/auth/me` bootstraps it on
 * mount, `loginWithIdToken` exchanges a verified Firebase ID token for it, and
 * `logout`/`logoutAll` tear it down. Firebase itself is only ever touched here
 * to sign the browser client out immediately after a successful exchange —
 * see docs/superpowers/specs/2026-09-01-portfyl-multiuser-foundation-design.md.
 */
export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState(null);
  const [workspaces, setWorkspaces] = useState([]);
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState(null);
  const [csrfToken, setCsrfToken] = useState(null);

  const currentWorkspace = useMemo(
    () => pickWorkspace(workspaces, currentWorkspaceId),
    [workspaces, currentWorkspaceId]
  );

  // Every identity/workspace change invalidates every previously-fetched
  // resource — a stale holding, alert, or note from a different account must
  // never flash on screen (see design spec, "clears the React Query cache
  // whenever identity or workspace changes").
  const applyAccount = useCallback(
    (payload, preferredWorkspaceId) => {
      const nextWorkspaces = payload?.workspaces || [];
      const nextWorkspace = pickWorkspace(nextWorkspaces, preferredWorkspaceId);
      const nextCsrfToken = payload?.csrf_token || null;
      setUser(payload?.user || null);
      setWorkspaces(nextWorkspaces);
      setCurrentWorkspaceId(nextWorkspace?.id || null);
      setCsrfToken(nextCsrfToken);
      configureRequestContext({ workspaceId: nextWorkspace?.id || null, csrfToken: nextCsrfToken });
      queryClient.clear();
    },
    [queryClient]
  );

  const clearAccount = useCallback(() => {
    setUser(null);
    setWorkspaces([]);
    setCurrentWorkspaceId(null);
    setCsrfToken(null);
    configureRequestContext({ workspaceId: null, csrfToken: null });
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((payload) => {
        if (!cancelled) applyAccount(payload, currentWorkspaceId);
      })
      .catch(() => {
        if (!cancelled) clearAccount();
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
    // Intentionally run once on mount only — applyAccount/clearAccount are
    // stable (useCallback), and re-running this on every render would refetch
    // the account on each re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loginWithIdToken = useCallback(
    async (idToken) => {
      const payload = await exchangeSession(idToken);
      applyAccount(payload);
      // The backend session cookie is now the durable credential; the
      // Firebase client session served its one purpose (proving the e-mail)
      // and must not linger in the browser.
      try {
        await signOutFirebaseClient();
      } catch {
        // Best-effort — a client-side sign-out failure must not undo an
        // already-established backend session.
      }
      return payload;
    },
    [applyAccount]
  );

  const logout = useCallback(async () => {
    try {
      await logoutSession();
    } finally {
      clearAccount();
    }
  }, [clearAccount]);

  const logoutAll = useCallback(async () => {
    try {
      await logoutAllSessions();
    } finally {
      clearAccount();
    }
  }, [clearAccount]);

  const selectWorkspace = useCallback(
    (workspaceId) => {
      const match = workspaces.find((w) => w.id === workspaceId);
      if (!match || match.id === currentWorkspaceId) return;
      setCurrentWorkspaceId(match.id);
      configureRequestContext({ workspaceId: match.id, csrfToken });
      queryClient.clear();
    },
    [workspaces, currentWorkspaceId, csrfToken, queryClient]
  );

  const value = useMemo(
    () => ({
      ready,
      user,
      workspaces,
      currentWorkspace,
      csrfToken,
      loginWithIdToken,
      logout,
      logoutAll,
      selectWorkspace,
    }),
    [ready, user, workspaces, currentWorkspace, csrfToken, loginWithIdToken, logout, logoutAll, selectWorkspace]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
