import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import OnboardingView, { choiceHandler } from "../components/onboarding/OnboardingView";
import { activatePortfolio, createDemoPortfolio, createPendingImportPortfolio, requestBrokerSupport } from "../api";
import { useCurrency, usePortfolio } from "../App";
import { TRACKER_HOME } from "../lib/routes";
import { findSupportedBroker } from "../lib/onboardingBrokers";
import { clearConnectStep, connectStepBroker, readCheckoutReturn, rememberConnectStep } from "../lib/onboardingConnect";
import { useOnboardingConnect } from "../hooks/useOnboardingConnect";
import { clearIntendedBroker, intendedBroker, rememberIntendedBroker } from "../lib/signupIntent";
import { useRegisteredActivation } from "../analytics/useRegisteredActivation";
import { useAnalytics } from "../analytics/AnalyticsProvider";
import { ANALYTICS_EVENTS } from "../analytics/eventContract";
import { useT } from "../i18n/I18nProvider";


function errorMessage(error, t) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return detail?.message || t("We couldn't prepare your portfolio. Please try again.");
}


// One action per ONBOARDING_CHOICE_KEYS entry (Onboarding.test.jsx checks the
// two match). Pure: it only builds the closures; nothing runs until a click.
// `openConnect` opens the connect step inside onboarding; no portfolio is
// created until the visitor submits credentials.
export function buildOnboardingActions({ beginImport, activate, openConnect }) {
  return {
    import: beginImport,
    demo: () => activate(createDemoPortfolio, TRACKER_HOME, "demo"),
    broker: openConnect,
  };
}


export default function Onboarding() {
  const t = useT();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { pathname } = useLocation();
  const { pendingImportPortfolio, setCurrentId, refetchPortfolios } = usePortfolio();
  const { currency, setCurrency } = useCurrency() ?? {};
  const { recordPortfolioCreated, recordPortfolioDataImported } = useRegisteredActivation();
  const { capture } = useAnalytics();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  // In memory, not the URL: it may be free text the user typed.
  const [unsupportedName, setUnsupportedName] = useState(null);
  // The "notify me" request for unsupportedName. notifyRun changes with every
  // new unsupportedName, so a slow answer for a broker no longer on screen is
  // dropped; notifyBusy stops a double click from sending twice.
  const [notifyState, setNotifyState] = useState("idle");
  const notifyRun = useRef(0);
  const notifyBusy = useRef(false);
  // A broker the visitor named on the landing page, remembered across sign-up
  // and e-mail verification. Read once, on the first render, so step 2 shows
  // at once; a broker in the URL wins, and any later pick or "Change broker"
  // drops it (changeBroker), so it can never override a newer choice.
  // A connect step left open (closed tab) wins over it and reopens that step.
  // Stripe's return carries no broker: the checkout effect below finds it.
  const [checkoutReturn] = useState(() => readCheckoutReturn(searchParams));
  const [initialBroker] = useState(() => {
    if (searchParams.has("broker") || checkoutReturn) return { key: null, fromMarker: false };
    const marker = connectStepBroker();
    return marker ? { key: marker, fromMarker: true } : { key: intendedBroker(), fromMarker: false };
  });
  const [remembered, setRemembered] = useState(initialBroker.key);
  // True only until the mount effect has put the restored step in the URL.
  const [restoringConnect, setRestoringConnect] = useState(initialBroker.fromMarker);
  // In the URL, so "Leave import" on the Import page can return to step 2.
  const broker = findSupportedBroker(searchParams.get("broker") ?? remembered);
  // Stripe returns to /pricing: AppLayout then remounts onboarding at the
  // right path, so this instance renders nothing meanwhile.
  const movingCheckoutReturn = Boolean(checkoutReturn) && pathname !== "/onboarding";

  // Funnel: one onboarding_step_viewed per step the visitor reaches. The ref
  // holds the last step reported, so a re-render on the same step and React
  // StrictMode's double effect stay silent, while coming back to a step
  // (broker -> choices -> Change broker -> broker) reports it again. The step
  // is only a fixed label; the typed broker name never leaves this page.
  const connectWanted = searchParams.get("step") === "connect" || restoringConnect;
  const step = unsupportedName ? "unsupported" : broker ? (connectWanted && broker.api ? "connect" : "choices") : "broker";
  const reportedStep = useRef(null);
  useEffect(() => {
    if (movingCheckoutReturn || reportedStep.current === step) return;
    reportedStep.current = step;
    capture(ANALYTICS_EVENTS.ONBOARDING_STEP_VIEWED, { step });
  }, [step, capture, movingCheckoutReturn]);

  // Put the remembered broker (and a restored connect step) in the URL too, so
  // that Leave import and a reload come back to it.
  useEffect(() => {
    if (!remembered) return;
    const next = new URLSearchParams(searchParams);
    next.set("broker", remembered);
    if (initialBroker.fromMarker) next.set("step", "connect");
    setSearchParams(next, { replace: true });
    setRestoringConnect(false);
    // Only on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A checkout return that landed away from /onboarding moves there with its
  // parameters, for the remembered broker; without one only the checkout
  // parameters are dropped. A return that already is on /onboarding but cannot
  // show the connect step is cleaned up the same way.
  useEffect(() => {
    if (!checkoutReturn) return;
    if (pathname !== "/onboarding") {
      const key = connectStepBroker() ?? intendedBroker();
      const next = new URLSearchParams();
      if (key) {
        next.set("broker", key);
        next.set("step", "connect");
        next.set("checkout", checkoutReturn.outcome);
        if (checkoutReturn.sessionId) next.set("session_id", checkoutReturn.sessionId);
      }
      const query = next.toString();
      navigate(`/onboarding${query ? `?${query}` : ""}`, { replace: true });
    } else if (!(broker?.api && searchParams.get("step") === "connect")) {
      stripCheckoutParams();
    }
    // Only on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function stripCheckoutParams() {
    const next = new URLSearchParams(searchParams);
    next.delete("checkout");
    next.delete("session_id");
    setSearchParams(next, { replace: true });
  }

  function openConnect() {
    if (!broker) return;
    rememberConnectStep(broker.key);
    const next = new URLSearchParams(searchParams);
    next.set("broker", broker.key);
    next.set("step", "connect");
    setSearchParams(next);
  }

  function leaveConnect() {
    clearConnectStep();
    const next = new URLSearchParams(searchParams);
    next.delete("step");
    setSearchParams(next);
  }

  function changeBroker(key) {
    // Only a real pick: null is "Change broker", and a broker restored from
    // the URL or the landing page never comes through here.
    if (key) capture(ANALYTICS_EVENTS.ONBOARDING_BROKER_PICKED, { broker_key: key });
    setError(null);
    setRemembered(null);
    clearConnectStep();
    // Storage follows the latest choice, so a stale broker never survives a
    // reload or reaches the sample-data banner after the demo.
    if (key) rememberIntendedBroker(key);
    else clearIntendedBroker();
    const next = new URLSearchParams(searchParams);
    if (key) next.set("broker", key);
    else next.delete("broker");
    next.delete("step");
    setSearchParams(next);
  }

  function changeUnsupported(name) {
    // A name means the visitor went to the unsupported screen; null is
    // "Choose another broker" or the first half of a supported pick. The
    // marker is fixed: the typed name is never an event property.
    if (name) capture(ANALYTICS_EVENTS.ONBOARDING_BROKER_PICKED, { broker_key: "unsupported" });
    setError(null);
    setUnsupportedName(name);
    notifyRun.current += 1;
    notifyBusy.current = false;
    setNotifyState("idle");
  }

  async function notifyMe() {
    if (!unsupportedName || notifyBusy.current) return;
    const run = notifyRun.current;
    notifyBusy.current = true;
    setNotifyState("sending");
    let result = "sent";
    try {
      await requestBrokerSupport(unsupportedName);
    } catch {
      result = "error";
    }
    if (run !== notifyRun.current) return;
    notifyBusy.current = false;
    setNotifyState(result);
    if (result === "sent") capture(ANALYTICS_EVENTS.BROKER_REQUEST_SENT, {});
  }

  async function activate(create, destination, kind) {
    setBusy(kind);
    setError(null);
    try {
      const portfolio = await create();
      setCurrentId(portfolio.id);
      recordPortfolioCreated(kind);
      // The demo keeps the remembered broker: the sample-data banner offers
      // "Import your own portfolio" for that broker.
      clearConnectStep();
      // createDemoPortfolio populates its data as part of creation itself --
      // unlike csv/broker, there is no separate later import step for it.
      if (kind === "demo") recordPortfolioDataImported("demo");
      navigate(destination);
      await refetchPortfolios();
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(null);
    }
  }

  async function beginImport() {
    setBusy("import");
    setError(null);
    try {
      const portfolio = await createPendingImportPortfolio(t("My portfolio"));
      setCurrentId(portfolio.id);
      recordPortfolioCreated("csv");
      clearIntendedBroker();
      clearConnectStep();
      await refetchPortfolios();
      navigate(broker ? `/import?broker=${broker.key}` : "/import");
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(null);
    }
  }

  async function startBlank() {
    setBusy("blank");
    setError(null);
    try {
      const pending = pendingImportPortfolio || await createPendingImportPortfolio(t("My portfolio"));
      const portfolio = await activatePortfolio(pending.id);
      setCurrentId(portfolio.id);
      recordPortfolioCreated("blank");
      clearIntendedBroker();
      clearConnectStep();
      navigate(TRACKER_HOME);
      await refetchPortfolios();
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(null);
    }
  }

  // Keeps today's order: navigate first, so the refetch that removes the
  // pending-portfolio gate cannot unmount onboarding mid-flight.
  async function finishConnect({ imported }) {
    recordPortfolioCreated("broker");
    if (imported) recordPortfolioDataImported("broker");
    clearIntendedBroker();
    clearConnectStep();
    navigate(TRACKER_HOME);
    await refetchPortfolios();
  }

  // The hook only works while the connect step is on screen (null = idle).
  const connectState = useOnboardingConnect({
    broker: step === "connect" ? broker : null,
    pendingPortfolio: pendingImportPortfolio,
    setCurrentId,
    checkoutReturn: pathname === "/onboarding" ? checkoutReturn : null,
    onCheckoutReturnHandled: stripCheckoutParams,
    onFinished: finishConnect,
  });

  const actions = buildOnboardingActions({ beginImport, activate, openConnect });
  const connect = step === "connect"
    ? {
      phase: connectState.phase,
      billingEnabled: connectState.plan?.billingEnabled,
      canManageBilling: connectState.plan?.canManageBilling,
      investorMonthlyCents: connectState.plan?.investorMonthlyCents,
      notice: connectState.notice,
      error: connectState.error,
      locked: connectState.locked,
      onSubmit: connectState.submit,
      onUpgrade: connectState.upgrade,
      onRecheck: connectState.recheck,
      onImportFree: () => beginImport(),
      onBack: leaveConnect,
      onChangeBroker: () => changeBroker(null),
      onDemo: () => activate(createDemoPortfolio, TRACKER_HOME, "demo"),
    }
    : null;

  if (movingCheckoutReturn) return null;

  return (
    <OnboardingView
      currency={currency}
      onCurrencyChange={setCurrency}
      brokerKey={broker?.key ?? null}
      onBrokerChange={changeBroker}
      unsupportedName={unsupportedName}
      onUnsupportedChange={changeUnsupported}
      onNotify={notifyMe}
      notifyState={notifyState}
      onChoose={(key) => choiceHandler(actions, key)()}
      onStartBlank={startBlank}
      busy={busy}
      error={error}
      connect={connect}
    />
  );
}
