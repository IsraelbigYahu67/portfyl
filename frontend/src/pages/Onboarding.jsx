import { useState } from "react";
import { useNavigate } from "react-router-dom";
import OnboardingView, { choiceHandler } from "../components/onboarding/OnboardingView";
import { activatePortfolio, createDemoPortfolio, createPendingImportPortfolio, createPortfolio } from "../api";
import { usePortfolio } from "../App";
import { TRACKER_HOME } from "../lib/routes";
import { useRegisteredActivation } from "../analytics/useRegisteredActivation";


function errorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return detail?.message || "We couldn't prepare your portfolio. Please try again.";
}


// One action per ONBOARDING_CHOICE_KEYS entry (Onboarding.test.jsx checks the
// two match). Pure: it only builds the closures; nothing runs until a click.
export function buildOnboardingActions({ beginImport, activate }) {
  return {
    import: beginImport,
    demo: () => activate(createDemoPortfolio, TRACKER_HOME, "demo"),
    broker: () => activate(
      () => createPortfolio({ name: "My portfolio" }),
      "/settings?section=connections",
      "broker",
    ),
  };
}


export default function Onboarding() {
  const navigate = useNavigate();
  const { pendingImportPortfolio, setCurrentId, refetchPortfolios } = usePortfolio();
  const { recordPortfolioCreated, recordPortfolioDataImported } = useRegisteredActivation();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  async function activate(create, destination, kind) {
    setBusy(kind);
    setError(null);
    try {
      const portfolio = await create();
      setCurrentId(portfolio.id);
      recordPortfolioCreated(kind);
      // createDemoPortfolio populates its data as part of creation itself --
      // unlike csv/broker, there is no separate later import step for it.
      if (kind === "demo") recordPortfolioDataImported("demo");
      navigate(destination);
      await refetchPortfolios();
    } catch (err) {
      setError(errorMessage(err));
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
      await refetchPortfolios();
      navigate("/import");
    } catch (err) {
      setError(errorMessage(err));
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
      navigate(TRACKER_HOME);
      await refetchPortfolios();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const actions = buildOnboardingActions({ beginImport, activate });

  return (
    <OnboardingView
      onChoose={(key) => choiceHandler(actions, key)()}
      onStartBlank={startBlank}
      busy={busy}
      error={error}
    />
  );
}
