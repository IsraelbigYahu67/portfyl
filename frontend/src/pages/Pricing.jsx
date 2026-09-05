import { useEffect, useRef, useState } from "react";
import { Check, Clock3, X } from "lucide-react";


const PLANS = [
  {
    id: "free",
    name: "Free",
    monthly: 0,
    annual: 0,
    features: ["1 portfolio", "15 active positions", "250 transactions", "3 alerts"],
  },
  {
    id: "investor",
    name: "Investor",
    monthly: 499,
    annual: 4900,
    features: ["5 portfolios", "2 broker connections", "Complete analytics", "Daily sync", "BYOK AI"],
  },
  {
    id: "pro",
    name: "Pro",
    monthly: 799,
    annual: 7900,
    features: ["15 portfolios", "5 broker connections", "Advanced options & Polymarket", "6-hour sync", "100 hosted AI messages/month"],
  },
];


function euro(cents) {
  return new Intl.NumberFormat("en", { style: "currency", currency: "EUR" }).format(cents / 100);
}


export default function Pricing() {
  const [selected, setSelected] = useState(null);
  const closeButtonRef = useRef(null);
  const dialogRef = useRef(null);
  const invokerRef = useRef(null);

  const closeDialog = () => setSelected(null);

  const openDialog = (plan, interval, event) => {
    invokerRef.current = event.currentTarget;
    setSelected({ plan, interval });
  };

  useEffect(() => {
    if (!selected) {
      invokerRef.current?.focus();
      invokerRef.current = null;
      return undefined;
    }

    closeButtonRef.current?.focus();
    const keepFocusInDialog = (event) => {
      if (event.key === "Escape") {
        closeDialog();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = dialogRef.current?.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", keepFocusInDialog);
    return () => window.removeEventListener("keydown", keepFocusInDialog);
  }, [selected]);

  return (
    <>
    <div
      className="max-w-5xl mx-auto space-y-6"
      aria-hidden={selected ? "true" : undefined}
      inert={selected ? "" : undefined}
    >
      <div>
        <h1 className="text-2xl font-bold">Plans</h1>
        <p className="text-sm text-muted mt-1">
          Compare the planned Portfyl tiers. Prices include the listed product access; applicable taxes may vary.
        </p>
      </div>

      <div className="flex gap-3 rounded-xl border border-brand/40 bg-brand/5 px-4 py-3">
        <Clock3 size={18} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold">Paid plans are coming soon</p>
          <p className="mt-0.5 text-sm text-muted">
            Payments are not active yet. All cloud workspaces currently use the Free plan.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {PLANS.map((plan) => (
          <section
            key={plan.id}
            className="flex flex-col rounded-xl border border-surface-border bg-surface-card p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold">{plan.name}</h2>
              {plan.id === "free" && (
                <span className="rounded-full border border-gain/30 bg-gain/10 px-2.5 py-1 text-xs font-semibold text-gain">
                  Current plan
                </span>
              )}
            </div>
            <div className="mt-2 text-2xl font-bold">
              {plan.id === "free" ? "€0" : `${euro(plan.monthly)} / month`}
            </div>
            {plan.id !== "free" && (
              <p className="mt-1 text-xs text-muted">or {euro(plan.annual)} annually</p>
            )}
            <ul className="mt-5 flex-1 space-y-2 text-sm">
              {plan.features.map((feature) => (
                <li key={feature} className="flex gap-2">
                  <Check size={15} className="mt-0.5 shrink-0 text-gain" aria-hidden="true" />
                  {feature}
                </li>
              ))}
            </ul>
            {plan.id !== "free" && (
              <div className="mt-6 grid grid-cols-2 gap-2">
                {[
                  ["month", "Monthly"],
                  ["year", "Annual"],
                ].map(([interval, label]) => (
                  <button
                    key={interval}
                    type="button"
                    aria-label={`${plan.name} ${label.toLowerCase()} — coming soon`}
                    onClick={(event) => openDialog(plan.name, label.toLowerCase(), event)}
                    className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm font-semibold text-text-primary hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    {label}
                    <span className="block text-[10px] font-medium text-muted">Coming soon</span>
                  </button>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>

      <p className="text-xs text-muted">
        Variable-cost services are subject to the displayed fair-use quotas.
      </p>

    </div>

      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeDialog();
          }}
        >
          <section
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="payments-coming-soon-title"
            className="w-full max-w-md rounded-2xl border border-surface-border bg-surface-card p-6 shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id="payments-coming-soon-title" className="text-xl font-semibold">
                  Payments are coming soon
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted">
                  Payments are not available yet. The {selected.plan} {selected.interval} plan is shown for comparison only, and no payment was attempted.
                </p>
              </div>
              <button
                ref={closeButtonRef}
                type="button"
                aria-label="Close"
                onClick={closeDialog}
                className="rounded-lg p-2 text-muted hover:bg-white/5 hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <button
              type="button"
              onClick={closeDialog}
              className="mt-6 w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-card"
            >
              Got it
            </button>
          </section>
        </div>
      )}
    </>
  );
}
