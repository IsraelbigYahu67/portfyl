import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { BILLING_STATUS_KEY } from "../../lib/billingStatusQuery";

const THROTTLE_MS = 30_000;
const DAY_MS = 86_400_000;

// Keeps the cached plan honest when it changes under an open app (a trial
// running out): a denied request refetches the billing status and the plan's
// capabilities (at most once per 30 s), and while a trial ends within 24 h one
// timer refetches both at the moment it ends.
export function useEntitlementRefresh(status) {
  const queryClient = useQueryClient();
  const lastRefresh = useRef(0);

  useEffect(() => {
    const refresh = (force) => {
      const now = Date.now();
      if (!force && now - lastRefresh.current < THROTTLE_MS) return;
      lastRefresh.current = now;
      queryClient.invalidateQueries({ queryKey: BILLING_STATUS_KEY });
      queryClient.invalidateQueries({ queryKey: ["plan-capabilities"] });
    };
    const onDenied = () => refresh(false);
    window.addEventListener("portfyl:entitlement-denied", onDenied);
    return () => window.removeEventListener("portfyl:entitlement-denied", onDenied);
  }, [queryClient]);

  const endsAt = status?.source === "trial" ? status.effective_until : null;
  useEffect(() => {
    if (!endsAt) return undefined;
    const delay = Date.parse(endsAt) - Date.now();
    if (!Number.isFinite(delay) || delay <= 0 || delay >= DAY_MS) return undefined;
    const timer = setTimeout(() => {
      lastRefresh.current = Date.now();
      queryClient.invalidateQueries({ queryKey: BILLING_STATUS_KEY });
      queryClient.invalidateQueries({ queryKey: ["plan-capabilities"] });
    }, delay);
    return () => clearTimeout(timer);
  }, [endsAt, queryClient]);
}
