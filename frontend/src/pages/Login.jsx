import { useId, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { LogIn } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { TRACKER_HOME } from "../lib/routes";
import {
  getIdToken,
  isGoogleSignInEnabled,
  mapFirebaseAuthError,
  sendVerificationEmail,
  signInWithEmailPassword,
} from "../auth/firebase";
import AuthMethodDivider from "../components/auth/AuthMethodDivider";
import GoogleSignInButton from "../components/auth/GoogleSignInButton";
import { rich, useT } from "../i18n/I18nProvider";

export default function Login() {
  const t = useT();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { loginWithIdToken } = useAuth();
  const emailId = useId();
  const passwordId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [unverifiedUser, setUnverifiedUser] = useState(null);
  const [resendStatus, setResendStatus] = useState("idle"); // idle | sending | sent

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setUnverifiedUser(null);
    setResendStatus("idle");
    setSubmitting(true);
    // Kept outside the try body so the catch branch can still offer a resend
    // action using the just-signed-in Firebase user, if we got that far.
    let firebaseUser = null;
    try {
      firebaseUser = await signInWithEmailPassword(email, password);
      if (!firebaseUser.emailVerified) {
        setUnverifiedUser(firebaseUser);
        return;
      }
      const idToken = await getIdToken(firebaseUser, true);
      await loginWithIdToken(idToken);
      navigate(TRACKER_HOME, { replace: true });
    } catch (err) {
      // The client SDK's emailVerified flag can be stale (cached ID token
      // claims); the backend is the source of truth and re-rejects with this
      // code if verification actually isn't complete yet.
      if (err?.response?.status === 403 && err?.response?.data?.code === "email_verification_required") {
        setUnverifiedUser(firebaseUser || { email });
      } else {
        setError(t(mapFirebaseAuthError(err)));
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResend() {
    if (!unverifiedUser?.getIdToken && !unverifiedUser?.email) return;
    setResendStatus("sending");
    try {
      if (unverifiedUser.getIdToken) {
        await sendVerificationEmail(unverifiedUser);
      }
      setResendStatus("sent");
    } catch {
      setResendStatus("idle");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-bg">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <img src="/portfyl-mark.svg" alt="" className="w-12 h-12 object-contain" />
          <h1 className="font-display font-bold text-xl text-ink">{t("Log in to Portfyl")}</h1>
          <p className="text-sm text-muted">{t("Track your portfolio, dividends, and taxes in one place.")}</p>
        </div>

        {searchParams.get("verified") === "1" && (
          <p role="status" className="text-sm text-gain text-center">
            {t("E-mail verified. Log in to continue.")}
          </p>
        )}

        {isGoogleSignInEnabled() && (
          <div className="space-y-4">
            <GoogleSignInButton />
            <AuthMethodDivider />
          </div>
        )}

        <form onSubmit={handleSubmit} className="card space-y-4" noValidate>
          <div className="space-y-1.5">
            <label htmlFor={emailId} className="eyebrow">{t("E-mail")}</label>
            <input
              id={emailId}
              type="email"
              autoComplete="email"
              required
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor={passwordId} className="eyebrow">{t("Password")}</label>
            <input
              id={passwordId}
              type="password"
              autoComplete="current-password"
              required
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {unverifiedUser && (
            <div role="status" className="text-xs text-ink bg-surface-hover rounded-lg p-3 space-y-2">
              <p>
                {rich(
                  t("Please verify your e-mail before logging in — we sent a verification link to <b>{email}</b>. Check your inbox (and spam folder).", { email: unverifiedUser.email || email }),
                  { b: (words) => <span className="font-medium">{words}</span> },
                )}
              </p>
              {unverifiedUser.getIdToken && (
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={resendStatus === "sending"}
                  className="text-brand font-medium hover:underline disabled:opacity-50"
                >
                  {resendStatus === "sent"
                    ? t("Verification e-mail sent")
                    : resendStatus === "sending"
                    ? t("Sending…")
                    : t("Resend verification e-mail")}
                </button>
              )}
            </div>
          )}

          {error && (
            <p role="alert" className="text-xs text-loss">
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary w-full flex items-center justify-center gap-2" disabled={submitting}>
            <LogIn size={15} />
            {submitting ? t("Logging in…") : t("Log in")}
          </button>

          <div className="flex items-center justify-between text-xs pt-1">
            <Link to="/forgot-password" className="text-muted hover:text-brand">
              {t("Forgot password?")}
            </Link>
            <Link to="/register" className="text-muted hover:text-brand">
              {t("Create an account")}
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
