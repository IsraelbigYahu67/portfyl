import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, Loader2, Trash2, X } from "lucide-react";

import {
  cancelWorkspaceDeletion,
  deleteWorkspaceNow,
  downloadWorkspaceExport,
  fetchDeletionStatus,
  openBillingPortal,
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
import { BILLING_STATUS_KEY, billingStatusQuery } from "../lib/billingStatusQuery";
import { formatMoney } from "../lib/format";
import AnalyticsPreferences from "../analytics/AnalyticsPreferences";
import AuthMethodDivider from "./auth/AuthMethodDivider";


// How long the warning keeps "continue" disabled, so the consequences are read
// before the typed confirmation and the password are asked for.
const WARNING_SECONDS = 10;


// A subscription that still gives the workspace paid features. Deleting the
// workspace cancels it on the spot, so the user must consent to that first.
const LIVE_SUBSCRIPTION_STATUSES = ["active", "trialing", "past_due"];

function longDate(iso, language) {
  const date = new Date(iso);
  if (!iso || !Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat(language, { day: "numeric", month: "long", year: "numeric" }).format(date);
}


function errorCode(error) {
  const body = error?.response?.data;
  return body?.code || body?.detail?.code;
}


function errorMessage(error, fallback, t) {
  const code = errorCode(error);
  const messages = {
    workspace_owner_required: t("Only the workspace owner can delete the workspace."),
    workspace_has_other_members: t("Remove other workspace members before deleting."),
    workspace_confirmation_mismatch: t("The workspace name does not match."),
    recent_reauthentication_required: t("Confirm your identity again and retry."),
    reauthentication_identity_mismatch: t("The signed-in identity does not match this account."),
    email_verification_required: t("Verify your e-mail before deleting."),
    active_subscription: t("You have a paid subscription. Reopen this dialog so that we can show you what happens to it, then try again."),
    subscription_cancel_failed: t("We could not cancel your subscription, so nothing was deleted. Please try again in a moment."),
    subscription_refund_failed: t("We could not refund your payment, so nothing was deleted and your subscription is unchanged. Please try again in a moment."),
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
  // What the person was shown when they pressed "continue", and so what the
  // server is told they agreed to (the billing status may change afterwards).
  const [consent, setConsent] = useState({ live: false, refund: false });
  // Set when the server found the 14-day window had closed meanwhile.
  const [notice, setNotice] = useState(null);
  // Set after a successful deletion that refunded the payment: the dialog then
  // stays open on a confirmation, and the post-delete hand-off waits for Close.
  const [outcome, setOutcome] = useState(null);
  const deleteButtonRef = useRef(null);
  const confirmationInputRef = useRef(null);
  const warningCancelRef = useRef(null);
  const refundCloseRef = useRef(null);
  const closeDialog = () => {
    setDialogOpen(false);
    setStep("warning");
    setSecondsLeft(WARNING_SECONDS);
    setNotice(null);
  };
  // The data is already gone on the confirmation step, so closing it (button,
  // X or Escape) is what hands over to the signed-out / reloaded account.
  const finishDeletion = () => {
    const done = outcome;
    setOutcome(null);
    closeDialog();
    if (done?.accountDeleted) accountDeleted();
    else reloadAccount().catch(() => {});
  };
  const dismissDialog = () => (step === "refunded" ? finishDeletion() : closeDialog());
  const dialogRef = useFocusTrap({
    active: dialogOpen,
    onEscape: dismissDialog,
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
    if (dialogOpen && step === "refunded") refundCloseRef.current?.focus();
  }, [dialogOpen, step]);

  // Back on the warning after the server changed the terms: keep keyboard
  // focus inside the dialog instead of on the control that just disappeared.
  useEffect(() => {
    if (dialogOpen && step === "warning" && notice) warningCancelRef.current?.focus();
  }, [dialogOpen, step, notice]);
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

  // Read only while the dialog is open, and always fresh. Where billing does
  // not exist (the local edition, 404) there is simply no subscription and the
  // dialog behaves as it always did. Any other failure, or a read still in
  // flight, blocks "continue": we must not let the person go on without
  // knowing what happens to a subscription.
  const billingQuery = useQuery({
    ...billingStatusQuery,
    staleTime: 0,
    enabled: dialogOpen && Boolean(currentWorkspace?.id),
  });
  const billingFailed = billingQuery.isError && billingQuery.error?.response?.status !== 404;
  const billingPending = dialogOpen && (billingQuery.isPending || billingQuery.isFetching);
  const billingBlocked = billingPending || billingFailed;
  const subscription = billingFailed ? undefined : billingQuery.data?.subscription;
  const hasLiveSubscription = Boolean(subscription) && LIVE_SUBSCRIPTION_STATUSES.includes(subscription.status);
  const periodEnd = hasLiveSubscription ? longDate(subscription.current_period_end, language) : null;
  // The server decides, by its own clock, whether the 14 days after the first
  // paid order are still running. Anything but a literal true counts as closed.
  const withdrawalOpen = hasLiveSubscription && subscription.withdrawal_open === true;

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
        // Only sent when the dialog showed the consent for a live subscription.
        ...(consent.live ? { cancel_subscription: true } : {}),
        // Only sent when the dialog promised the full refund, so the server can
        // refuse (409) if the 14 days ran out while the person was deleting.
        ...(consent.refund ? { refund_expected: true } : {}),
      });
    },
    onSuccess: (result) => {
      if (!result) return;
      setPassword("");
      setConfirmation("");
      setError(null);
      setNotice(null);
      if (result.refunded === true) {
        // Show the refund before the session ends; Close does the hand-off.
        const cents = result.refunded_amount_cents;
        const currency = typeof result.currency === "string" && result.currency ? result.currency : null;
        setOutcome({
          accountDeleted: Boolean(result.account_deleted),
          amount: typeof cents === "number" && Number.isFinite(cents) && currency
            ? formatMoney(cents / 100, currency)
            : null,
        });
        setStep("refunded");
        return;
      }
      closeDialog();
      // The server has already erased the data. With the last workspace the
      // account went too, so the session is over; otherwise re-read the
      // account so the deleted workspace drops out of the list.
      if (result.account_deleted) accountDeleted();
      else reloadAccount().catch(() => {});
    },
    onError: (err) => {
      if (err?.response?.status === 409 && errorCode(err) === "withdrawal_window_changed") {
        // Nothing was deleted or refunded. Re-read the status so the warning
        // shows the no-refund consent, and make the person confirm it afresh.
        queryClient.invalidateQueries({ queryKey: BILLING_STATUS_KEY });
        setError(null);
        setPassword("");
        setConfirmation("");
        setConsent({ live: false, refund: false });
        setNotice(t("The 14-day withdrawal period ended while you were deleting, so no refund applies. Nothing was deleted. Please read the updated information and decide again."));
        setStep("warning");
        setSecondsLeft(WARNING_SECONDS);
        return;
      }
      if (errorCode(err) === "active_subscription") {
        queryClient.invalidateQueries({ queryKey: BILLING_STATUS_KEY });
      }
      const message = err?.code?.startsWith?.("auth/")
        ? t(mapFirebaseAuthError(err))
        : errorMessage(err, t("Could not delete the workspace."), t);
      setError(message);
    },
  });

  // Same hand-off as the pricing page: the Stripe portal opens in this tab.
  const portalMutation = useMutation({
    mutationFn: openBillingPortal,
    onSuccess: ({ url }) => window.location.assign(url),
    onError: () => setError(t("The payment page could not be opened. Please try again.")),
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
  const errorAlert = error && (
    <div className="flex items-start gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3" role="alert">
      <AlertTriangle size={16} className="shrink-0 mt-0.5" />
      {error}
    </div>
  );

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

      {/* While the dialog is open the modal covers the page, so the message is
          shown inside it instead. */}
      {!dialogOpen && errorAlert}

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
              setNotice(null);
              setConsent({ live: false, refund: false });
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

      {dialogOpen && createPortal(
        // In a portal like ui/Modal: a transformed ancestor (animate-fade-up)
        // would turn `fixed` into "fixed to that box", and the dim would stop
        // short of the top bar. z-[60] sits above the top (z-30) and bottom
        // (z-40) bars.
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
          style={{ backdropFilter: "blur(var(--blur-overlay))" }}
          role="presentation"
        >
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
                <h3 id="delete-workspace-title" className={`text-lg font-semibold ${step === "refunded" ? "text-ink" : "text-loss"}`}>
                  {step === "refunded" ? t("Workspace deleted") : t("Delete workspace permanently")}
                </h3>
                <p id="delete-workspace-description" className="text-sm text-muted mt-1">
                  {step === "refunded"
                    ? (outcome?.amount
                      ? t("Your workspace was deleted and we refunded {amount}. The money returns to your original payment method; the payment provider will e-mail you a confirmation.", { amount: outcome.amount })
                      : t("Your workspace was deleted and we refunded your payment. The money returns to your original payment method; the payment provider will e-mail you a confirmation."))
                    : t("This happens immediately and cannot be undone. Read the consequences before you continue.")}
                </p>
              </div>
              <button
                type="button"
                aria-label={t("Close deletion dialog")}
                onClick={dismissDialog}
                className="text-muted hover:text-ink"
              >
                <X size={18} />
              </button>
            </div>

            {step !== "refunded" && errorAlert}

            {step === "refunded" ? (
              <div className="flex justify-end">
                <button
                  ref={refundCloseRef}
                  type="button"
                  onClick={finishDeletion}
                  className="btn-primary flex items-center justify-center min-h-11 md:min-h-0 text-sm"
                >
                  {t("Close")}
                </button>
              </div>
            ) : step === "warning" ? (
              <>
                {notice && (
                  <div className="flex items-start gap-2 text-sm font-medium text-ink bg-brand-light border border-brand/30 rounded-lg px-4 py-3" role="alert">
                    <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                    {notice}
                  </div>
                )}
                <ul className="list-disc pl-5 space-y-2 text-sm text-ink">
                  <li>{t("All portfolios, transactions, notes, alerts and settings in this workspace are erased at once.")}</li>
                  <li>{t("Connected broker keys and saved integrations are removed.")}</li>
                  <li>{t("If this is your last workspace, your Portfyl account and sign-in are deleted too, and you are signed out.")}</li>
                  <li>{t("Portfyl cannot restore anything afterwards, not even on request. Download the export first if you want a copy.")}</li>
                  {hasLiveSubscription && !withdrawalOpen && (
                    <li className="font-medium text-loss">
                      {periodEnd
                        ? t("I agree that I am deleting this workspace and that I immediately lose the remaining paid features until the end of the billing period ({date}). My subscription is cancelled and the rest of the period is not refunded.", { date: periodEnd })
                        : t("I agree that I am deleting this workspace and that I immediately lose the remaining paid features until the end of the billing period. My subscription is cancelled and the rest of the period is not refunded.")}
                    </li>
                  )}
                </ul>
                {withdrawalOpen && (
                  <div className="text-sm font-medium text-ink bg-brand-light border border-brand/30 rounded-lg px-4 py-3" role="note">
                    {t("You ordered this subscription less than 14 days ago. Deleting the workspace counts as withdrawing from the contract: we cancel the subscription immediately and refund the full amount you paid.")}
                  </div>
                )}
                {billingPending && (
                  <p className="flex items-center gap-2 text-sm text-muted" role="status">
                    <Loader2 size={16} className="animate-spin" />
                    {t("Checking your subscription…")}
                  </p>
                )}
                {billingFailed && !billingPending && (
                  <div className="flex flex-col gap-2 text-sm text-loss bg-loss/10 border border-loss/30 rounded-lg px-4 py-3" role="alert">
                    <span className="flex items-start gap-2">
                      <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                      {t("We could not check your subscription, so we cannot continue yet. Please try again.")}
                    </span>
                    <button
                      type="button"
                      onClick={() => billingQuery.refetch()}
                      className="btn-ghost self-start flex items-center justify-center text-sm font-medium min-h-11 md:min-h-0"
                    >
                      {t("Try again")}
                    </button>
                  </div>
                )}
                {hasLiveSubscription && !withdrawalOpen && (
                  <div className="text-sm text-muted space-y-1">
                    <p>
                      {periodEnd
                        ? t("If you want to use the paid period, cancel the subscription first and delete the workspace after {date}.", { date: periodEnd })
                        : t("If you want to use the paid period, cancel the subscription first and delete the workspace after it has ended.")}
                    </p>
                    <button
                      type="button"
                      onClick={() => portalMutation.mutate()}
                      disabled={portalMutation.isPending}
                      className="btn-ghost flex items-center justify-center gap-2 text-sm font-medium min-h-11 md:min-h-0 disabled:opacity-50"
                    >
                      {portalMutation.isPending && <Loader2 size={16} className="animate-spin" />}
                      {t("Manage subscription")}
                    </button>
                  </div>
                )}
                <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
                  <button
                    ref={warningCancelRef}
                    type="button"
                    onClick={closeDialog}
                    className="btn-ghost flex items-center justify-center text-sm font-medium min-h-11 md:min-h-0"
                  >
                    {hasLiveSubscription ? t("Back – let my subscription run") : t("Cancel")}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setConsent({ live: hasLiveSubscription, refund: withdrawalOpen });
                      setNotice(null);
                      setStep("confirm");
                    }}
                    disabled={secondsLeft > 0 || billingBlocked}
                    className="btn-primary !bg-loss hover:!bg-loss/90 flex items-center justify-center gap-2 min-h-11 md:min-h-0 text-sm disabled:opacity-40"
                  >
                    {secondsLeft > 0
                      ? t("Continue in {seconds} s", { seconds: secondsLeft })
                      : withdrawalOpen ? t("Delete and get a refund")
                        : hasLiveSubscription ? t("Delete anyway") : t("I understand, continue")}
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
        </div>,
        document.body,
      )}
    </div>
  );
}
