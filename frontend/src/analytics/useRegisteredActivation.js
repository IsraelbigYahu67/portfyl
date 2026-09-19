import { useCallback, useMemo } from "react";
import { useAuth } from "../auth/AuthProvider";
import { useAnalytics } from "./AnalyticsProvider";
import { CONSENT_STATES } from "./consent";
import { ANALYTICS_EVENTS } from "./eventContract";
import { readActivationState, writeActivationState } from "./activationState";

/**
 * Tracks the registered-account activation funnel: portfolio creation, first
 * data import, and first populated dashboard render. Local progress lives in
 * activationState (never uploaded, never enumerated); only the four
 * contract-shaped events below ever reach analytics, and only after the
 * mutation they describe has actually succeeded.
 */
export function useRegisteredActivation() {
  const { user, currentWorkspace } = useAuth();
  const { consent, capture } = useAnalytics();

  const userId = user?.id ?? null;
  const workspaceId = currentWorkspace?.id ?? null;
  const persist = consent === CONSENT_STATES.ACCEPTED;

  const withState = useCallback(
    (mutate) => {
      if (!userId || !workspaceId) return false;
      const state = readActivationState(userId, workspaceId, { persist });
      const outcome = mutate(state);
      if (!outcome) return false;
      writeActivationState(userId, workspaceId, outcome.nextState, { persist });
      for (const [name, properties] of outcome.events) capture(name, properties);
      return true;
    },
    [userId, workspaceId, persist, capture]
  );

  const recordPortfolioCreated = useCallback(
    (creationPath) => {
      if (!userId || !workspaceId) return false;
      capture(ANALYTICS_EVENTS.PORTFOLIO_CREATED, { creation_path: creationPath });
      return true;
    },
    [userId, workspaceId, capture]
  );

  const recordPortfolioDataImported = useCallback(
    (sourceType) =>
      withState((state) => {
        const events = [[ANALYTICS_EVENTS.PORTFOLIO_DATA_IMPORTED, { source_type: sourceType }]];
        let nextState = { ...state, sourceType, dataImported: true };
        if (state.dashboardRendered && !state.activated) {
          events.push([ANALYTICS_EVENTS.DASHBOARD_FIRST_VALUE_RENDERED, { source_type: sourceType }]);
          events.push([ANALYTICS_EVENTS.USER_ACTIVATION_REACHED, { source_type: sourceType }]);
          nextState = { ...nextState, activated: true };
        }
        return { nextState, events };
      }),
    [withState]
  );

  const recordPopulatedDashboard = useCallback(
    () =>
      withState((state) => {
        // "duplicate renders emit neither again" -- once this workspace has
        // recorded a populated dashboard, later renders are a no-op.
        if (state.dashboardRendered) return null;
        let nextState = { ...state, dashboardRendered: true };
        const events = [];
        if (state.dataImported && !state.activated) {
          events.push([ANALYTICS_EVENTS.DASHBOARD_FIRST_VALUE_RENDERED, { source_type: state.sourceType }]);
          events.push([ANALYTICS_EVENTS.USER_ACTIVATION_REACHED, { source_type: state.sourceType }]);
          nextState = { ...nextState, activated: true };
        }
        return { nextState, events };
      }),
    [withState]
  );

  return useMemo(
    () => ({ recordPortfolioCreated, recordPortfolioDataImported, recordPopulatedDashboard }),
    [recordPortfolioCreated, recordPortfolioDataImported, recordPopulatedDashboard]
  );
}
