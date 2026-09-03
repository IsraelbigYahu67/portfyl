import { useId, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { UserPlus } from "lucide-react";
import { mapFirebaseAuthError, registerWithEmailPassword, sendVerificationEmail } from "../auth/firebase";

const MIN_PASSWORD_LENGTH = 8;

export default function Register() {
  const navigate = useNavigate();
  const emailId = useId();
  const passwordId = useId();
  const confirmId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Choose a password with at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setSubmitting(true);
    try {
      const user = await registerWithEmailPassword(email, password);
      await sendVerificationEmail(user);
      navigate("/verify-email", { state: { email } });
    } catch (err) {
      setError(mapFirebaseAuthError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-bg">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <img src="/portfyl-mark.png" alt="" className="w-12 h-12 object-contain" />
          <h1 className="font-display font-bold text-xl text-ink">Create your account</h1>
          <p className="text-sm text-muted">A personal workspace is created for you automatically.</p>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4" noValidate>
          <div className="space-y-1.5">
            <label htmlFor={emailId} className="eyebrow">E-mail</label>
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
            <label htmlFor={passwordId} className="eyebrow">Password</label>
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
            <label htmlFor={confirmId} className="eyebrow">Confirm password</label>
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

          <button type="submit" className="btn-primary w-full flex items-center justify-center gap-2" disabled={submitting}>
            <UserPlus size={15} />
            {submitting ? "Creating account…" : "Create account"}
          </button>

          <p className="text-xs text-muted text-center pt-1">
            Already have an account?{" "}
            <Link to="/login" className="text-brand hover:underline">
              Log in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
