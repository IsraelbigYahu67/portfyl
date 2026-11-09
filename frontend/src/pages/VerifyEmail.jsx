import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { MailCheck } from "lucide-react";
import { getCurrentFirebaseUser, mapFirebaseAuthError, sendVerificationEmail } from "../auth/firebase";
import { rich, useT } from "../i18n/I18nProvider";

export default function VerifyEmail() {
  const t = useT();
  const location = useLocation();
  const emailHint = location.state?.email || null;
  const [status, setStatus] = useState("idle"); // idle | sending | sent
  const [error, setError] = useState(null);

  // In-memory Firebase persistence keeps the just-registered/just-signed-in
  // user available for the lifetime of this tab, so a resend usually doesn't
  // need the visitor to sign in again — but a hard refresh drops it, and
  // that's a real, expected case to handle gracefully.
  const currentUser = getCurrentFirebaseUser();

  async function handleResend() {
    if (!currentUser) return;
    setStatus("sending");
    setError(null);
    try {
      await sendVerificationEmail(currentUser);
      setStatus("sent");
    } catch (err) {
      setError(t(mapFirebaseAuthError(err)));
      setStatus("idle");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-bg">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <MailCheck size={40} className="text-brand" aria-hidden="true" />
          <h1 className="font-display font-bold text-xl text-ink">{t("Verify your e-mail")}</h1>
        </div>

        <div className="card space-y-4 text-sm text-ink">
          <p>
            {emailHint
              ? rich(t("We sent a verification link to <b>{email}</b>. Click the link, then come back and log in.", { email: emailHint }), {
                  b: (words) => <span className="font-medium">{words}</span>,
                })
              : t("We sent a verification link to your e-mail address. Click the link, then come back and log in.")}
          </p>

          {currentUser ? (
            <button
              type="button"
              onClick={handleResend}
              disabled={status === "sending"}
              className="btn-primary w-full"
            >
              {status === "sent" ? t("Verification e-mail sent") : status === "sending" ? t("Sending…") : t("Resend verification e-mail")}
            </button>
          ) : (
            <p className="text-xs text-muted">
              {t("Sign in again to resend the verification e-mail.")}
            </p>
          )}

          {status === "sent" && (
            <p role="status" className="text-xs text-gain">
              {t("Check your inbox (and spam folder).")}
            </p>
          )}
          {error && (
            <p role="alert" className="text-xs text-loss">
              {error}
            </p>
          )}

          <p className="text-xs text-muted text-center pt-1">
            <Link to="/login" className="text-brand hover:underline">
              {t("Back to login")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
