// The "or" rule between alternative ways to prove identity (Google vs.
// e-mail and password). Purely decorative, so it is hidden from assistive tech.
export default function AuthMethodDivider() {
  return (
    <div className="flex items-center gap-3 text-xs text-muted" aria-hidden="true">
      <span className="h-px flex-1 bg-hairline" />
      or
      <span className="h-px flex-1 bg-hairline" />
    </div>
  );
}
