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
import { msg, useI18n, useT } from "../i18n/I18nProvider";


// Monthly prices in euro cents, VAT included. In billing mode the backend's
// /billing/status prices win; these cover the no-payment test mode.
const PLANS = [
  {
    id: "free",
    name: "Free",
    icon: Sprout,
    tagline: msg("Track one portfolio and get to know Portfyl."),
    monthly: 0,
    features: [msg("1 portfolio"), msg("15 active positions"), msg("250 transactions"), msg("3 alerts")],
  },
  {
    id: "investor",
    name: "Investor",
    icon: TrendingUp,
    tagline: msg("For long-term investors with several accounts."),
    monthly: 599,
    features: [msg("5 portfolios"), msg("2 broker connections"), msg("Complete analytics"), msg("Daily sync")],
  },
  {
    id: "pro",
    name: "Pro",
    icon: Gem,
    tagline: msg("For active investors who trade options and research deeply."),
    monthly: 999,
    features: [
      msg("15 portfolios"),
      msg("5 broker connections"),
      msg("Advanced options & Polymarket"),
      msg("6-hour sync"),
      msg("Advanced research & custom benchmarks"),
    ],
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


// Spelled-out month names sit inside translated sentences, so they follow the
// app language (numeric formats elsewhere still follow the display currency).
function longDate(iso, language = "en") {
  return new Intl.DateTimeFormat(language, { day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));
}


function PlanCard({ plan, price, isCurrent, badge, action }) {
  const t = useT();
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
      <p className="mt-1 text-sm text-muted md:min-h-[2.5rem]">{t(plan.tagline)}</p>

      <p className="mt-5 flex items-baseline gap-1.5">
        <span className="font-display text-4xl font-extrabold tracking-tight text-ink tnum">{euro(price)}</span>
        <span className="text-sm text-muted">{t("/ month")}</span>
      </p>
      <p className="financial-meta mt-1">{price > 0 ? t("VAT included, billed monthly") : " "}</p>

      <div className="my-5 h-px bg-hairline" aria-hidden="true" />

      <ul className="flex-1 space-y-2.5 text-sm">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2.5">
            <span className="mt-px grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand-light text-brand">
              <Check size={12} strokeWidth={3} aria-hidden="true" />
            </span>
            {t(feature)}
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
  const t = useT();
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
      setAnnouncement(t("{plan} is now active for this workspace.", { plan: plan.name }));
    } catch {
      setError(t("The plan could not be changed. Please try again."));
    } finally {
      setChangingPlan(null);
    }
  };

  return (
    <>
      <Notice icon={FlaskConical} title={t("Free plan switching during private testing")}>
        {t("Choose any plan below. No payment method, checkout, charge, or subscription will be created.")}
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
              badge={isCurrent && <Badge tone="brand">{t("Current test plan")}</Badge>}
              action={(
                <PlanButton
                  primary={isUpgrade}
                  disabled={currentPlan === null || isCurrent || changingPlan !== null}
                  busy={changingPlan === plan.id}
                  current={isCurrent}
                  onClick={() => selectPlan(plan)}
                >
                  {isCurrent ? t("Active for testing") : t("Use {plan} for testing", { plan: plan.name })}
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


function subscriptionSummary(subscription, t, language) {
  if (!subscription) return null;
  const date = (iso) => longDate(iso, language);
  if (subscription.scheduled_plan && subscription.scheduled_change_at) {
    return t("{next} starts on {date}. Until then you keep {current}, with nothing extra to pay now.", {
      next: planName(subscription.scheduled_plan),
      date: date(subscription.scheduled_change_at),
      current: planName(subscription.plan),
    });
  }
  if (subscription.status === "past_due") {
    return subscription.grace_ends_at
      ? t("Your last payment failed. Update your payment method by {date} to keep your plan.", { date: date(subscription.grace_ends_at) })
      : t("Your last payment failed. Update your payment method to keep your plan.");
  }
  if (!subscription.current_period_end) return null;
  return subscription.cancel_at_period_end
    ? t("Cancelled. Your plan stays active until {date}, then the workspace moves to Free.", { date: date(subscription.current_period_end) })
    : t("Renews automatically on {date}.", { date: date(subscription.current_period_end) });
}


function PaidPlans({ status, onStatusChange }) {
  const { t, language } = useI18n();
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
      setError(t("The plan change could not be saved. Please try again."));
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
      setError(t("The payment page could not be opened. Please try again."));
      setRedirecting(null);
    }
  };
  const openPortal = () => goTo("portal", openBillingPortal);
  const checkout = (plan) => goTo(plan.id, () => startCheckout(plan.id));

  const summary = subscriptionSummary(subscription, t, language);

  return (
    <>
      <Notice icon={CreditCard} title={t("Secure payments through Link")}>
        {t("Payments are processed by Link, a Stripe company, as the seller of record. It handles VAT, receipts and payment support. Portfyl never sees your card details. Cancel anytime; you keep your plan until the end of the paid month.")}
      </Notice>

      {subscription && (
        <div className="card flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold">{t("Your subscription: {plan}", { plan: planName(subscription.plan) })}</p>
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
              {t("Manage subscription")}
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
            {t("I want my subscription to start immediately. I understand that once it starts I lose my 14-day right of withdrawal for this digital service.")}
          </span>
        </label>
      )}
      {!canManage && (
        <p className="text-sm text-muted">{t("Only the workspace owner can change the plan or manage billing.")}</p>
      )}

      <ErrorBanner message={error} />

      <div className="grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => {
          const price = plan.id === "free" ? 0 : prices[plan.id] ?? plan.monthly;
          const isCurrent = status.plan === plan.id;
          const isScheduled = subscription?.scheduled_plan === plan.id;
          let action;
          let badge = isCurrent && <Badge tone="brand">{t("Current plan")}</Badge>;
          if (isCurrent && subscription?.scheduled_plan) {
            // A switch is booked: offer to stay on the current plan instead.
            action = (
              <PlanButton disabled={!canManage || busy} busy={changing === plan.id} onClick={() => bookChange(plan)}>
                {t("Keep {plan}", { plan: plan.name })}
              </PlanButton>
            );
          } else if (isCurrent) {
            action = <PlanButton disabled current>{t("Current plan")}</PlanButton>;
          } else if (isScheduled) {
            badge = <Badge tone="neutral">{t("From {date}", { date: longDate(subscription.scheduled_change_at, language) })}</Badge>;
            action = <PlanButton disabled current>{t("Starts next period")}</PlanButton>;
          } else if (subscription && plan.id === "free") {
            // Moving to Free is a cancellation, handled in the Stripe portal.
            action = (
              <PlanButton disabled={!canManage || busy} onClick={openPortal}>{t("Cancel in billing portal")}</PlanButton>
            );
          } else if (subscription?.cancel_at_period_end) {
            // Resume the cancelled subscription in the portal before switching.
            action = (
              <PlanButton disabled={!canManage || busy} onClick={openPortal}>{t("Manage in billing portal")}</PlanButton>
            );
          } else if (subscription) {
            action = (
              <PlanButton disabled={!canManage || busy} busy={changing === plan.id} onClick={() => bookChange(plan)}>
                {subscription.current_period_end
                  ? t("Switch to {plan} from {date}", { plan: plan.name, date: longDate(subscription.current_period_end, language) })
                  : t("Switch to {plan} next period", { plan: plan.name })}
              </PlanButton>
            );
          } else if (plan.id === "free") {
            action = <PlanButton disabled>{t("Included")}</PlanButton>;
          } else {
            action = (
              <PlanButton
                primary
                disabled={!canManage || !consented || busy}
                busy={redirecting === plan.id}
                onClick={() => checkout(plan)}
              >
                {t("Upgrade to {plan}", { plan: plan.name })}
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
  const t = useT();
  return (
    <>
      <Notice icon={FlaskConical} title={t("Local edition: every feature is included")}>
        {t("These are the cloud plans for reference. Nothing here changes this installation.")}
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
  const t = useT();
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
            ? t("Thank you! Your subscription is active.")
            : t("Your payment is being processed. Your plan will switch shortly."),
        );
        queryClient.invalidateQueries({ queryKey: ["plan-capabilities"] });
        return;
      }
      if (!active) return;
      setStatus(current);
      if (outcome === "canceled") setMessage(t("Checkout was cancelled. You have not been charged."));
    };

    load().catch(() => {
      if (active) setError(t("Unable to load your plan."));
    });
    return () => {
      active = false;
    };
    // The messages are set once per load; a language change does not reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient, outcome, sessionId, planSwitching]);

  const billing = status?.billing_enabled;

  return (
    <div className="hover-pop-zone mx-auto max-w-5xl space-y-8 animate-fade-up">
      <header className="space-y-2">
        <p className="eyebrow">{t("Portfyl plans")}</p>
        <h1 className="text-2xl font-bold sm:text-3xl">{t("Plans")}</h1>
        <p className="max-w-2xl text-sm text-muted">
          {!planSwitching
            ? t("Compare the Portfyl cloud tiers.")
            : billing
              ? t("Choose the plan that fits how you invest. Prices include VAT.")
              : t("Compare Portfyl tiers and choose which limits and features to test.")}
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
                ? t("Booked: {plan} starts when your current period ends.", { plan: planName(next.subscription.scheduled_plan) })
                : t("You stay on {plan}.", { plan: planName(next.plan) }),
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
        {t("Variable-cost services remain subject to the displayed fair-use quotas.")}
      </p>
    </div>
  );
}
