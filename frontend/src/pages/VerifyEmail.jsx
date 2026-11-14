import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { MailCheck } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import {
  getCurrentFirebaseUser,
  getIdToken,
  mapFirebaseAuthError,
  reloadFirebaseUser,
  sendVerificationEmail,
} from "../auth/firebase";
import { rich, useT } from "../i18n/I18nProvider";
import { TRACKER_HOME } from "../lib/routes";

// Ask Firebase every 4 s whether the link was clicked, for at most 15 minutes.
const VERIFY_POLL_MS = 4000;
const VERIFY_POLL_LIMIT = 225;

export default function VerifyEmail() {
  const t = useT();
  const location = useLocation();
  const navigate = useNavigate();
  const { loginWithIdToken } = useAuth();
  const emailHint = location.state?.email || null;
  const [status, setStatus] = useState("idle"); // idle | sending | sent
  const [error, setError] = useState(null);

  // In-memory Firebase persistence keeps the just-registered/just-signed-in
  // user available for the lifetime of this tab, so a resend usually doesn't
  // need the visitor to sign in again — but a hard refresh drops it, and
  // that's a real, expected case to handle gracefully.
  const [currentUser] = useState(() => getCurrentFirebaseUser());

  // The latest callbacks, so the polling effect below starts once per user.
  const continueRef = useRef(null);
  continueRef.current = async (user) => {
    const idToken = await getIdToken(user, true);
    await loginWithIdToken(idToken);
    navigate(TRACKER_HOME, { replace: true });
  };
  const failRef = useRef(null);
  failRef.current = (err) => setError(t(mapFirebaseAuthError(err)));

  // Once the link is clicked (in this or another tab or device), exchange the
  // now-verified Firebase user for a Portfyl session and continue by itself.
  // With no in-memory user (e.g. after a refresh) there is nothing to poll.
  useEffect(() => {
    if (!currentUser) return undefined;
    let active = true;
    let exchanging = false;
    let busy = false;
    let polls = 0;
    let timer = null;

    function stopPolling() {
      clearInterval(timer);
      window.removeEventListener("focus", check);
    }

    async function check() {
      if (!active || busy) return;
      busy = true;
      try {
        const verified = await reloadFirebaseUser(currentUser);
        if (!active || !verified) return;
        exchanging = true;
        stopPolling();
        await continueRef.current(currentUser);
      } catch (err) {
        // A failed reload is transient (network): keep polling. A failed
        // exchange happens after polling stopped and is shown to the person.
        if (exchanging && active) failRef.current(err);
      } finally {
        busy = false;
      }
    }

    timer = setInterval(() => {
      polls += 1;
      check();
      if (polls >= VERIFY_POLL_LIMIT) stopPolling();
    }, VERIFY_POLL_MS);
    window.addEventListener("focus", check);

    return () => {
      active = false;
      stopPolling();
    };
  }, [currentUser]);

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
            {currentUser
              ? rich(t("We sent a verification link to <b>{email}</b>. Click it and this page continues by itself.", { email: currentUser.email || emailHint || "" }), {
                  b: (words) => <span className="font-medium">{words}</span>,
                })
              : emailHint
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
