import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, FlaskConical, Gem, LoaderCircle, Sprout, TrendingUp } from "lucide-react";

import { fetchTestPlan, updateTestPlan } from "../api";


const PLANS = [
  {
    id: "free",
    name: "Free",
    icon: Sprout,
    tagline: "Track one portfolio and get to know Portfyl.",
    monthly: 0,
    annual: 0,
    features: ["1 portfolio", "15 active positions", "250 transactions", "3 alerts"],
  },
  {
    id: "investor",
    name: "Investor",
    icon: TrendingUp,
    tagline: "For long-term investors with several accounts.",
    monthly: 499,
    annual: 4900,
    features: ["5 portfolios", "2 broker connections", "Complete analytics", "Daily sync"],
  },
  {
    id: "pro",
    name: "Pro",
    icon: Gem,
    tagline: "For active investors who trade options and research deeply.",
    monthly: 799,
    annual: 7900,
    features: ["15 portfolios", "5 broker connections", "Advanced options & Polymarket", "6-hour sync", "Advanced research & custom benchmarks"],
  },
];

const PLAN_ORDER = PLANS.map((plan) => plan.id);


function euro(cents) {
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: cents === 0 ? 0 : 2,
  }).format(cents / 100);
}


function PlanCard({ plan, currentPlan, changingPlan, onSelect }) {
  const Icon = plan.icon;
  const isCurrent = currentPlan === plan.id;
  const isChanging = changingPlan === plan.id;
  const isUpgrade = currentPlan !== null && PLAN_ORDER.indexOf(plan.id) > PLAN_ORDER.indexOf(currentPlan);
  const headingId = `plan-${plan.id}-name`;

  return (
    <section
      aria-labelledby={headingId}
      className={`card flex flex-col p-6 ${isCurrent ? "outline outline-2 outline-offset-4 outline-brand" : ""}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-brand-light text-brand">
          <Icon size={20} aria-hidden="true" />
        </span>
        {isCurrent && (
          <span className="rounded-full bg-brand-light px-3 py-1 text-xs font-semibold text-brand">
            Current test plan
          </span>
        )}
      </div>

      <h2 id={headingId} className="mt-4 text-lg font-bold">{plan.name}</h2>
      <p className="mt-1 text-sm text-muted md:min-h-[2.5rem]">{plan.tagline}</p>

      <p className="mt-5 flex items-baseline gap-1.5">
        <span className="font-display text-4xl font-extrabold tracking-tight text-ink tnum">{euro(plan.monthly)}</span>
        <span className="text-sm text-muted">/ month</span>
      </p>
      {plan.annual > 0 ? (
        <p className="financial-meta mt-1">Planned price: {euro(plan.annual)} annually</p>
      ) : (
        <p className="financial-meta mt-1" aria-hidden="true">&nbsp;</p>
      )}

      <div className="my-5 h-px bg-hairline" aria-hidden="true" />

      <ul className="flex-1 space-y-2.5 text-sm">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2.5">
            <span className="mt-px grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand-light text-brand">
              <Check size={12} strokeWidth={3} aria-hidden="true" />
            </span>
            {feature}
          </li>
        ))}
      </ul>

      <button
        type="button"
        disabled={currentPlan === null || isCurrent || changingPlan !== null}
        onClick={() => onSelect(plan)}
        className={`${isUpgrade ? "btn-primary" : "btn-ghost"} mt-6 flex min-h-11 w-full items-center justify-center gap-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60`}
      >
        {isChanging && <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />}
        {isCurrent && <Check size={16} aria-hidden="true" />}
        {isCurrent ? "Active for testing" : `Use ${plan.name} for testing`}
      </button>
    </section>
  );
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
    <div className="hover-pop-zone mx-auto max-w-5xl space-y-8 animate-fade-up">
      <header className="space-y-2">
        <p className="eyebrow">Portfyl plans</p>
        <h1 className="text-2xl font-bold sm:text-3xl">Plans</h1>
        <p className="max-w-2xl text-sm text-muted">
          Compare Portfyl tiers and choose which limits and features to test.
        </p>
      </header>

      <div className="flex items-start gap-3 rounded-2xl border border-hairline bg-surface-card-elevated px-5 py-4">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-light text-brand">
          <FlaskConical size={17} aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-semibold">Free plan switching during private testing</p>
          <p className="mt-0.5 text-sm text-muted">
            Choose any plan below. No payment method, checkout, charge, or subscription will be created.
          </p>
        </div>
      </div>

      {error && (
        <p role="alert" className="flex items-center gap-2 rounded-2xl border border-loss bg-surface-card px-5 py-3 text-sm font-medium text-loss">
          <AlertTriangle size={16} className="shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}
      <p aria-live="polite" className="sr-only">{announcement}</p>

      <div className="grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => (
          <PlanCard
            key={plan.id}
            plan={plan}
            currentPlan={currentPlan}
            changingPlan={changingPlan}
            onSelect={selectPlan}
          />
        ))}
      </div>

      <p className="financial-meta text-center">
        Displayed prices are previews only. Variable-cost services remain subject to the displayed fair-use quotas.
      </p>
    </div>
  );
}
