import { useEffect, useId, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { UserPlus } from "lucide-react";
import {
  isGoogleSignInEnabled,
  mapFirebaseAuthError,
  registerWithEmailPassword,
  sendVerificationEmail,
} from "../auth/firebase";
import AuthMethodDivider from "../components/auth/AuthMethodDivider";
import GoogleSignInButton from "../components/auth/GoogleSignInButton";
import { useAnalytics } from "../analytics/AnalyticsProvider";
import { ANALYTICS_EVENTS } from "../analytics/eventContract";
import { getAnalyticsLanguage } from "../analytics/analyticsCopy";
import { rich, useI18n } from "../i18n/I18nProvider";

const MIN_PASSWORD_LENGTH = 8;

// Strict allowlist: only a literal ?source=demo maps to "demo". Any other
// value (or none) is "direct" -- arbitrary query parameters are never
// forwarded into analytics.
function sourceSurfaceFrom(searchParams) {
  return searchParams.get("source") === "demo" ? "demo" : "direct";
}

export default function Register() {
  const { t, language: appLanguage } = useI18n();
  const navigate = useNavigate();
  const emailId = useId();
  const passwordId = useId();
  const confirmId = useId();
  const [searchParams] = useSearchParams();
  const { capture } = useAnalytics();
  const sourceSurface = sourceSurfaceFrom(searchParams);
  const language = getAnalyticsLanguage();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  // Art. 13 GDPR: the privacy information is given at the moment the data is
  // collected. Registration (password or Google) needs this 18+ and
  // Terms/Privacy confirmation first (privacy review B5).
  const [agreed, setAgreed] = useState(false);
  const agreeId = useId();
  // The legal documents exist in Czech and English only (see the languages
  // plan); other languages get the English text and the link says so.
  const legalLang = appLanguage === "cs" ? "cs" : "en";
  const legalSuffix = appLanguage === "cs" || appLanguage === "en" ? "" : ` ${t("(in English)")}`;

  useEffect(() => {
    capture(ANALYTICS_EVENTS.SIGNUP_STARTED, { source_surface: sourceSurface, language });
    // Fires once per mount of this route -- source_surface/language are
    // fixed for the lifetime of this page view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (!agreed) {
      setError(t("Please confirm that you are 18 or older and accept the Terms of Service and Privacy Policy."));
      return;
    }
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
      const user = await registerWithEmailPassword(email, password);
      await sendVerificationEmail(user);
      // Capture before navigating away, and only once Firebase user
      // creation has actually succeeded. No e-mail or Firebase UID leaves
      // this call -- the schema for signup_completed allows source_surface
      // and auth_method only.
      capture(ANALYTICS_EVENTS.SIGNUP_COMPLETED, { source_surface: sourceSurface, auth_method: "password" });
      navigate("/verify-email", { state: { email } });
    } catch (err) {
      setError(t(mapFirebaseAuthError(err)));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-bg">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <img src="/portfyl-mark.svg" alt="" className="w-12 h-12 object-contain" />
          <h1 className="font-display font-bold text-xl text-ink">{t("Create your Portfyl account")}</h1>
          <p className="text-sm text-muted">
            {t("Track your portfolio, dividends, and taxes in one place.")}
          </p>
        </div>

        <div className="flex items-start gap-2">
          <input
            id={agreeId}
            type="checkbox"
            className="mt-0.5 h-4 w-4 shrink-0"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
          />
          <label htmlFor={agreeId} className="text-xs text-muted">
            {rich(t("I am 18 or older and I accept the <terms>Terms of Service</terms> and have read the <privacy>Privacy Policy</privacy>."), {
              terms: (words) => (
                <a href={`/terms?lang=${legalLang}`} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                  {words}{legalSuffix}
                </a>
              ),
              privacy: (words) => (
                <a href={`/privacy?lang=${legalLang}`} target="_blank" rel="noreferrer" className="text-brand hover:underline">
                  {words}{legalSuffix}
                </a>
              ),
            })}
          </label>
        </div>

        {isGoogleSignInEnabled() && (
          <div className="space-y-4">
            <GoogleSignInButton sourceSurface={sourceSurface} disabled={!agreed} />
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

          <button type="submit" className="btn-primary w-full flex items-center justify-center gap-2" disabled={submitting || !agreed}>
            <UserPlus size={15} />
            {submitting ? t("Creating account…") : t("Create account")}
          </button>

          <p className="text-xs text-muted text-center pt-1">
            {rich(t("Already have an account? <link>Log in</link>"), {
              link: (words) => (
                <Link to="/login" className="text-brand hover:underline">
                  {words}
                </Link>
              ),
            })}
          </p>
        </form>
      </div>
    </div>
  );
}
