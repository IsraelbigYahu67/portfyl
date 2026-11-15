import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchEditionOnboardingPlan } from "@edition-manifest";

import {
  activatePortfolio,
  confirmCheckout,
  connectEtoro,
  connectIBKR,
  connectT212,
  createPendingImportPortfolio,
  fetchEtoroStatus,
  fetchIBKRStatus,
  fetchT212Status,
  startCheckout,
  syncEtoro,
  syncIBKR,
  syncT212,
  updateTestPlan,
} from "../api";
import { useT } from "../i18n/I18nProvider";
import { getApiErrorMessage } from "../lib/apiError";
import {
  apiErrorCode,
  clearConnectStep,
  isPlanUpgradeRequired,
  rememberConnectStep,
  syncImportedData,
} from "../lib/onboardingConnect";
import { rememberIntendedBroker } from "../lib/signupIntent";

// Onboarding's "Connect <broker>" step: the plan check, the upgrade, the
// checkout return, connect -> first sync -> activate, and resume. Pure state
// machine; Onboarding.jsx wires it to the URL, analytics and navigation.

const QUIET = { suppressEntitlementPrompt: true };

const BROKER_CONNECTORS = {
  trading212: {
    status: () => fetchT212Status(),
    connect: (credentials, options) => connectT212(credentials.apiKey.trim(), credentials.apiSecret.trim(), options),
    sync: (options) => syncT212(options),
  },
  ibkr: {
    status: () => fetchIBKRStatus(),
    connect: (credentials, options) => connectIBKR(credentials.flexToken.trim(), credentials.queryId.trim(), options),
    sync: (options) => syncIBKR(options),
  },
  etoro: {
    status: () => fetchEtoroStatus(),
    connect: (credentials, options) => connectEtoro(credentials.userKey.trim(), options),
    sync: (options) => syncEtoro(options),
  },
};

export function useOnboardingConnect({
  broker,
  pendingPortfolio,
  setCurrentId,
  checkoutReturn,
  onCheckoutReturnHandled,
  onFinished,
}) {
  const t = useT();
  const queryClient = useQueryClient();
  const brokerKey = broker?.key ?? null;

  const [phase, setPhase] = useState("loading");
  const [plan, setPlan] = useState(null);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const [locked, setLocked] = useState(false);

  // Always the latest props and translator: the async runs below span renders.
  const latest = useRef({});
  latest.current = { broker, pendingPortfolio, setCurrentId, checkoutReturn, onCheckoutReturnHandled, onFinished, t, plan, queryClient };
  // Each async run takes a number; a run whose number is no longer current
  // (broker changed, unmounted, a newer run started) drops its result.
  const runRef = useRef(0);
  // The checkout return is handled once per value, even when React StrictMode
  // runs the load effect twice: both runs await the same promise.
  const checkoutRef = useRef(null);
  // A pending portfolio this hook created itself, until the page's list
  // catches up. Stops a retry after a wrong key from creating a second one.
  const createdRef = useRef(null);
  const upgradingRef = useRef(false);

  const handleCheckoutOnce = useCallback((returned) => {
    if (checkoutRef.current?.returned === returned) return checkoutRef.current.promise;
    const promise = (async () => {
      let result = null;
      if (returned.outcome === "canceled") {
        result = "canceled";
      } else if (returned.sessionId) {
        const current = await fetchEditionOnboardingPlan();
        if (current.billingEnabled) {
          try {
            const confirmed = await confirmCheckout(returned.sessionId);
            if (confirmed?.checkout_status !== "complete") result = "processing";
          } catch {
            result = "processing";
          }
        }
      }
      clearConnectStep();
      latest.current.onCheckoutReturnHandled?.();
      return result;
    })();
    checkoutRef.current = { returned, promise };
    return promise;
  }, []);

  // Activate the pending portfolio (after the first sync when `withSync`) and
  // hand over to the page. A 409 on activate means a broker sync already wrote
  // rows, which is success.
  const finish = useCallback(async (key, portfolioId, withSync, run) => {
    const connector = BROKER_CONNECTORS[key];
    const stale = () => run !== runRef.current;
    try {
      let imported = false;
      if (withSync) {
        setPhase("syncing");
        const result = await connector.sync(QUIET);
        if (stale()) return;
        imported = syncImportedData(key, result);
      }
      try {
        await activatePortfolio(portfolioId);
      } catch (activateError) {
        if (activateError?.response?.status !== 409) throw activateError;
      }
      if (stale()) return;
      await latest.current.onFinished({ imported });
    } catch (finishError) {
      if (stale()) return;
      const { t: translate } = latest.current;
      setPhase("sync-failed");
      setError(getApiErrorMessage(finishError, translate("Sync failed"), translate));
    }
  }, []);

  // Steps: checkout return -> resume a connected pending portfolio -> plan.
  const load = useCallback(async ({ keepNotice = false } = {}) => {
    const { broker: current } = latest.current;
    if (!current) return;
    const key = current.key;
    const run = ++runRef.current;
    const stale = () => run !== runRef.current;
    setPhase("loading");
    setError(null);
    if (!keepNotice) setNotice(null);
    try {
      const returned = latest.current.checkoutReturn;
      if (returned) {
        const outcome = await handleCheckoutOnce(returned);
        if (stale()) return;
        if (outcome) setNotice(outcome);
      }

      const pending = latest.current.pendingPortfolio ?? createdRef.current;
      if (pending) {
        latest.current.setCurrentId(pending.id);
        const status = await BROKER_CONNECTORS[key].status();
        if (stale()) return;
        if (status?.connected === true) {
          setLocked(true);
          await finish(key, pending.id, !status.last_synced_at, run);
          return;
        }
        if (key === "etoro" && status?.configured === false) {
          setPhase("unavailable");
          return;
        }
      }

      const next = await fetchEditionOnboardingPlan();
      if (stale()) return;
      setPlan(next);
      if (next.brokerSync) setNotice(null);
      setPhase(next.brokerSync ? "form" : "gated");
    } catch {
      if (stale()) return;
      setPhase("load-error");
      setError(latest.current.t("We couldn't check your plan. Please try again."));
    }
  }, [finish, handleCheckoutOnce]);

  useEffect(() => {
    setPlan(null);
    setNotice(null);
    setError(null);
    setLocked(false);
    setPhase("loading");
    if (brokerKey) load();
    return () => {
      runRef.current += 1;
    };
  }, [brokerKey, load]);

  const submit = useCallback(async (credentials) => {
    const { broker: current } = latest.current;
    if (!current) return;
    const key = current.key;
    const connector = BROKER_CONNECTORS[key];
    const run = ++runRef.current;
    const stale = () => run !== runRef.current;
    setError(null);
    setPhase("connecting");
    let portfolioId;
    try {
      let pending = latest.current.pendingPortfolio ?? createdRef.current;
      if (!pending) {
        pending = await createPendingImportPortfolio();
        createdRef.current = pending;
      }
      if (stale()) return;
      portfolioId = pending.id;
      latest.current.setCurrentId(portfolioId);
      await connector.connect(credentials, QUIET);
      if (stale()) return;
    } catch (connectError) {
      if (stale()) return;
      if (isPlanUpgradeRequired(connectError)) {
        try {
          const next = await fetchEditionOnboardingPlan();
          if (stale()) return;
          setPlan(next);
        } catch {
          /* The gate is still the right screen; the plan is re-read on the next try. */
        }
        setPhase("gated");
        return;
      }
      if (key === "etoro" && connectError?.response?.status === 503) {
        setPhase("unavailable");
        return;
      }
      const { t: translate } = latest.current;
      setPhase("form");
      setError(getApiErrorMessage(connectError, translate("Failed to connect"), translate));
      return;
    }
    setLocked(true);
    await finish(key, portfolioId, true, run);
  }, [finish]);

  const recheck = useCallback(() => load({ keepNotice: true }), [load]);

  const upgrade = useCallback(async () => {
    const { broker: current, plan: knownPlan } = latest.current;
    if (!current || upgradingRef.current) return;
    const key = current.key;
    const { t: translate } = latest.current;
    upgradingRef.current = true;
    setError(null);
    try {
      if (!knownPlan?.billingEnabled) {
        try {
          await updateTestPlan("investor");
          latest.current.queryClient.invalidateQueries({ queryKey: ["plan-capabilities"] });
          const next = await fetchEditionOnboardingPlan();
          setPlan(next);
          if (next.brokerSync) setNotice(null);
          setPhase(next.brokerSync ? "form" : "gated");
        } catch {
          setError(translate("The plan could not be changed. Please try again."));
        }
        return;
      }
      rememberConnectStep(key);
      rememberIntendedBroker(key);
      try {
        const { url } = await startCheckout("investor");
        window.location.assign(url);
      } catch (checkoutError) {
        const code = apiErrorCode(checkoutError);
        if (code === "workspace_owner_required") {
          setError(translate("Only the workspace owner can change the plan or manage billing."));
        } else if (code === "subscription_exists") {
          await recheck();
        } else {
          setError(translate("The payment page could not be opened. Please try again."));
        }
      }
    } finally {
      upgradingRef.current = false;
    }
  }, [recheck]);

  return { phase, plan, notice, error, locked, submit, upgrade, recheck };
}
