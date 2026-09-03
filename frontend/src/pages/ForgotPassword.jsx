import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { KeyRound } from "lucide-react";
import { sendPasswordReset } from "../auth/firebase";

export default function ForgotPassword() {
  const emailId = useId();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await sendPasswordReset(email);
    } catch {
      // Deliberately swallowed: the response must never reveal whether an
      // account exists for this address (anti user-enumeration — see the
      // multiuser foundation design spec's forgot-password requirement).
    } finally {
      setSubmitting(false);
      setSubmitted(true);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-bg">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <KeyRound size={36} className="text-brand" aria-hidden="true" />
          <h1 className="font-display font-bold text-xl text-ink">Reset your password</h1>
          <p className="text-sm text-muted">We'll e-mail you a link to choose a new one.</p>
        </div>

        <div className="card space-y-4">
          {submitted ? (
            <p role="status" className="text-sm text-ink">
              If an account exists for that e-mail, we've sent a link to reset your password. Check your
              inbox (and spam folder).
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
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
              <button type="submit" className="btn-primary w-full" disabled={submitting}>
                {submitting ? "Sending…" : "Send reset link"}
              </button>
            </form>
          )}

          <p className="text-xs text-muted text-center pt-1">
            <Link to="/login" className="text-brand hover:underline">
              Back to login
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
