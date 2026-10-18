import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, FlaskConical, LoaderCircle } from "lucide-react";

import { fetchTestPlan, updateTestPlan } from "../api";


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
    features: ["5 portfolios", "2 broker connections", "Complete analytics", "Daily sync"],
  },
  {
    id: "pro",
    name: "Pro",
    monthly: 799,
    annual: 7900,
    features: ["15 portfolios", "5 broker connections", "Advanced options & Polymarket", "6-hour sync", "Advanced research & custom benchmarks"],
  },
];


function euro(cents) {
  return new Intl.NumberFormat("en", { style: "currency", currency: "EUR" }).format(cents / 100);
}


export default function Pricing() {
  const queryClient = useQueryClient();
  const [currentPlan, setCurrentPlan] = useState(null);
  const [changingPlan, setChangingPlan] = useState(null);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    let active = true;
    fetchTestPlan()
      .then((result) => {
        if (active) setCurrentPlan(result.plan);
      })
      .catch(() => {
        if (active) setError("Unable to load the current test plan.");
      });
    return () => {
      active = false;
    };
  }, []);

  const selectPlan = async (plan) => {
    setChangingPlan(plan.id);
    setError("");
    setAnnouncement("");
    try {
      const result = await updateTestPlan(plan.id);
      setCurrentPlan(result.plan);
      // The dashboard picks its paid widgets from the plan's capabilities.
      queryClient.invalidateQueries({ queryKey: ["plan-capabilities"] });
      setAnnouncement(`${plan.name} is now active for this workspace.`);
    } catch {
      setError("The plan could not be changed. Please try again.");
    } finally {
      setChangingPlan(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Plans</h1>
        <p className="text-sm text-muted mt-1">
          Compare Portfyl tiers and choose which limits and features to test.
        </p>
      </div>

      <div className="flex gap-3 rounded-xl border border-brand/40 bg-brand/5 px-4 py-3">
        <FlaskConical size={18} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold">Free plan switching during private testing</p>
          <p className="mt-0.5 text-sm text-muted">
            Choose any plan below. No payment method, checkout, charge, or subscription will be created.
          </p>
        </div>
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-loss/40 bg-loss/10 px-4 py-3 text-sm text-loss">
          {error}
        </p>
      )}
      <p aria-live="polite" className="sr-only">{announcement}</p>

      <div className="grid gap-4 md:grid-cols-3">
        {PLANS.map((plan) => {
          const isCurrent = currentPlan === plan.id;
          const isChanging = changingPlan === plan.id;
          return (
            <section
              key={plan.id}
              className={`flex flex-col rounded-xl border bg-surface-card p-5 ${
                isCurrent ? "border-brand ring-1 ring-brand/40" : "border-surface-border"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-lg font-semibold">{plan.name}</h2>
                {isCurrent && (
                  <span className="pt-1 text-xs font-medium text-brand">Current test plan</span>
                )}
              </div>
              <div className="mt-2 text-2xl font-bold">
                {plan.id === "free" ? "€0" : `${euro(plan.monthly)} / month`}
              </div>
              {plan.id !== "free" && (
                <p className="mt-1 text-xs text-muted">Planned price: {euro(plan.annual)} annually</p>
              )}
              <ul className="mt-5 flex-1 space-y-2 text-sm">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex gap-2">
                    <Check size={15} className="mt-0.5 shrink-0 text-gain" aria-hidden="true" />
                    {feature}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                disabled={currentPlan === null || isCurrent || changingPlan !== null}
                onClick={() => selectPlan(plan)}
                className="mt-6 flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand px-3 py-2 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface-card"
              >
                {isChanging && <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />}
                {isCurrent ? "Active for testing" : `Use ${plan.name} for testing`}
              </button>
            </section>
          );
        })}
      </div>

      <p className="text-xs text-muted">
        Displayed prices are previews only. Variable-cost services remain subject to the displayed fair-use quotas.
      </p>
    </div>
  );
}
