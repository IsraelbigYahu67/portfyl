import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { CircleAlert, KeyRound, Loader2, MailCheck, ShieldCheck } from "lucide-react";
import {
  applyEmailActionCode,
  checkEmailActionCode,
  confirmNewPassword,
  mapFirebaseAuthError,
  verifyResetCode,
} from "../auth/firebase";
import { rich, useT } from "../i18n/I18nProvider";

// Portfyl's own page for the links in Firebase's e-mails (verify e-mail,
// reset password, undo an e-mail change). The Firebase project's action URL
// points here (see "E-mail action links" in deploy/cloudrun.md), so the
// person never sees Firebase's generic page on firebaseapp.com.
//
// Firebase appends ?mode=…&oobCode=…&apiKey=…&continueUrl=…&lang=…. The page
// reads them once, then replaces the address with a clean /auth/action.

const MIN_PASSWORD_LENGTH = 8;

export const AUTH_ACTION_PATH = "/auth/action";

function readActionParams(search) {
  const params = new URLSearchParams(search);
  return {
    mode: params.get("mode"),
    code: params.get("oobCode"),
    continueUrl: params.get("continueUrl"),
  };
}

// Where "Continue" goes after a verified e-mail. Only the continue URL our own
// code set (this origin, or a local dev server) is followed; anything else
// falls back to the login page, so the link cannot send people elsewhere.
export function safeContinueTarget(continueUrl, origin = window.location.origin) {
  const fallback = "/login?verified=1";
  if (!continueUrl) return fallback;
  let url;
  try {
    url = new URL(continueUrl, origin);
  } catch {
    return fallback;
  }
  if (url.origin === origin) return url.pathname + url.search;
  const local = url.protocol === "http:" && (url.hostname === "localhost" || url.hostname === "127.0.0.1");
  return local ? url.href : fallback;
}

function Shell({ icon: Icon, tone = "text-brand", spin = false, title, children }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-bg">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3 text-center">
          <img src="/portfyl-mark.svg" alt="Portfyl" className="w-10 h-10 object-contain" />
          <Icon size={40} className={`${tone}${spin ? " motion-safe:animate-spin" : ""}`} aria-hidden="true" />
          <h1 className="font-display font-bold text-xl text-ink">{title}</h1>
        </div>
        <div className="card space-y-4 text-sm text-ink">{children}</div>
      </div>
    </div>
  );
}

function ContinueButton({ to, children }) {
  if (/^https?:/.test(to)) {
    return (
      <a href={to} className="btn-primary w-full text-center">
        {children}
      </a>
    );
  }
  return (
    <Link to={to} className="btn-primary w-full text-center">
      {children}
    </Link>
  );
}

function BackToLogin() {
  const t = useT();
  return (
    <p className="text-xs text-muted text-center pt-1">
      <Link to="/login" className="text-brand hover:underline">
        {t("Back to login")}
      </Link>
    </p>
  );
}

export default function AuthAction() {
  const t = useT();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useState(() => readActionParams(location.search));
  // working | verified | recovered | reset-form | reset-done | error
  const [status, setStatus] = useState("working");
  const [error, setError] = useState(null);
  const [email, setEmail] = useState(null);
  const started = useRef(false);

  useEffect(() => {
    // The code is single-use, so it runs once even under StrictMode.
    if (started.current) return;
    started.current = true;

    // A clean address bar: the long Firebase query is no longer needed.
    if (location.search) navigate(AUTH_ACTION_PATH, { replace: true });

    const { mode, code } = params;
    const fail = (err) => {
      setError(t(mapFirebaseAuthError(err)));
      setStatus("error");
    };

    if (!code) {
      setError(t("This link is no longer valid. It may have been used already."));
      setStatus("error");
      return;
    }

    if (mode === "verifyEmail") {
      applyEmailActionCode(code).then(() => setStatus("verified"), fail);
    } else if (mode === "resetPassword") {
      verifyResetCode(code).then((address) => {
        setEmail(address);
        setStatus("reset-form");
      }, fail);
    } else if (mode === "recoverEmail") {
      checkEmailActionCode(code)
        .then(async (info) => {
          await applyEmailActionCode(code);
          setEmail(info.email);
          setStatus("recovered");
        })
        .catch(fail);
    } else {
      setError(t("This link is no longer valid. It may have been used already."));
      setStatus("error");
    }
    // Runs once per page load; params never change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (status === "working") {
    return (
      <Shell icon={Loader2} spin title={t("One moment…")}>
        <p role="status" className="text-center text-muted">{t("Checking your link…")}</p>
      </Shell>
    );
  }

  if (status === "verified") {
    return (
      <Shell icon={MailCheck} tone="text-gain" title={t("Your e-mail is verified")}>
        <p>{t("Thanks! Your Portfyl account is ready. If Portfyl is still open in another tab, it continues there by itself.")}</p>
        <ContinueButton to={safeContinueTarget(params.continueUrl)}>{t("Continue to Portfyl")}</ContinueButton>
      </Shell>
    );
  }

  if (status === "recovered") {
    return (
      <Shell icon={ShieldCheck} tone="text-gain" title={t("Your sign-in e-mail is restored")}>
        <p>
          {rich(t("Your account signs in with <b>{email}</b> again. If you didn't ask for the change, reset your password now.", { email: email || "" }), {
            b: (words) => <span className="font-medium">{words}</span>,
          })}
        </p>
        <ContinueButton to="/forgot-password">{t("Reset password")}</ContinueButton>
        <BackToLogin />
      </Shell>
    );
  }

  if (status === "reset-form") {
    return <ResetPasswordForm code={params.code} email={email} onDone={() => setStatus("reset-done")} />;
  }

  if (status === "reset-done") {
    return (
      <Shell icon={ShieldCheck} tone="text-gain" title={t("Password changed")}>
        <p>{t("You can now log in with your new password.")}</p>
        <ContinueButton to="/login">{t("Log in")}</ContinueButton>
      </Shell>
    );
  }

  return (
    <Shell icon={CircleAlert} tone="text-loss" title={t("This link didn't work")}>
      <p role="alert">{error}</p>
      <BackToLogin />
    </Shell>
  );
}

function ResetPasswordForm({ code, email, onDone }) {
  const t = useT();
  const passwordId = useId();
  const confirmId = useId();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(t("Choose a password with at least {min} characters.", { min: MIN_PASSWORD_LENGTH }));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("Passwords don't match."));
      return;
    }
    setSubmitting(true);
    try {
      await confirmNewPassword(code, password);
      onDone();
    } catch (err) {
      setError(t(mapFirebaseAuthError(err)));
      setSubmitting(false);
    }
  }

  return (
    <Shell icon={KeyRound} title={t("Choose a new password")}>
      {email && (
        <p className="text-muted">
          {rich(t("For <b>{email}</b>", { email }), { b: (words) => <span className="font-medium text-ink">{words}</span> })}
        </p>
      )}
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {/* Lets password managers save the new password under the right account. */}
        {email && <input type="email" autoComplete="username" value={email} readOnly hidden />}
        <div className="space-y-1.5">
          <label htmlFor={passwordId} className="eyebrow">{t("New password")}</label>
          <input
            id={passwordId}
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor={confirmId} className="eyebrow">{t("Confirm password")}</label>
          <input
            id={confirmId}
            type="password"
            autoComplete="new-password"
            required
            className="input"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </div>
        {error && (
          <p role="alert" className="text-xs text-loss">
            {error}
          </p>
        )}
        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          {submitting ? t("Saving…") : t("Save new password")}
        </button>
      </form>
      <BackToLogin />
    </Shell>
  );
}
