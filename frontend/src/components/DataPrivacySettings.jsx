import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, Loader2, Trash2, X } from "lucide-react";

import {
  cancelWorkspaceDeletion,
  downloadWorkspaceExport,
  fetchDeletionStatus,
  scheduleWorkspaceDeletion,
} from "../api";
import { useAuth } from "../auth/AuthProvider";
import {
  isGoogleSignInEnabled,
  mapFirebaseAuthError,
  prepareGoogleSignIn,
  reauthenticateWithGoogle,
  reauthenticateWithPassword,
} from "../auth/firebase";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { rich, useT } from "../i18n/I18nProvider";
import AnalyticsPreferences from "../analytics/AnalyticsPreferences";
import AuthMethodDivider from "./auth/AuthMethodDivider";


function errorMessage(error, fallback, t) {
  const body = error?.response?.data;
  const code = body?.code || body?.detail?.code;
  const messages = {
    workspace_owner_required: t("Only the workspace owner can schedule deletion."),
    workspace_has_other_members: t("Remove other workspace members before scheduling deletion."),
    workspace_confirmation_mismatch: t("The workspace name does not match."),
    recent_reauthentication_required: t("Confirm your identity again and retry."),
    reauthentication_identity_mismatch: t("The signed-in identity does not match this account."),
    email_verification_required: t("Verify your e-mail before scheduling deletion."),
  };
  return messages[code] || fallback;
}


export default function DataPrivacySettings() {
  const t = useT();
  const queryClient = useQueryClient();
  const { user, currentWorkspace } = useAuth();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const deleteButtonRef = useRef(null);
  const confirmationInputRef = useRef(null);
  const closeDialog = () => setDialogOpen(false);
  const dialogRef = useFocusTrap({
    active: dialogOpen,
    onEscape: closeDialog,
    initialFocusRef: confirmationInputRef,
    restoreFocusRef: deleteButtonRef,
  });
  const queryKey = ["workspace-deletion", currentWorkspace?.id];
  // Either proof is equivalent to the backend: it only checks that a fresh
  // Firebase token belongs to this user. Offering both avoids having to know
  // which providers the account has.
  const googleEnabled = isGoogleSignInEnabled();

  const { data: deletion, isLoading } = useQuery({
    queryKey,
    queryFn: fetchDeletionStatus,
    enabled: Boolean(currentWorkspace?.id),
  });

  const exportMutation = useMutation({
    mutationFn: downloadWorkspaceExport,
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setError(null);
    },
    onError: (err) => setError(errorMessage(err, t("Failed to prepare the workspace export."), t)),
  });

  const scheduleMutation = useMutation({
    mutationFn: async (method) => {
      const reauthIdToken = method === "google"
        ? await reauthenticateWithGoogle(user.email)
        : await reauthenticateWithPassword(user.email, password);
      if (!reauthIdToken) return null; // Google popup dismissed
      return scheduleWorkspaceDeletion({
        reauth_id_token: reauthIdToken,
        confirmation,
      });
    },
    onSuccess: (status) => {
      if (!status) return;
      queryClient.setQueryData(queryKey, status);
      setPassword("");
      setConfirmation("");
      setDialogOpen(false);
      setError(null);
    },
    onError: (err) => {
      const message = err?.code?.startsWith?.("auth/")
        ? t(mapFirebaseAuthError(err))
        : errorMessage(err, t("Could not schedule workspace deletion."), t);
      setError(message);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: cancelWorkspaceDeletion,
    onSuccess: () => {
      queryClient.setQueryData(queryKey, {
        scheduled: false,
        grace_days: deletion?.grace_days || 30,
      });
      setError(null);
    },
    onError: (err) => setError(errorMessage(err, t("Could not cancel workspace deletion."), t)),
  });

  if (!currentWorkspace) return null;

  const confirmationMatches = confirmation === currentWorkspace.name;
  const canSchedule = confirmationMatches && password.length > 0 && !scheduleMutation.isPending;
  const canScheduleWithGoogle = confirmationMatches && !scheduleMutation.isPending;
  const pendingMethod = scheduleMutation.isPending ? scheduleMutation.variables : null;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
      <div>
        <h2 className="text-lg font-semibold">{t("Data and privacy")}</h2>
        <p className="text-sm text-muted mt-0.5">
          {rich(t("Export or delete data for <b>{name}</b>.", { name: currentWorkspace.name }), {
            b: (name) => <span className="text-ink">{name}</span>,
          })}{" "}
          {t("These controls are available on every plan.")}
        </p>
      </div>

      {/* An inset well, not a second raised card: the nested card's own
          surface is flattened so only the pressed well shows. */}
      <div
        data-surface="inset"
        className="rounded-2xl p-2 [&>.card]:!border-transparent [&>.card]:!bg-transparent [&>.card]:!bg-none [&>.card]:!shadow-none [&>.card]:!backdrop-blur-none"
        style={{ background: "var(--bg-subtle)", boxShadow: "var(--clay-inset-sm, var(--shadow-inset, none))" }}
      >
        <AnalyticsPreferences />
      </div>

      {error && (
        <div className="flex items-start gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3" role="alert">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-surface-border pb-5">
        <div>
          <div className="text-sm font-medium text-ink">{t("Workspace export")}</div>
          <p className="text-xs text-muted mt-1">
            {t("Download your portfolio data, preferences, notes, alerts, and safe integration metadata as versioned JSON.")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => exportMutation.mutate()}
          disabled={exportMutation.isPending}
          className="btn-ghost shrink-0 flex items-center justify-center gap-2 text-sm font-medium min-h-11 md:min-h-0 disabled:opacity-50"
        >
          {exportMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
          {t("Download JSON export")}
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <div className="text-sm font-medium text-loss">{t("Delete workspace")}</div>
          {deletion?.scheduled ? (
            <p className="text-xs text-muted mt-1">
              {t("Deletion is scheduled for {date}.", { date: new Date(deletion.execute_after).toLocaleString() })}{" "}
              {t("Your data and export remain available until then.")}
            </p>
          ) : (
            <p className="text-xs text-muted mt-1">
              {t("Starts a {days}-day grace period. You can cancel at any time before the deadline.", { days: deletion?.grace_days || 30 })}
            </p>
          )}
        </div>

        {!isLoading && (deletion?.scheduled ? (
          <button
            ref={deleteButtonRef}
            type="button"
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
            className="btn-ghost flex items-center gap-2 text-sm font-medium min-h-11 md:min-h-0 disabled:opacity-50"
          >
            {cancelMutation.isPending && <Loader2 size={16} className="animate-spin" />}
            {t("Cancel deletion")}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => {
              setDialogOpen(true);
              setError(null);
              // Warm Firebase up so the Google popup opens straight from the
              // click instead of being blocked after an async load.
              if (googleEnabled) prepareGoogleSignIn().catch(() => {});
            }}
            className="btn-ghost text-loss flex items-center gap-2 text-sm font-medium min-h-11 md:min-h-0"
          >
            <Trash2 size={16} />
            {t("Delete workspace")}
          </button>
        ))}
      </div>

      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="presentation">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-workspace-title"
            aria-describedby="delete-workspace-description"
            className="w-full max-w-md bg-surface-card border border-surface-border rounded-xl p-6 shadow-2xl space-y-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 id="delete-workspace-title" className="text-lg font-semibold text-loss">
                  {t("Schedule workspace deletion")}
                </h3>
                <p id="delete-workspace-description" className="text-sm text-muted mt-1">
                  {t("Portfyl waits 30 days before permanent deletion. Access and export remain available during the grace period.")}
                </p>
              </div>
              <button
                type="button"
                aria-label={t("Close deletion dialog")}
                onClick={closeDialog}
                className="text-muted hover:text-ink"
              >
                <X size={18} />
              </button>
            </div>

            <label className="block text-sm text-muted">
              {t("Type {name} to confirm", { name: currentWorkspace.name })}
              <input
                ref={confirmationInputRef}
                type="text"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                autoComplete="off"
                className="input mt-1.5 focus:border-loss"
              />
            </label>
            <label className="block text-sm text-muted">
              {t("Password")}
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                className="input mt-1.5 focus:border-loss"
              />
            </label>
            <button
              type="button"
              onClick={() => scheduleMutation.mutate("password")}
              disabled={!canSchedule}
              className="btn-primary !bg-loss hover:!bg-loss/90 w-full flex items-center justify-center gap-2 min-h-11 md:min-h-0 text-sm disabled:opacity-40"
            >
              {pendingMethod === "password" && <Loader2 size={16} className="animate-spin" />}
              {t("Schedule deletion")}
            </button>
            {googleEnabled && (
              <>
                <AuthMethodDivider />
                <p className="text-xs text-muted">
                  {t("Signed up with Google? Confirm with your Google account instead of a password.")}
                </p>
                <button
                  type="button"
                  onClick={() => scheduleMutation.mutate("google")}
                  disabled={!canScheduleWithGoogle}
                  className="btn-ghost text-loss w-full flex items-center justify-center gap-2 min-h-11 md:min-h-0 text-sm font-semibold disabled:opacity-40"
                >
                  {pendingMethod === "google" && <Loader2 size={16} className="animate-spin" />}
                  {t("Confirm with Google")}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
