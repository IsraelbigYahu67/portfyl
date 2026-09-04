import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, CreditCard, Loader2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import {
  createBillingPortal,
  createCheckout,
  fetchBillingPrices,
  fetchEntitlements,
} from "../api";

const FEATURES = {
  free: ["1 portfolio", "15 active positions", "250 transactions", "3 alerts"],
  investor: ["5 portfolios", "2 broker connections", "Complete analytics", "Daily sync", "BYOK AI"],
  pro: ["15 portfolios", "5 broker connections", "Advanced options & Polymarket", "6-hour sync", "100 hosted AI messages/month"],
};

function euro(cents) {
  return new Intl.NumberFormat("en", { style: "currency", currency: "EUR" }).format(cents / 100);
}

export default function Pricing() {
  const [searchParams] = useSearchParams();
  const awaitingProjection = searchParams.get("billing") === "success";
  const { data: priceData } = useQuery({ queryKey: ["billing-prices"], queryFn: fetchBillingPrices });
  const { data: access, isLoading } = useQuery({
    queryKey: ["entitlements"],
    queryFn: fetchEntitlements,
    refetchInterval: (query) => (
      awaitingProjection && query.state.data?.source !== "subscription" ? 2000 : false
    ),
  });
  const checkout = useMutation({
    mutationFn: ({ plan, interval }) => createCheckout(plan, interval),
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const portal = useMutation({
    mutationFn: createBillingPortal,
    onSuccess: ({ url }) => window.location.assign(url),
  });

  const prices = new Map(
    (priceData?.prices || []).map((item) => [`${item.plan}:${item.interval}`, item.amount_cents]),
  );
  const plans = ["free", "investor", "pro"];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Plan & Billing</h1>
          <p className="text-sm text-muted mt-1">Prices are shown before applicable VAT.</p>
        </div>
        {access?.source === "subscription" && (
          <button
            onClick={() => portal.mutate()}
            disabled={portal.isPending}
            className="flex items-center gap-2 bg-surface-card border border-surface-border rounded-lg px-4 py-2 text-sm font-semibold"
          >
            {portal.isPending ? <Loader2 size={15} className="animate-spin" /> : <CreditCard size={15} />}
            Manage billing
          </button>
        )}
      </div>

      {isLoading ? <Loader2 className="animate-spin text-brand" /> : (
        <div className="rounded-xl border border-surface-border bg-surface-card px-4 py-3 text-sm">
          Current access: <span className="font-semibold capitalize">{access?.plan || "free"}</span>
          {access?.source === "trial" && access.effective_until && (
            <span className="text-muted"> · Pro trial until {new Date(access.effective_until).toLocaleDateString()}</span>
          )}
          {access?.in_grace && (
            <span className="text-loss"> · Payment failed; update payment details before {new Date(access.effective_until).toLocaleDateString()}</span>
          )}
          {access?.cancel_at_period_end && (
            <span className="text-muted"> · Cancels at the end of the paid period</span>
          )}
        </div>
      )}

      {awaitingProjection && access?.source !== "subscription" && (
        <div className="rounded-xl border border-brand/50 bg-brand/5 px-4 py-3 text-sm">
          Payment received. Plan access is pending signed Stripe reconciliation; this page will refresh automatically.
        </div>
      )}

      {access?.usage?.hosted_ai_monthly?.limit > 0 && (
        <p className="text-sm text-muted">
          Hosted AI remaining this month: {access.usage.hosted_ai_monthly.remaining} of {access.usage.hosted_ai_monthly.limit}
        </p>
      )}
      {access?.usage?.hosted_ai_trial?.limit > 0 && (
        <p className="text-sm text-muted">
          Hosted AI remaining in trial: {access.usage.hosted_ai_trial.remaining} of {access.usage.hosted_ai_trial.limit}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {plans.map((plan) => {
          const current = access?.plan === plan;
          const managedInPortal = access?.source === "subscription";
          return (
            <section key={plan} className={`rounded-xl border p-5 bg-surface-card ${plan === "pro" ? "border-brand" : "border-surface-border"}`}>
              <h2 className="text-lg font-semibold capitalize">{plan}</h2>
              <div className="mt-2 text-2xl font-bold">
                {plan === "free" ? "€0" : `${euro(prices.get(`${plan}:month`) || 0)} / month`}
              </div>
              {plan !== "free" && (
                <p className="text-xs text-muted mt-1">or {euro(prices.get(`${plan}:year`) || 0)} annually</p>
              )}
              <ul className="mt-5 space-y-2 text-sm">
                {FEATURES[plan].map((feature) => <li key={feature} className="flex gap-2"><Check size={15} className="text-gain shrink-0 mt-0.5" />{feature}</li>)}
              </ul>
              {plan !== "free" && (
                <div className="grid grid-cols-2 gap-2 mt-6">
                  {["month", "year"].map((interval) => (
                    <button
                      key={interval}
                      disabled={checkout.isPending || current || managedInPortal}
                      onClick={() => checkout.mutate({ plan, interval })}
                      className="rounded-lg bg-brand text-black font-semibold px-3 py-2 text-sm disabled:opacity-40"
                    >
                      {current ? "Current" : managedInPortal ? "Use portal" : interval === "month" ? "Monthly" : "Annual"}
                    </button>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
      {checkout.error && <p className="text-sm text-loss">{checkout.error.response?.data?.detail?.code || "Checkout could not be started."}</p>}
      <p className="text-xs text-muted">
        Variable-cost services are subject to the displayed fair-use quotas.
      </p>
    </div>
  );
}
