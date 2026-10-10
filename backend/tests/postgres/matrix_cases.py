"""The literal Alice/Bob route matrix.

This module is data, not behaviour: it enumerates every tenant-owned resource
the API exposes, the URL Alice uses to reach her own copy, the URL she would
use to reach Bob's, and the payloads for create/update. `test_alice_bob_matrix.py`
parametrizes over it; `docs/security/tenant-isolation-matrix.md` renders the
same rows for humans.

Contract encoded here (see the plan's Global Constraints):

* Public API identifiers are UUID strings. Every `{placeholder}` below resolves
  to a `public_id`, never to an internal integer primary key -- those must be
  neither accepted nor serialized.
* A foreign resource is indistinguishable from a nonexistent one: every foreign
  read / update / delete is **404**, exactly what a random UUID returns. A 403
  would leak the existence of another tenant's row and let an attacker
  enumerate IDs, so `FOREIGN_STATUS` is a single constant on purpose.
* Names are unique per workspace, not globally: the same name in another tenant
  is a different customer's data (200), the same name inside one workspace is a
  conflict (409).
* No session at all is **401**; a valid session with a missing/failed CSRF token
  on a CSRF-gated route is **403**.

Placeholders resolved from `MatrixTenants.ids`:
  alice_workspace, alice_portfolio, alice_transaction, alice_cash,
  alice_watchlist, alice_watchlist_item, alice_benchmark, alice_alert,
  and the identical `bob_*` set, plus `random` (a UUID that exists nowhere).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


#: A foreign resource must be indistinguishable from a nonexistent one.
FOREIGN_STATUS = 404


@dataclass(frozen=True)
class ResourceCase:
    """One tenant-owned resource and the five things the matrix needs to
    exercise it: where Alice lists it, where she reaches her own row, where she
    would reach Bob's, and the create/update bodies."""

    resource: str
    list_url: str | None
    own_url: str | None
    foreign_url: str | None
    create_payload: Mapping[str, Any] | None
    update_payload: Mapping[str, Any] | None
    #: HTTP verb used for "update" on this resource.
    update_method: str = "PATCH"
    #: Extra query params (templated) sent with every request for this resource.
    params: Mapping[str, str] = field(default_factory=dict)
    #: Query params that address Bob's portfolio instead of Alice's. When set,
    #: the resource is reached through a *portfolio* the caller does not own,
    #: rather than through a foreign resource UUID in the path.
    foreign_params: Mapping[str, str] | None = None
    #: URL a create POSTs to (defaults to `list_url`).
    create_url: str | None = None
    #: Set when DELETE is not supported for this resource.
    delete_supported: bool = True
    #: Expected status for Alice's own successful create.
    create_status: int = 200


#: Query params addressing Alice's own portfolio / Bob's portfolio. Routes
#: built on `require_portfolio` take the portfolio as a query parameter, so
#: "reach Bob's data" means "pass Bob's portfolio UUID", not "pass Bob's row id".
ALICE_PORTFOLIO_PARAMS: Mapping[str, str] = {"portfolio_id": "{alice_portfolio}"}
BOB_PORTFOLIO_PARAMS: Mapping[str, str] = {"portfolio_id": "{bob_portfolio}"}
RANDOM_PORTFOLIO_PARAMS: Mapping[str, str] = {"portfolio_id": "{random}"}


RESOURCE_CASES: tuple[ResourceCase, ...] = (
    # ---- Portfolios -------------------------------------------------------
    ResourceCase(
        resource="portfolios",
        list_url="/api/portfolios",
        own_url="/api/portfolios/{alice_portfolio}",
        foreign_url="/api/portfolios/{bob_portfolio}",
        create_payload={"name": "Matrix created portfolio"},
        update_payload={"name": "Matrix renamed portfolio"},
    ),
    # ---- Transactions -----------------------------------------------------
    ResourceCase(
        resource="transactions",
        list_url="/api/portfolio/transactions",
        own_url="/api/portfolio/transactions/{alice_transaction}",
        foreign_url="/api/portfolio/transactions/{bob_transaction}",
        create_payload={
            "ticker": "MSFT", "type": "buy", "shares": 1, "price": 100.0,
            "currency": "USD", "date": "2024-05-01",
        },
        update_payload=None,  # transactions are create/read/delete only
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
    ),
    # ---- Trade notes ------------------------------------------------------
    ResourceCase(
        resource="notes",
        list_url="/api/notes/all",
        own_url="/api/notes/transaction/{alice_transaction}",
        foreign_url="/api/notes/transaction/{bob_transaction}",
        create_payload=None,  # notes are upserted through PUT, not POSTed
        update_payload={"content": "matrix note", "sentiment": "bullish"},
        update_method="PUT",
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
    ),
    # ---- Custom benchmarks ------------------------------------------------
    ResourceCase(
        resource="benchmarks",
        list_url="/api/analytics/benchmarks",
        own_url="/api/analytics/benchmarks/{alice_benchmark}",
        foreign_url="/api/analytics/benchmarks/{bob_benchmark}",
        create_payload={"name": "Matrix benchmark", "kind": "ticker", "ticker": "^NDX"},
        update_payload={"name": "Matrix renamed benchmark"},
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
    ),
    # ---- Cash rows --------------------------------------------------------
    ResourceCase(
        resource="cash",
        list_url="/api/cash",
        own_url="/api/cash/{alice_cash}",
        foreign_url="/api/cash/{bob_cash}",
        create_payload={
            "type": "deposit", "amount": 250, "currency": "USD", "date": "2024-02-02",
        },
        update_payload={
            "type": "deposit", "amount": 260, "currency": "USD", "date": "2024-02-03",
        },
        update_method="PUT",
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
    ),
    # ---- Cash interest rates (workspace+portfolio scoped, no per-row URL) --
    ResourceCase(
        resource="cash-interest-rates",
        list_url="/api/cash/interest-rates",
        own_url=None,
        foreign_url=None,
        create_payload=None,
        update_payload=None,
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
        delete_supported=False,
    ),
    # ---- Watchlists + items ----------------------------------------------
    ResourceCase(
        resource="watchlists",
        list_url="/api/watchlists",
        own_url="/api/watchlists/{alice_watchlist}",
        foreign_url="/api/watchlists/{bob_watchlist}",
        create_payload={"name": "Matrix watchlist"},
        update_payload={"name": "Matrix renamed watchlist"},
    ),
    ResourceCase(
        resource="watchlist-items",
        list_url=None,
        own_url="/api/watchlists/{alice_watchlist}/items/{alice_watchlist_item}",
        foreign_url="/api/watchlists/{bob_watchlist}/items/{bob_watchlist_item}",
        create_url="/api/watchlists/{alice_watchlist}/items",
        create_payload={"ticker": "NVDA"},
        update_payload=None,  # items are add/remove only
    ),
    # ---- Price alerts -----------------------------------------------------
    ResourceCase(
        resource="alerts",
        list_url="/api/alerts",
        own_url="/api/alerts/{alice_alert}",
        foreign_url="/api/alerts/{bob_alert}",
        create_payload={"ticker": "TSLA", "direction": "above", "target_price": 500},
        update_payload={"target_price": 501},
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
    ),
    # ---- Personal (user-scoped) settings ----------------------------------
    ResourceCase(
        resource="user-settings",
        list_url="/api/assistant/config",
        own_url="/api/assistant/config",
        foreign_url=None,  # personal settings are keyed by the session's user
        create_payload=None,
        update_payload={"api_key": "matrix-personal-key", "model": "deepseek-chat"},
        update_method="PUT",
    ),
    # ---- Workspace-scoped settings ----------------------------------------
    ResourceCase(
        resource="workspace-settings",
        list_url="/api/settings/sync-schedule",
        own_url="/api/settings/sync-schedule",
        foreign_url=None,  # reached through X-Workspace-ID, not a row URL
        create_payload=None,
        update_payload={"mode": "daily", "daily_time": "05:30", "interval_hours": 6},
        update_method="PUT",
        delete_supported=False,
    ),
    # ---- Broker connection (Trading 212) ----------------------------------
    ResourceCase(
        resource="broker-connections",
        list_url="/api/broker/trading212/status",
        own_url=None,
        foreign_url=None,
        create_payload=None,
        update_payload=None,
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
        delete_supported=False,
    ),
    # ---- Broker balances (IBKR) -------------------------------------------
    ResourceCase(
        resource="broker-balances",
        list_url="/api/broker/ibkr/balance",
        own_url=None,
        foreign_url=None,
        create_payload=None,
        update_payload=None,
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
        delete_supported=False,
    ),
    # ---- Options ----------------------------------------------------------
    ResourceCase(
        resource="options",
        list_url="/api/options/trades",
        own_url=None,
        foreign_url=None,
        create_payload=None,
        update_payload=None,
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
        delete_supported=False,
    ),
    # ---- Polymarket -------------------------------------------------------
    ResourceCase(
        resource="polymarket",
        list_url="/api/polymarket/positions",
        own_url=None,
        foreign_url=None,
        create_payload=None,
        update_payload=None,
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
        delete_supported=False,
    ),
    # ---- Discord webhooks -------------------------------------------------
    ResourceCase(
        resource="discord",
        list_url="/api/discord/webhook",
        own_url="/api/discord/webhook",
        foreign_url=None,  # reached through the portfolio param, not a row URL
        create_payload={"webhook_url": "https://discord.com/api/webhooks/matrix/token"},
        create_url="/api/discord/webhook",
        update_payload={"notify_trades": False},
        params=ALICE_PORTFOLIO_PARAMS,
        foreign_params=BOB_PORTFOLIO_PARAMS,
        delete_supported=False,  # covered explicitly (delete removes the fixture row)
    ),
)


#: Read-only endpoints that take the portfolio as a query parameter. Reaching
#: any of them with Bob's portfolio UUID must 404 rather than return his data,
#: and must be indistinguishable from a random UUID.
PORTFOLIO_SCOPED_READS: tuple[tuple[str, str], ...] = (
    ("transactions", "/api/portfolio/transactions"),
    ("notes", "/api/notes/all"),
    ("benchmarks", "/api/analytics/benchmarks"),
    ("cash", "/api/cash"),
    ("cash-interest-rates", "/api/cash/interest-rates"),
    ("import-undo-status", "/api/portfolio/import-csv/undo"),
    ("alerts", "/api/alerts"),
    ("broker-connections", "/api/broker/trading212/status"),
    ("broker-ibkr-status", "/api/broker/ibkr/status"),
    ("broker-balances", "/api/broker/ibkr/balance"),
    ("options-trades", "/api/options/trades"),
    ("options-summary", "/api/options/summary"),
    ("options-by-underlying", "/api/options/by-underlying"),
    ("options-calendar", "/api/options/calendar"),
    ("polymarket-status", "/api/broker/polymarket/status"),
    ("polymarket-positions", "/api/polymarket/positions"),
    ("polymarket-summary", "/api/polymarket/summary"),
    ("discord", "/api/discord/webhook"),
    ("allocation-targets", "/api/allocation-targets"),
    ("allocation-target-drift", "/api/allocation-targets/drift"),
)


#: Mutating endpoints that take the portfolio as a query parameter and would
#: act on it. Each must 404 for Bob's portfolio -- including the ones that
#: reach third-party services, which must never even be called.
PORTFOLIO_SCOPED_MUTATIONS: tuple[tuple[str, str, str, Any], ...] = (
    ("import-preview", "POST", "/api/portfolio/import-csv/preview", None),
    ("import-commit", "POST", "/api/portfolio/import-csv/commit", None),
    ("import-undo", "POST", "/api/portfolio/import-csv/undo", None),
    ("transactions-delete-all", "DELETE", "/api/portfolio/transactions", None),
    ("broker-sync", "POST", "/api/broker/trading212/sync", None),
    ("broker-auto-sync", "POST", "/api/broker/trading212/auto-sync", {"enabled": True}),
    ("broker-disconnect", "DELETE", "/api/broker/trading212/connect", None),
    ("ibkr-auto-sync", "POST", "/api/broker/ibkr/auto-sync", {"enabled": True}),
    ("ibkr-disconnect", "DELETE", "/api/broker/ibkr/connect", None),
    ("ibkr-sync", "POST", "/api/broker/ibkr/sync", None),
    ("polymarket-sync", "POST", "/api/broker/polymarket/sync", None),
    ("polymarket-disconnect", "DELETE", "/api/broker/polymarket/connect", None),
    ("discord-create", "POST", "/api/discord/webhook",
     {"webhook_url": "https://discord.com/api/webhooks/stolen/token"}),
    ("discord-update", "PATCH", "/api/discord/webhook", {"notify_trades": False}),
    ("discord-delete", "DELETE", "/api/discord/webhook", None),
    ("discord-test", "POST", "/api/discord/webhook/test", {"message": "stolen"}),
    ("jobs-alert-check", "POST", "/api/alerts/check", None),
    ("cash-interest-rates", "PUT", "/api/cash/interest-rates",
     {"rates": [{"currency": "USD", "annual_rate": 0.9, "enabled": True}]}),
    ("allocation-targets", "PUT", "/api/allocation-targets",
     {"targets": [{"ticker": "MSFT", "target_pct": "100"}]}),
)


#: Alice deleting her OWN rows must succeed -- the isolation contract is
#: "Bob's data is unreachable", not "nothing is writable". Portfolios are
#: covered by a dedicated test because the API refuses to delete the last one.
OWN_DELETE_CASES: tuple[tuple[str, str, Mapping[str, str] | None, int], ...] = (
    ("notes", "/api/notes/transaction/{alice_transaction}", ALICE_PORTFOLIO_PARAMS, 200),
    ("transactions", "/api/portfolio/transactions/{alice_transaction}", ALICE_PORTFOLIO_PARAMS, 200),
    ("benchmarks", "/api/analytics/benchmarks/{alice_benchmark}", ALICE_PORTFOLIO_PARAMS, 200),
    ("cash", "/api/cash/{alice_cash}", ALICE_PORTFOLIO_PARAMS, 200),
    ("watchlist-items",
     "/api/watchlists/{alice_watchlist}/items/{alice_watchlist_item}", None, 200),
    ("watchlists", "/api/watchlists/{alice_watchlist}", None, 200),
    ("alerts", "/api/alerts/{alice_alert}", ALICE_PORTFOLIO_PARAMS, 200),
    ("user-settings", "/api/assistant/config", None, 200),
    ("discord", "/api/discord/webhook", ALICE_PORTFOLIO_PARAMS, 200),
)


#: Own-side counterparts of PORTFOLIO_SCOPED_MUTATIONS that reach no external
#: service, so the matrix proves each route works for its owner and 404s for
#: everyone else. (The network-bound sync routes are proven against their own
#: workspace in tests/postgres/test_integration_tenancy.py, which stubs the
#: upstream HTTP calls.)
OWN_MUTATIONS: tuple[tuple[str, str, str, Any, int], ...] = (
    ("cash-interest-rates", "PUT", "/api/cash/interest-rates",
     {"rates": [{"currency": "USD", "annual_rate": 0.02, "enabled": True}]}, 200),
    ("broker-auto-sync", "POST", "/api/broker/trading212/auto-sync", {"enabled": True}, 200),
    ("ibkr-auto-sync", "POST", "/api/broker/ibkr/auto-sync", {"enabled": True}, 200),
    ("jobs-alert-check", "POST", "/api/alerts/check", None, 200),
    ("broker-disconnect", "DELETE", "/api/broker/trading212/connect", None, 200),
    ("ibkr-disconnect", "DELETE", "/api/broker/ibkr/connect", None, 200),
    ("polymarket-disconnect", "DELETE", "/api/broker/polymarket/connect", None, 200),
    ("transactions-delete-all", "DELETE", "/api/portfolio/transactions", None, 200),
    ("allocation-targets", "PUT", "/api/allocation-targets",
     {"targets": [{"ticker": "MSFT", "target_pct": "100"}]}, 200),
)


#: CSRF-gated routes: a valid session with no CSRF header must be 403, never a
#: silent success and never the 404 the tenancy layer uses.
CSRF_GATED: tuple[tuple[str, str, str, Any], ...] = (
    ("portfolios-create", "POST", "/api/portfolios", {"name": "csrf probe"}),
    ("portfolios-pending-import", "POST", "/api/portfolios/pending-import", None),
    ("portfolios-activate", "POST", "/api/portfolios/{alice_portfolio}/activate", None),
    ("portfolios-update", "PATCH", "/api/portfolios/{alice_portfolio}", {"name": "csrf probe"}),
    ("portfolios-delete", "DELETE", "/api/portfolios/{alice_portfolio}", None),
    ("assistant-key-set", "PUT", "/api/assistant/config",
     {"api_key": "csrf-probe-key", "model": "deepseek-chat"}),
    ("assistant-key-clear", "DELETE", "/api/assistant/config", None),
    ("discord-create", "POST", "/api/discord/webhook",
     {"webhook_url": "https://discord.com/api/webhooks/csrf/probe"}),
    ("discord-update", "PATCH", "/api/discord/webhook", {"notify_trades": False}),
    ("discord-delete", "DELETE", "/api/discord/webhook", None),
    ("allocation-targets", "PUT", "/api/allocation-targets",
     {"targets": [{"ticker": "MSFT", "target_pct": "100"}]}),
)


def resolve(template: str | None, ids: Mapping[str, str]) -> str | None:
    """Fill `{placeholder}` UUIDs into a templated URL or param value."""
    if template is None:
        return None
    return template.format(**ids)


def resolve_params(
    params: Mapping[str, str] | None,
    ids: Mapping[str, str],
) -> dict[str, str]:
    return {key: resolve(value, ids) for key, value in (params or {}).items()}
