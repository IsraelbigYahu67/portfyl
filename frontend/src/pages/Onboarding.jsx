import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BarChart3, Link2, Upload, Loader2 } from "lucide-react";

import { createDemoPortfolio, createPortfolio } from "../api";
import { usePlatform, usePortfolio } from "../App";
import { TRACKER_HOME } from "../lib/routes";


function errorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return detail?.message || "We couldn't prepare your portfolio. Please try again.";
}


export default function Onboarding() {
  const navigate = useNavigate();
  const { setCurrentId, refetchPortfolios } = usePortfolio();
  const { setPlatform } = usePlatform();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  async function activate(create, destination, kind) {
    setBusy(kind);
    setError(null);
    try {
      const portfolio = await create();
      setCurrentId(portfolio.id);
      setPlatform("t212");
      await refetchPortfolios();
      navigate(destination);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const choices = [
    {
      key: "import",
      icon: Upload,
      title: "Import a CSV",
      description: "Preview a Trading 212 export or Portfyl CSV before anything is saved.",
      action: () => activate(
        () => createPortfolio({ name: "My portfolio" }),
        "/import",
        "import",
      ),
      primary: true,
    },
    {
      key: "demo",
      icon: BarChart3,
      title: "Explore sample portfolio",
      description: "Use clearly labelled sample data. You can replace or clear it at any time.",
      action: () => activate(createDemoPortfolio, TRACKER_HOME, "demo"),
    },
    {
      key: "broker",
      icon: Link2,
      title: "Connect a broker",
      description: "Create an empty portfolio, then review available connection options.",
      action: () => activate(
        () => createPortfolio({ name: "My portfolio" }),
        "/settings",
        "broker",
      ),
    },
  ];

  return (
    <main className="min-h-screen bg-bg px-6 py-12 flex items-center justify-center">
      <div className="w-full max-w-4xl space-y-8">
        <div className="text-center space-y-3">
          <img src="/portfyl-mark.png" alt="" className="w-14 h-14 object-contain mx-auto" />
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
          {choices.map(({ key, icon: Icon, title, description, action, primary }) => (
            <button
              key={key}
              type="button"
              onClick={action}
              disabled={busy != null}
              className={`card text-left space-y-4 transition-all hover:-translate-y-0.5 hover:border-brand disabled:opacity-60 ${
                primary ? "ring-1 ring-brand/30" : ""
              }`}
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

        <p className="text-center text-xs text-muted">
          Sample data is marked as demo data and never mixed into a real import unless you choose to keep it.
        </p>
      </div>
    </main>
  );
}
