import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, Loader2, Trash2, X } from "lucide-react";

import {
  cancelWorkspaceDeletion,
  deleteWorkspaceNow,
  downloadWorkspaceExport,
  fetchDeletionStatus,
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
import { rich, useI18n, useT } from "../i18n/I18nProvider";
import AnalyticsPreferences from "../analytics/AnalyticsPreferences";
import AuthMethodDivider from "./auth/AuthMethodDivider";


// How long the warning keeps "continue" disabled, so the consequences are read
// before the typed confirmation and the password are asked for.
const WARNING_SECONDS = 10;


function errorMessage(error, fallback, t) {
  const body = error?.response?.data;
  const code = body?.code || body?.detail?.code;
  const messages = {
    workspace_owner_required: t("Only the workspace owner can delete the workspace."),
    workspace_has_other_members: t("Remove other workspace members before deleting."),
    workspace_confirmation_mismatch: t("The workspace name does not match."),
    recent_reauthentication_required: t("Confirm your identity again and retry."),
    reauthentication_identity_mismatch: t("The signed-in identity does not match this account."),
    email_verification_required: t("Verify your e-mail before deleting."),
    active_subscription: t("Cancel your subscription first, then delete the workspace."),
    account_deletion_unavailable: t("Deletion could not be completed right now. Nothing was deleted; try again in a moment."),
  };
  return messages[code] || fallback;
}


export default function DataPrivacySettings() {
  const t = useT();
  // Sent so the confirmation e-mail is written in the language of the app.
  const { language } = useI18n();
  const queryClient = useQueryClient();
  const { user, currentWorkspace, accountDeleted, reloadAccount } = useAuth();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [step, setStep] = useState("warning");
  const [secondsLeft, setSecondsLeft] = useState(WARNING_SECONDS);
  const [confirmation, setConfirmation] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const deleteButtonRef = useRef(null);
  const confirmationInputRef = useRef(null);
  const warningCancelRef = useRef(null);
  const closeDialog = () => {
    setDialogOpen(false);
    setStep("warning");
    setSecondsLeft(WARNING_SECONDS);
  };
  const dialogRef = useFocusTrap({
    active: dialogOpen,
    onEscape: closeDialog,
    initialFocusRef: warningCancelRef,
    restoreFocusRef: deleteButtonRef,
  });

  useEffect(() => {
    if (!dialogOpen || step !== "warning" || secondsLeft <= 0) return undefined;
    const timer = setTimeout(() => setSecondsLeft((seconds) => seconds - 1), 1000);
    return () => clearTimeout(timer);
  }, [dialogOpen, step, secondsLeft]);

  useEffect(() => {
    if (dialogOpen && step === "confirm") confirmationInputRef.current?.focus();
  }, [dialogOpen, step]);
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

  const deleteMutation = useMutation({
    mutationFn: async (method) => {
      const reauthIdToken = method === "google"
        ? await reauthenticateWithGoogle(user.email)
        : await reauthenticateWithPassword(user.email, password);
      if (!reauthIdToken) return null; // Google popup dismissed
      return deleteWorkspaceNow({
        reauth_id_token: reauthIdToken,
        confirmation,
        lang: language,
      });
    },
    onSuccess: (result) => {
      if (!result) return;
      setPassword("");
      setConfirmation("");
      setError(null);
      closeDialog();
      // The server has already erased the data. With the last workspace the
      // account went too, so the session is over; otherwise re-read the
      // account so the deleted workspace drops out of the list.
      if (result.account_deleted) accountDeleted();
      else reloadAccount().catch(() => {});
    },
    onError: (err) => {
      const message = err?.code?.startsWith?.("auth/")
        ? t(mapFirebaseAuthError(err))
        : errorMessage(err, t("Could not delete the workspace."), t);
      setError(message);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: cancelWorkspaceDeletion,
    onSuccess: () => {
      queryClient.setQueryData(queryKey, { scheduled: false });
      setError(null);
    },
    onError: (err) => setError(errorMessage(err, t("Could not cancel workspace deletion."), t)),
  });

  if (!currentWorkspace) return null;

  const confirmationMatches = confirmation === currentWorkspace.name;
  const canDelete = confirmationMatches && password.length > 0 && !deleteMutation.isPending;
  const canDeleteWithGoogle = confirmationMatches && !deleteMutation.isPending;
  const pendingMethod = deleteMutation.isPending ? deleteMutation.variables : null;

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
              {t("Erases this workspace and its data immediately. This cannot be undone.")}
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
              setStep("warning");
              setSecondsLeft(WARNING_SECONDS);
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
            className="dialog-panel w-full max-w-md border border-surface-border rounded-xl p-6 shadow-2xl space-y-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 id="delete-workspace-title" className="text-lg font-semibold text-loss">
                  {t("Delete workspace permanently")}
                </h3>
                <p id="delete-workspace-description" className="text-sm text-muted mt-1">
                  {t("This happens immediately and cannot be undone. Read the consequences before you continue.")}
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

            {step === "warning" ? (
              <>
                <ul className="list-disc pl-5 space-y-2 text-sm text-ink">
                  <li>{t("All portfolios, transactions, notes, alerts and settings in this workspace are erased at once.")}</li>
                  <li>{t("Connected broker keys and saved integrations are removed.")}</li>
                  <li>{t("If this is your last workspace, your Portfyl account and sign-in are deleted too, and you are signed out.")}</li>
                  <li>{t("Portfyl cannot restore anything afterwards, not even on request. Download the export first if you want a copy.")}</li>
                </ul>
                <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
                  <button
                    ref={warningCancelRef}
                    type="button"
                    onClick={closeDialog}
                    className="btn-ghost flex items-center justify-center text-sm font-medium min-h-11 md:min-h-0"
                  >
                    {t("Cancel")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setStep("confirm")}
                    disabled={secondsLeft > 0}
                    className="btn-primary !bg-loss hover:!bg-loss/90 flex items-center justify-center gap-2 min-h-11 md:min-h-0 text-sm disabled:opacity-40"
                  >
                    {secondsLeft > 0
                      ? t("Continue in {seconds} s", { seconds: secondsLeft })
                      : t("I understand, continue")}
                  </button>
                </div>
              </>
            ) : (
              <>
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
                  onClick={() => deleteMutation.mutate("password")}
                  disabled={!canDelete}
                  className="btn-primary !bg-loss hover:!bg-loss/90 w-full flex items-center justify-center gap-2 min-h-11 md:min-h-0 text-sm disabled:opacity-40"
                >
                  {pendingMethod === "password" && <Loader2 size={16} className="animate-spin" />}
                  {t("Delete permanently now")}
                </button>
                {googleEnabled && (
                  <>
                    <AuthMethodDivider />
                    <p className="text-xs text-muted">
                      {t("Signed up with Google? Confirm with your Google account instead of a password.")}
                    </p>
                    <button
                      type="button"
                      onClick={() => deleteMutation.mutate("google")}
                      disabled={!canDeleteWithGoogle}
                      className="btn-ghost text-loss w-full flex items-center justify-center gap-2 min-h-11 md:min-h-0 text-sm font-semibold disabled:opacity-40"
                    >
                      {pendingMethod === "google" && <Loader2 size={16} className="animate-spin" />}
                      {t("Confirm with Google")}
                    </button>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
