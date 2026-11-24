import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  configureRequestContext,
  exchangeSession,
  fetchMe,
  logoutAllSessions,
  logoutSession,
  setCsrfRefreshHandler,
} from "../api";
import { signOutFirebaseClient } from "./firebase";
import { useAnalytics } from "../analytics/AnalyticsProvider";
import BotCheckDialog from "./BotCheckDialog";

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
  const analytics = useAnalytics();
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

  // api.js replays a request that failed with 403 csrf_failed once the token
  // has been re-read. Only the token is refreshed: applyAccount would also
  // clear the query cache, which a CSRF refresh must not do.
  const workspaceIdRef = useRef(null);
  useEffect(() => {
    workspaceIdRef.current = currentWorkspace?.id ?? null;
  }, [currentWorkspace?.id]);

  useEffect(() => {
    setCsrfRefreshHandler(async () => {
      const payload = await fetchMe();
      const nextCsrfToken = payload?.csrf_token || null;
      setCsrfToken(nextCsrfToken);
      configureRequestContext({ workspaceId: workspaceIdRef.current, csrfToken: nextCsrfToken });
    });
    return () => setCsrfRefreshHandler(null);
  }, []);

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

  // Identifies the signed-in user with analytics once the account has fully
  // loaded (a user id AND a provisioned workspace) and consent is accepted,
  // in whichever order those become true first. currentWorkspace.id only
  // gates *when* this fires -- it is never sent as an identify property,
  // only the opaque user id is.
  useEffect(() => {
    if (analytics.ready && analytics.consent === "accepted" && user?.id && currentWorkspace?.id) {
      analytics.identify(String(user.id));
    }
  }, [analytics.ready, analytics.consent, analytics.identify, user?.id, currentWorkspace?.id]);

  // The new-account bot check. The server asks for it (`bot_check_required`)
  // only when an exchange would create a new account. One dialog serves every
  // caller waiting at that moment (VerifyEmail polls), via the shared promise.
  const botCheck = useRef(null);
  const [botCheckOpen, setBotCheckOpen] = useState(false);

  const askBotCheck = useCallback(() => {
    if (!botCheck.current) {
      let resolve;
      const promise = new Promise((done) => {
        resolve = done;
      });
      botCheck.current = { promise, resolve };
      setBotCheckOpen(true);
    }
    return botCheck.current.promise;
  }, []);

  // `token` is the Turnstile token, or null when the person cancelled.
  const finishBotCheck = useCallback((token) => {
    const pending = botCheck.current;
    botCheck.current = null;
    setBotCheckOpen(false);
    pending?.resolve(token);
  }, []);

  const cancelBotCheck = useCallback(() => finishBotCheck(null), [finishBotCheck]);

  const loginWithIdToken = useCallback(
    async (idToken, { termsAccepted = false } = {}) => {
      // Sent only when the register page's box was ticked (first Google sign-in).
      const accepted = termsAccepted ? { termsAccepted: true } : null;
      let payload;
      try {
        payload = await (accepted ? exchangeSession(idToken, accepted) : exchangeSession(idToken));
      } catch (error) {
        if (error?.response?.data?.code !== "bot_check_required") throw error;
        const turnstileToken = await askBotCheck();
        // Cancelled: the caller gets the original error. One retry only; a
        // `bot_check_failed` on it is the caller's to show.
        if (!turnstileToken) throw error;
        payload = await exchangeSession(idToken, { turnstileToken, ...accepted });
      }
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
    [applyAccount, askBotCheck]
  );

  // The local sign-out only happens once the server has really ended the
  // session. If the request fails (even after api.js's csrf_failed retry), the
  // session cookie is still valid, so wiping local state would only pretend:
  // a reload would silently sign the user back in. Leave them signed in and
  // let the caller show the error. A 401 means the session is already gone,
  // which is the outcome the user wanted.
  const finishSignOut = useCallback(
    (error) => {
      if (error && error?.response?.status !== 401) throw error;
      clearAccount();
      // An explicit sign-out, unlike an unauthenticated initial /me request,
      // ends this browser's analytics identity too.
      analytics.reset();
    },
    [clearAccount, analytics.reset]
  );

  const logout = useCallback(async () => {
    try {
      await logoutSession();
    } catch (error) {
      finishSignOut(error);
      return;
    }
    finishSignOut();
  }, [finishSignOut]);

  const logoutAll = useCallback(async () => {
    try {
      await logoutAllSessions();
    } catch (error) {
      finishSignOut(error);
      return;
    }
    finishSignOut();
  }, [finishSignOut]);

  // The server erased the signed-in account (its last workspace was deleted)
  // and already cleared the session cookie, so there is nothing to revoke:
  // just forget the local state, which sends the app back to the login screen.
  const accountDeleted = useCallback(() => {
    clearAccount();
    analytics.reset();
  }, [clearAccount, analytics.reset]);

  // A workspace was deleted but the user keeps another one: re-read the
  // account so the deleted workspace disappears from the list and the next
  // one becomes current.
  const reloadAccount = useCallback(async () => {
    const payload = await fetchMe();
    applyAccount(payload);
    return payload;
  }, [applyAccount]);

  const selectWorkspace = useCallback(
    (workspaceId) => {
      const match = workspaces.find((w) => w.id === workspaceId);
      if (!match || match.id === currentWorkspaceId) return;
      setCurrentWorkspaceId(match.id);
      configureRequestContext({ workspaceId: match.id, csrfToken });
      queryClient.clear();
      // Same person, different workspace: drop any workspace-scoped adapter
      // state and re-identify by user id only -- the workspace itself is
      // never sent to analytics.
      analytics.reset();
      if (user?.id) analytics.identify(String(user.id));
    },
    [workspaces, currentWorkspaceId, csrfToken, queryClient, analytics.reset, analytics.identify, user?.id]
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
      accountDeleted,
      reloadAccount,
      selectWorkspace,
    }),
    [ready, user, workspaces, currentWorkspace, csrfToken, loginWithIdToken, logout, logoutAll, accountDeleted, reloadAccount, selectWorkspace]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      <BotCheckDialog open={botCheckOpen} onToken={finishBotCheck} onCancel={cancelBotCheck} />
    </AuthContext.Provider>
  );
}
