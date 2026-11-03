import { BarChart3, Link2, Upload, Loader2 } from "lucide-react";

// Pure presentation of the first-run onboarding screen. It deliberately
// imports nothing from ../../api or analytics: the real Onboarding page wires
// the actions to the server, and OnboardingPreview reuses this exact view with
// local-only actions so signed-in users can walk through it again safely.

export const ONBOARDING_CHOICES = Object.freeze([
  {
    key: "import",
    icon: Upload,
    title: "Import a CSV",
    description: "Preview a Trading 212 export or Portfyl CSV before anything is saved.",
    primary: true,
  },
  {
    key: "demo",
    icon: BarChart3,
    title: "Explore sample portfolio",
    description: "Use clearly labelled sample data. You can replace or clear it at any time.",
  },
  {
    key: "broker",
    icon: Link2,
    title: "Connect a broker",
    description: "Create an empty portfolio, then review available connection options.",
  },
]);

export default function OnboardingView({
  onChoose,
  onStartBlank,
  busy = null,
  error = null,
  banner = null,
  notice = null,
  selected = null,
}) {
  return (
    <main className="min-h-screen bg-bg px-6 py-12 flex items-center justify-center">
      <div className="w-full max-w-4xl space-y-8">
        {banner}

        <div className="text-center space-y-3">
          <img src="/portfyl-mark.svg" alt="" className="w-14 h-14 object-contain mx-auto" />
          <p className="eyebrow text-brand">Your workspace is ready</p>
          <h1 className="font-display text-3xl font-bold text-ink">Add your first portfolio</h1>
          <p className="text-sm text-muted max-w-xl mx-auto">
            Start with real data or look around safely. Import remains available on every plan.
          </p>
        </div>

        {error && (
          <div role="alert" className="card border border-red-500/40 bg-loss/10 text-sm text-loss">
            {error}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-3">
          {ONBOARDING_CHOICES.map(({ key, icon: Icon, title, description, primary }) => (
            <button
              key={key}
              type="button"
              onClick={() => onChoose(key)}
              disabled={busy != null}
              className={`card text-left space-y-4 transition-all hover:-translate-y-0.5 hover:border-brand disabled:opacity-60 ${
                primary ? "ring-1 ring-brand/30" : ""
              } ${selected === key ? "border-brand" : ""}`}
              aria-label={title}
            >
              <span className="w-10 h-10 rounded-xl bg-brand/10 text-brand flex items-center justify-center">
                {busy === key ? <Loader2 size={20} className="animate-spin" /> : <Icon size={20} />}
              </span>
              <span className="block space-y-1.5">
                <span className="block font-semibold text-ink">{title}</span>
                <span className="block text-xs leading-5 text-muted">{description}</span>
              </span>
            </button>
          ))}
        </div>

        {notice}

        <p className="text-center text-xs text-muted">
          Sample data is marked as demo data and never mixed into a real import unless you choose to keep it.
        </p>
        <div className="text-center">
          <button type="button" onClick={onStartBlank} disabled={busy != null} className="text-sm font-medium text-muted underline-offset-4 hover:text-ink hover:underline disabled:opacity-50">
            {busy === "blank" ? "Preparing blank portfolio…" : "Start with a blank portfolio"}
          </button>
        </div>
      </div>
    </main>
  );
}
