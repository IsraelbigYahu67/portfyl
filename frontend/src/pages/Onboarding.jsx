import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import OnboardingView, { choiceHandler } from "../components/onboarding/OnboardingView";
import { activatePortfolio, createDemoPortfolio, createPendingImportPortfolio, createPortfolio } from "../api";
import { useCurrency, usePortfolio } from "../App";
import { TRACKER_HOME } from "../lib/routes";
import { uniquePortfolioName } from "../lib/brokerPortfolio";
import { findSupportedBroker } from "../lib/onboardingBrokers";
import { clearIntendedBroker, intendedBroker } from "../lib/signupIntent";
import { useRegisteredActivation } from "../analytics/useRegisteredActivation";
import { useT } from "../i18n/I18nProvider";


function errorMessage(error, t) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return detail?.message || t("We couldn't prepare your portfolio. Please try again.");
}


// One action per ONBOARDING_CHOICE_KEYS entry (Onboarding.test.jsx checks the
// two match). Pure: it only builds the closures; nothing runs until a click.
// `broker` is the supported broker picked in step 1 (null before that).
export function buildOnboardingActions({ beginImport, activate, broker = null, portfolios = [] }) {
  return {
    import: beginImport,
    demo: () => activate(createDemoPortfolio, TRACKER_HOME, "demo"),
    broker: () => activate(
      // One broker per portfolio: name it after the broker it will sync.
      () => createPortfolio({ name: broker ? uniquePortfolioName(portfolios, broker.key) : "My portfolio" }),
      broker ? `/settings?section=connections&broker=${broker.key}` : "/settings?section=connections",
      "broker",
    ),
  };
}


export default function Onboarding() {
  const t = useT();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { portfolios, pendingImportPortfolio, setCurrentId, refetchPortfolios } = usePortfolio();
  const { currency, setCurrency } = useCurrency() ?? {};
  const { recordPortfolioCreated, recordPortfolioDataImported } = useRegisteredActivation();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  // In memory, not the URL: it may be free text the user typed.
  const [unsupportedName, setUnsupportedName] = useState(null);
  // A broker the visitor named on the landing page, remembered across sign-up
  // and e-mail verification. Read once, on the first render, so step 2 shows
  // at once; a broker in the URL wins, and any later pick or "Change broker"
  // drops it (changeBroker), so it can never override a newer choice.
  const [remembered, setRemembered] = useState(() => (searchParams.has("broker") ? null : intendedBroker()));
  // In the URL, so "Leave import" on the Import page can return to step 2.
  const broker = findSupportedBroker(searchParams.get("broker") ?? remembered);

  // Put the remembered broker in the URL too, so that Leave import and a
  // reload come back to it.
  useEffect(() => {
    if (!remembered) return;
    const next = new URLSearchParams(searchParams);
    next.set("broker", remembered);
    setSearchParams(next, { replace: true });
    // Only on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function changeBroker(key) {
    setError(null);
    setRemembered(null);
    const next = new URLSearchParams(searchParams);
    if (key) next.set("broker", key);
    else next.delete("broker");
    setSearchParams(next);
  }

  function changeUnsupported(name) {
    setError(null);
    setUnsupportedName(name);
  }

  async function activate(create, destination, kind) {
    setBusy(kind);
    setError(null);
    try {
      const portfolio = await create();
      setCurrentId(portfolio.id);
      recordPortfolioCreated(kind);
      // The remembered broker has done its job once a real portfolio exists.
      // The demo keeps it: the sample-data banner offers "Import your own
      // portfolio" for that broker.
      if (kind === "broker") clearIntendedBroker();
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
      const portfolio = await createPendingImportPortfolio();
      setCurrentId(portfolio.id);
      recordPortfolioCreated("csv");
      clearIntendedBroker();
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
      const pending = pendingImportPortfolio || await createPendingImportPortfolio();
      const portfolio = await activatePortfolio(pending.id);
      setCurrentId(portfolio.id);
      recordPortfolioCreated("blank");
      clearIntendedBroker();
      navigate(TRACKER_HOME);
      await refetchPortfolios();
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(null);
    }
  }

  const actions = buildOnboardingActions({ beginImport, activate, broker, portfolios });

  return (
    <OnboardingView
      currency={currency}
      onCurrencyChange={setCurrency}
      brokerKey={broker?.key ?? null}
      onBrokerChange={changeBroker}
      unsupportedName={unsupportedName}
      onUnsupportedChange={changeUnsupported}
      onChoose={(key) => choiceHandler(actions, key)()}
      onStartBlank={startBlank}
      busy={busy}
      error={error}
    />
  );
}
