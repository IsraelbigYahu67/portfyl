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
import { mapFirebaseAuthError, reauthenticateWithPassword } from "../auth/firebase";
import { useFocusTrap } from "../hooks/useFocusTrap";


function errorMessage(error, fallback) {
  const body = error?.response?.data;
  const code = body?.code || body?.detail?.code;
  const messages = {
    workspace_owner_required: "Only the workspace owner can schedule deletion.",
    workspace_has_other_members: "Remove other workspace members before scheduling deletion.",
    workspace_confirmation_mismatch: "The workspace name does not match.",
    recent_reauthentication_required: "Sign in with your password again and retry.",
    reauthentication_identity_mismatch: "The signed-in identity does not match this account.",
    email_verification_required: "Verify your e-mail before scheduling deletion.",
  };
  return messages[code] || fallback;
}


export default function DataPrivacySettings() {
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
    onError: (err) => setError(errorMessage(err, "Failed to prepare the workspace export.")),
  });

  const scheduleMutation = useMutation({
    mutationFn: async () => {
      const reauthIdToken = await reauthenticateWithPassword(user.email, password);
      return scheduleWorkspaceDeletion({
        reauth_id_token: reauthIdToken,
        confirmation,
      });
    },
    onSuccess: (status) => {
      queryClient.setQueryData(queryKey, status);
      setPassword("");
      setConfirmation("");
      setDialogOpen(false);
      setError(null);
    },
    onError: (err) => {
      const message = err?.code?.startsWith?.("auth/")
        ? mapFirebaseAuthError(err)
        : errorMessage(err, "Could not schedule workspace deletion.");
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
    onError: (err) => setError(errorMessage(err, "Could not cancel workspace deletion.")),
  });

  if (!currentWorkspace) return null;

  const canSchedule =
    confirmation === currentWorkspace.name
    && password.length > 0
    && !scheduleMutation.isPending;

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-6 space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Data and privacy</h2>
        <p className="text-sm text-muted mt-0.5">
          Export or delete data for <span className="text-ink">{currentWorkspace.name}</span>.
          These controls are available on every plan.
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3" role="alert">
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-surface-border pb-5">
        <div>
          <div className="text-sm font-medium text-ink">Workspace export</div>
          <p className="text-xs text-muted mt-1">
            Download your portfolio data, preferences, notes, alerts, and safe integration metadata as versioned JSON.
          </p>
        </div>
        <button
          type="button"
          onClick={() => exportMutation.mutate()}
          disabled={exportMutation.isPending}
          className="shrink-0 flex items-center justify-center gap-2 border border-surface-border rounded-lg px-4 py-2 text-sm font-medium text-ink hover:bg-surface-hover disabled:opacity-50"
        >
          {exportMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
          Download JSON export
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <div className="text-sm font-medium text-loss">Delete workspace</div>
          {deletion?.scheduled ? (
            <p className="text-xs text-muted mt-1">
              Deletion is scheduled for {new Date(deletion.execute_after).toLocaleString()}.
              Your data and export remain available until then.
            </p>
          ) : (
            <p className="text-xs text-muted mt-1">
              Starts a {deletion?.grace_days || 30}-day grace period. You can cancel at any time before the deadline.
            </p>
          )}
        </div>

        {!isLoading && (deletion?.scheduled ? (
          <button
            ref={deleteButtonRef}
            type="button"
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
            className="flex items-center gap-2 border border-surface-border rounded-lg px-4 py-2 text-sm font-medium text-ink hover:bg-surface-hover disabled:opacity-50"
          >
            {cancelMutation.isPending && <Loader2 size={16} className="animate-spin" />}
            Cancel deletion
          </button>
        ) : (
          <button
            type="button"
            onClick={() => {
              setDialogOpen(true);
              setError(null);
            }}
            className="flex items-center gap-2 border border-loss/40 rounded-lg px-4 py-2 text-sm font-medium text-loss hover:bg-loss/10"
          >
            <Trash2 size={16} />
            Delete workspace
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
                  Schedule workspace deletion
                </h3>
                <p id="delete-workspace-description" className="text-sm text-muted mt-1">
                  Portfyl waits 30 days before permanent deletion. Access and export remain available during the grace period.
                </p>
              </div>
              <button
                type="button"
                aria-label="Close deletion dialog"
                onClick={closeDialog}
                className="text-muted hover:text-ink"
              >
                <X size={18} />
              </button>
            </div>

            <label className="block text-sm text-muted">
              Type {currentWorkspace.name} to confirm
              <input
                ref={confirmationInputRef}
                type="text"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                autoComplete="off"
                className="mt-1.5 w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-ink focus:outline-none focus:border-loss"
              />
            </label>
            <label className="block text-sm text-muted">
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                className="mt-1.5 w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-ink focus:outline-none focus:border-loss"
              />
            </label>
            <button
              type="button"
              onClick={() => scheduleMutation.mutate()}
              disabled={!canSchedule}
              className="w-full flex items-center justify-center gap-2 bg-loss text-white rounded-lg px-4 py-2.5 text-sm font-semibold disabled:opacity-40"
            >
              {scheduleMutation.isPending && <Loader2 size={16} className="animate-spin" />}
              Schedule deletion
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
