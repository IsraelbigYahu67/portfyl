import { useCallback, useRef } from "react";

import { createPortfolio, deletePortfolio } from "../api";
import { usePortfolio } from "../App";
import { getApiErrorMessage } from "../lib/apiError";
import { needsOwnPortfolio, uniquePortfolioName } from "../lib/brokerPortfolio";

// Opens a dedicated portfolio for `broker` when the selected one already holds
// other data, and switches to it so the following import/connect request (the
// axios interceptor sends the active portfolio) lands there.
//
// open(broker) resolves to:
//   null                          -> keep using the selected portfolio
//   { created, previous }         -> switched to the new portfolio `created`
//   { blocked, previous }         -> a new portfolio was needed but could not
//                                    be created (plan limit); still on `previous`
// discard(session) switches back and deletes a portfolio open() created, for
// when the import or connection it was made for did not happen.
export function useBrokerPortfolio() {
  const { current, refetchPortfolios, setCurrentId } = usePortfolio();
  // Always the latest setter: open() and discard() run across awaits during
  // which the active portfolio changes.
  const latest = useRef({});
  latest.current = { current, refetchPortfolios, setCurrentId };

  const open = useCallback(async (broker) => {
    const refreshed = await latest.current.refetchPortfolios();
    const portfolios = refreshed?.data ?? [];
    const selected = latest.current.current;
    const previous = portfolios.find((portfolio) => portfolio.id === selected?.id) ?? selected;
    if (!needsOwnPortfolio(previous, broker)) return null;
    let created;
    try {
      created = await createPortfolio({ name: uniquePortfolioName(portfolios, broker) });
    } catch (error) {
      return { blocked: getApiErrorMessage(error, "A new portfolio could not be created"), previous };
    }
    await latest.current.refetchPortfolios();
    latest.current.setCurrentId(created.id);
    return { created, previous };
  }, []);

  const discard = useCallback(async (session) => {
    if (!session?.created) return;
    latest.current.setCurrentId(session.previous.id);
    try {
      await deletePortfolio(session.created.id);
    } finally {
      await latest.current.refetchPortfolios();
    }
  }, []);

  return { open, discard };
}
