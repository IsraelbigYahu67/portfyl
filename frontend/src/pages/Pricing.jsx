import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, CreditCard, FlaskConical, Gem, LoaderCircle, Sprout, TrendingUp } from "lucide-react";

import {
  changePlan,
  confirmCheckout,
  fetchBillingStatus,
  fetchTestPlan,
  openBillingPortal,
  startCheckout,
  updateTestPlan,
} from "../api";
import { Badge } from "../components/ui/Badge";


// Monthly prices in euro cents, VAT included. In billing mode the backend's
// /billing/status prices win; these cover the no-payment test mode.
const PLANS = [
  {
    id: "free",
    name: "Free",
    icon: Sprout,
    tagline: "Track one portfolio and get to know Portfyl.",
    monthly: 0,
    features: ["1 portfolio", "15 active positions", "250 transactions", "3 alerts"],
  },
  {
    id: "investor",
    name: "Investor",
    icon: TrendingUp,
    tagline: "For long-term investors with several accounts.",
    monthly: 599,
    features: ["5 portfolios", "2 broker connections", "Complete analytics", "Daily sync"],
  },
  {
    id: "pro",
    name: "Pro",
    icon: Gem,
    tagline: "For active investors who trade options and research deeply.",
    monthly: 999,
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


function longDate(iso) {
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));
}


function PlanCard({ plan, price, isCurrent, badge, action }) {
  const Icon = plan.icon;
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
        {badge}
      </div>

      <h2 id={headingId} className="mt-4 text-lg font-bold">{plan.name}</h2>
      <p className="mt-1 text-sm text-muted md:min-h-[2.5rem]">{plan.tagline}</p>

      <p className="mt-5 flex items-baseline gap-1.5">
        <span className="font-display text-4xl font-extrabold tracking-tight text-ink tnum">{euro(price)}</span>
        <span className="text-sm text-muted">/ month</span>
      </p>
      <p className="financial-meta mt-1">{price > 0 ? "VAT included, billed monthly" : " "}</p>

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

      {action}
    </section>
  );
}


function PlanButton({ primary, disabled, busy, current, onClick, children }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`${primary ? "btn-primary" : "btn-ghost"} mt-6 flex min-h-11 w-full items-center justify-center gap-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60`}
    >
      {busy && <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />}
      {current && <Check size={16} aria-hidden="true" />}
      {children}
    </button>
  );
}


function Notice({ icon: Icon, title, children }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-hairline bg-surface-card-elevated px-5 py-4">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-light text-brand">
        <Icon size={17} aria-hidden="true" />
      </span>
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <div className="mt-0.5 text-sm text-muted">{children}</div>
      </div>
    </div>
  );
}


function ErrorBanner({ message }) {
  if (!message) return null;
  return (
    <p role="alert" className="flex items-center gap-2 rounded-2xl border border-loss bg-surface-card px-5 py-3 text-sm font-medium text-loss">
      <AlertTriangle size={16} className="shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}


function TestPlans({ currentPlan, onPlanChanged }) {
  const [changingPlan, setChangingPlan] = useState(null);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");

  const selectPlan = async (plan) => {
    setChangingPlan(plan.id);
    setError("");
    setAnnouncement("");
    try {
      const result = await updateTestPlan(plan.id);
      onPlanChanged(result.plan);
      setAnnouncement(`${plan.name} is now active for this workspace.`);
    } catch {
      setError("The plan could not be changed. Please try again.");
    } finally {
      setChangingPlan(null);
    }
  };

  return (
    <>
      <Notice icon={FlaskConical} title="Free plan switching during private testing">
        Choose any plan below. No payment method, checkout, charge, or subscription will be created.
      </Notice>
      <ErrorBanner message={error} />
      <p aria-live="polite" className="sr-only">{announcement}</p>
      <div className="grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => {
          const isCurrent = currentPlan === plan.id;
          const isUpgrade = currentPlan !== null && PLAN_ORDER.indexOf(plan.id) > PLAN_ORDER.indexOf(currentPlan);
          return (
            <PlanCard
              key={plan.id}
              plan={plan}
              price={plan.monthly}
              isCurrent={isCurrent}
              badge={isCurrent && <Badge tone="brand">Current test plan</Badge>}
              action={(
                <PlanButton
                  primary={isUpgrade}
                  disabled={currentPlan === null || isCurrent || changingPlan !== null}
                  busy={changingPlan === plan.id}
                  current={isCurrent}
                  onClick={() => selectPlan(plan)}
                >
                  {isCurrent ? "Active for testing" : `Use ${plan.name} for testing`}
                </PlanButton>
              )}
            />
          );
        })}
      </div>
    </>
  );
}


function planName(id) {
  return PLANS.find((plan) => plan.id === id)?.name ?? id;
}


function subscriptionSummary(subscription) {
  if (!subscription) return null;
  if (subscription.scheduled_plan && subscription.scheduled_change_at) {
    return `${planName(subscription.scheduled_plan)} starts on ${longDate(subscription.scheduled_change_at)}. `
      + `Until then you keep ${planName(subscription.plan)}, with nothing extra to pay now.`;
  }
  if (subscription.status === "past_due") {
    return subscription.grace_ends_at
      ? `Your last payment failed. Update your payment method by ${longDate(subscription.grace_ends_at)} to keep your plan.`
      : "Your last payment failed. Update your payment method to keep your plan.";
  }
  if (!subscription.current_period_end) return null;
  return subscription.cancel_at_period_end
    ? `Cancelled. Your plan stays active until ${longDate(subscription.current_period_end)}, then the workspace moves to Free.`
    : `Renews automatically on ${longDate(subscription.current_period_end)}.`;
}


function PaidPlans({ status, onStatusChange }) {
  const [consented, setConsented] = useState(false);
  const [redirecting, setRedirecting] = useState(null);
  const [changing, setChanging] = useState(null);
  const [error, setError] = useState("");

  const subscription = status.subscription;
  const canManage = status.can_manage_billing;
  const prices = status.prices?.monthly_cents ?? {};
  const busy = redirecting !== null || changing !== null;

  const bookChange = async (plan) => {
    setChanging(plan.id);
    setError("");
    try {
      onStatusChange(await changePlan(plan.id));
    } catch {
      setError("The plan change could not be saved. Please try again.");
    } finally {
      setChanging(null);
    }
  };

  const goTo = async (target, request) => {
    setRedirecting(target);
    setError("");
    try {
      const { url } = await request();
      window.location.assign(url);
    } catch {
      setError("The payment page could not be opened. Please try again.");
      setRedirecting(null);
    }
  };
  const openPortal = () => goTo("portal", openBillingPortal);
  const checkout = (plan) => goTo(plan.id, () => startCheckout(plan.id));

  const summary = subscriptionSummary(subscription);

  return (
    <>
      <Notice icon={CreditCard} title="Secure payments through Link">
        Payments are processed by Link, a Stripe company, as the seller of record. It handles VAT, receipts and
        payment support. Portfyl never sees your card details. Cancel anytime; you keep your plan until the end of
        the paid month.
      </Notice>

      {subscription && (
        <div className="card flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold">Your subscription: {planName(subscription.plan)}</p>
            {summary && <p className="mt-0.5 text-sm text-muted">{summary}</p>}
          </div>
          {canManage && (
            <button
              type="button"
              onClick={openPortal}
              disabled={busy}
              className="btn-ghost flex min-h-11 shrink-0 items-center justify-center gap-2 px-5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
            >
              {redirecting === "portal" && <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />}
              Manage subscription
            </button>
          )}
        </div>
      )}

      {!subscription && canManage && (
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={consented}
            onChange={(event) => setConsented(event.target.checked)}
            className="mt-0.5 h-4 w-4 accent-brand"
          />
          <span className="text-sm">
            I want my subscription to start immediately. I understand that once it starts I lose my 14-day right of
            withdrawal for this digital service.
          </span>
        </label>
      )}
      {!canManage && (
        <p className="text-sm text-muted">Only the workspace owner can change the plan or manage billing.</p>
      )}

      <ErrorBanner message={error} />

      <div className="grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => {
          const price = plan.id === "free" ? 0 : prices[plan.id] ?? plan.monthly;
          const isCurrent = status.plan === plan.id;
          const isScheduled = subscription?.scheduled_plan === plan.id;
          let action;
          let badge = isCurrent && <Badge tone="brand">Current plan</Badge>;
          if (isCurrent && subscription?.scheduled_plan) {
            // A switch is booked: offer to stay on the current plan instead.
            action = (
              <PlanButton disabled={!canManage || busy} busy={changing === plan.id} onClick={() => bookChange(plan)}>
                {`Keep ${plan.name}`}
              </PlanButton>
            );
          } else if (isCurrent) {
            action = <PlanButton disabled current>Current plan</PlanButton>;
          } else if (isScheduled) {
            badge = <Badge tone="neutral">From {longDate(subscription.scheduled_change_at)}</Badge>;
            action = <PlanButton disabled current>Starts next period</PlanButton>;
          } else if (subscription && plan.id === "free") {
            // Moving to Free is a cancellation, handled in the Stripe portal.
            action = (
              <PlanButton disabled={!canManage || busy} onClick={openPortal}>Cancel in billing portal</PlanButton>
            );
          } else if (subscription?.cancel_at_period_end) {
            // Resume the cancelled subscription in the portal before switching.
            action = (
              <PlanButton disabled={!canManage || busy} onClick={openPortal}>Manage in billing portal</PlanButton>
            );
          } else if (subscription) {
            action = (
              <PlanButton disabled={!canManage || busy} busy={changing === plan.id} onClick={() => bookChange(plan)}>
                {subscription.current_period_end
                  ? `Switch to ${plan.name} from ${longDate(subscription.current_period_end)}`
                  : `Switch to ${plan.name} next period`}
              </PlanButton>
            );
          } else if (plan.id === "free") {
            action = <PlanButton disabled>Included</PlanButton>;
          } else {
            action = (
              <PlanButton
                primary
                disabled={!canManage || !consented || busy}
                busy={redirecting === plan.id}
                onClick={() => checkout(plan)}
              >
                {`Upgrade to ${plan.name}`}
              </PlanButton>
            );
          }
          return (
            <PlanCard
              key={plan.id}
              plan={plan}
              price={price}
              isCurrent={isCurrent}
              badge={badge}
              action={action}
            />
          );
        })}
      </div>
    </>
  );
}


function ReferencePlans() {
  return (
    <>
      <Notice icon={FlaskConical} title="Local edition: every feature is included">
        These are the cloud plans for reference. Nothing here changes this installation.
      </Notice>
      <div className="grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => (
          <PlanCard key={plan.id} plan={plan} price={plan.monthly} isCurrent={false} />
        ))}
      </div>
    </>
  );
}


function checkoutReturn() {
  const params = new URLSearchParams(window.location.search);
  return { outcome: params.get("checkout"), sessionId: params.get("session_id") };
}


// The local edition has no plans (it always resolves to Pro) and no billing or
// /api/test-plans routes, so it renders the catalogue read-only.
export default function Pricing({ planSwitching = true }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState(null);
  const [testPlan, setTestPlan] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  // Read once per mount: the effect below strips the Stripe return
  // parameters from the URL, and a re-run (React StrictMode) must still see them.
  const [{ outcome, sessionId }] = useState(checkoutReturn);

  useEffect(() => {
    if (!planSwitching) return undefined;
    let active = true;
    if (outcome) {
      // Drop the Stripe return parameters so a reload does not repeat them.
      window.history.replaceState(null, "", window.location.pathname);
    }

    const load = async () => {
      const current = await fetchBillingStatus();
      if (!current.billing_enabled) {
        const selection = await fetchTestPlan();
        if (active) setTestPlan(selection.plan);
      }
      if (outcome === "success" && sessionId && current.billing_enabled) {
        const confirmed = await confirmCheckout(sessionId);
        if (!active) return;
        setStatus(confirmed);
        setMessage(
          confirmed.checkout_status === "complete"
            ? "Thank you! Your subscription is active."
            : "Your payment is being processed. Your plan will switch shortly.",
        );
        queryClient.invalidateQueries({ queryKey: ["plan-capabilities"] });
        return;
      }
      if (!active) return;
      setStatus(current);
      if (outcome === "canceled") setMessage("Checkout was cancelled. You have not been charged.");
    };

    load().catch(() => {
      if (active) setError("Unable to load your plan.");
    });
    return () => {
      active = false;
    };
  }, [queryClient, outcome, sessionId, planSwitching]);

  const billing = status?.billing_enabled;

  return (
    <div className="hover-pop-zone mx-auto max-w-5xl space-y-8 animate-fade-up">
      <header className="space-y-2">
        <p className="eyebrow">Portfyl plans</p>
        <h1 className="text-2xl font-bold sm:text-3xl">Plans</h1>
        <p className="max-w-2xl text-sm text-muted">
          {!planSwitching
            ? "Compare the Portfyl cloud tiers."
            : billing
              ? "Choose the plan that fits how you invest. Prices include VAT."
              : "Compare Portfyl tiers and choose which limits and features to test."}
        </p>
      </header>

      {!planSwitching && <ReferencePlans />}

      <ErrorBanner message={error} />
      {message && (
        <p role="status" className="rounded-2xl border border-hairline bg-surface-card px-5 py-3 text-sm font-medium">
          {message}
        </p>
      )}

      {status && billing && (
        <PaidPlans
          status={status}
          onStatusChange={(next) => {
            setStatus(next);
            setMessage(
              next.subscription?.scheduled_plan
                ? `Booked: ${planName(next.subscription.scheduled_plan)} starts when your current period ends.`
                : `You stay on ${planName(next.plan)}.`,
            );
          }}
        />
      )}
      {status && !billing && (
        <TestPlans
          currentPlan={testPlan}
          onPlanChanged={(plan) => {
            setTestPlan(plan);
            // The dashboard picks its paid widgets from the plan's capabilities.
            queryClient.invalidateQueries({ queryKey: ["plan-capabilities"] });
          }}
        />
      )}

      <p className="financial-meta text-center">
        Variable-cost services remain subject to the displayed fair-use quotas.
      </p>
    </div>
  );
}
