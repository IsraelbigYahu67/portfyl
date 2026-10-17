from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import ibkr_ledger
from ibkr_ledger import apply_flex_ledger
from importers.instruments import DefaultInstrumentResolver
from importers.openfigi import OpenFigiUnavailable
from models import BrokerConnection, OptionsTrade, Transaction
from private_loop import run_on_private_loop
from routers import ibkr as ibkr_router
from tests.helpers import make_txn

FIXTURE = (Path(__file__).parent / "fixtures" / "brokers" / "ibkr" / "flex_2025_sample.xml").read_text()
RESOLVER = DefaultInstrumentResolver(figi=None)
# The options sync stores closed open/close pairs only.
OPTION_PAIR = (
    '<Trade assetCategory="OPT" underlyingSymbol="AAPL" strike="200" expiry="20250620" putCall="C" '
    'quantity="1" tradePrice="3" tradeDate="20250401" openCloseIndicator="O" buySell="BUY" '
    'multiplier="100" currency="USD" ibOrderID="1" ibCommission="-1" transactionID="9101" '
    'levelOfDetail="EXECUTION"/>'
    '<Trade assetCategory="OPT" underlyingSymbol="AAPL" strike="200" expiry="20250620" putCall="C" '
    'quantity="-1" tradePrice="4" tradeDate="20250501" openCloseIndicator="C" buySell="SELL" '
    'multiplier="100" currency="USD" ibOrderID="2" ibCommission="-1" transactionID="9102" '
    'levelOfDetail="EXECUTION"/>'
)
WITH_OPTIONS = FIXTURE.replace("</Trades>", OPTION_PAIR + "</Trades>")


@pytest.fixture(autouse=True)
def _no_network_fx(monkeypatch):
    monkeypatch.setattr("routers.portfolio.bulk_fetch_fx", lambda keys: {})


def _txns(db, portfolio):
    return db.query(Transaction).filter(Transaction.portfolio_id == portfolio.id).all()


def test_sync_imports_once_and_is_idempotent(db_session, default_portfolio):
    first = apply_flex_ledger(db_session, default_portfolio, FIXTURE, resolver=RESOLVER)
    db_session.commit()
    second = apply_flex_ledger(db_session, default_portfolio, FIXTURE, resolver=RESOLVER)
    db_session.commit()
    assert first["status"] == "imported" and first["imported"] > 0
    assert second["imported"] == 0 and second["already_present"] == first["imported"]
    rows = _txns(db_session, default_portfolio)
    assert len(rows) == first["imported"]
    assert {row.source for row in rows} == {"ibkr"}
    assert {"AAPL", "VWCE.DE", "NVDA"} <= {row.ticker for row in rows if row.ticker}


def test_imported_rows_carry_czk_fx(db_session, default_portfolio):
    apply_flex_ledger(db_session, default_portfolio, FIXTURE, resolver=RESOLVER)
    db_session.commit()
    [buy] = [r for r in _txns(db_session, default_portfolio) if r.type == "buy"]
    assert buy.fx_to_czk == pytest.approx(23.10)
    [deposit] = [r for r in _txns(db_session, default_portfolio) if r.type == "deposit"]
    assert deposit.fx_to_czk == 1.0


def test_missing_sections_changes_nothing(db_session, default_portfolio):
    result = apply_flex_ledger(db_session, default_portfolio,
                               "<FlexQueryResponse><FlexStatements/></FlexQueryResponse>", resolver=RESOLVER)
    assert result["status"] == "sections_missing" and _txns(db_session, default_portfolio) == []


def test_manual_rows_for_same_ticker_block_import(db_session, default_portfolio):
    db_session.add(make_txn("AAPL", "buy", 1, 100, source="csv", portfolio_id=default_portfolio.id))
    db_session.commit()
    result = apply_flex_ledger(db_session, default_portfolio, FIXTURE, resolver=RESOLVER)
    assert result["status"] == "needs_review" and "AAPL" in result["errors"][0]
    assert len(_txns(db_session, default_portfolio)) == 1


def test_parser_errors_block_import(db_session, default_portfolio):
    bad = FIXTURE.replace('type="Other Fees"', 'type="Mystery"')
    result = apply_flex_ledger(db_session, default_portfolio, bad, resolver=RESOLVER)
    assert result["status"] == "needs_review" and _txns(db_session, default_portfolio) == []


def test_upload_then_sync_does_not_duplicate(db_session, default_portfolio, monkeypatch):
    """An XML upload and the Flex sync share source and event ids."""
    from routers import portfolio as portfolio_router
    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: RESOLVER)
    parsed = portfolio_router._parse_import_content(FIXTURE.encode(), "2025.xml")
    db_session.add_all(portfolio_router._prepare_import_transactions(parsed.rows, default_portfolio))
    db_session.commit()
    result = apply_flex_ledger(db_session, default_portfolio, FIXTURE, resolver=RESOLVER)
    assert result["imported"] == 0 and result["already_present"] == len(parsed.rows)


# --- _run_ibkr_sync wiring --------------------------------------------------


def _connect(db, portfolio, **kw):
    conn = BrokerConnection(workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
                            broker="ibkr", api_key="token-0000000000", api_secret="123456",
                            environment="live", **kw)
    db.add(conn)
    db.commit()
    return conn


def _run_sync(db, portfolio, xml=WITH_OPTIONS):
    with patch.object(ibkr_router, "_send_flex_request", AsyncMock(return_value="REF")), \
         patch.object(ibkr_router, "_poll_flex_statement", AsyncMock(return_value=xml)), \
         patch("importers.instruments.DefaultInstrumentResolver.from_env", return_value=RESOLVER):
        return run_on_private_loop(ibkr_router._run_ibkr_sync, db, portfolio.workspace_id, portfolio.id)


def test_flex_sync_writes_stocks_and_still_syncs_options(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    result = _run_sync(db_session, default_portfolio)
    assert result["ledger"]["status"] == "imported" and result["ledger"]["imported"] > 0
    assert any(r.type == "buy" and r.ticker == "AAPL" for r in _txns(db_session, default_portfolio))
    assert db_session.query(OptionsTrade).filter(OptionsTrade.portfolio_id == default_portfolio.id).count() == 1


def test_flex_sync_review_flags_connection_but_keeps_options(db_session, default_portfolio):
    conn = _connect(db_session, default_portfolio)
    db_session.add(make_txn("AAPL", "buy", 1, 100, source="csv", portfolio_id=default_portfolio.id))
    db_session.commit()
    result = _run_sync(db_session, default_portfolio)
    db_session.refresh(conn)
    assert result["ledger"]["status"] == "needs_review"
    assert conn.needs_attention is True and "AAPL" in conn.last_error
    assert db_session.query(OptionsTrade).filter(OptionsTrade.portfolio_id == default_portfolio.id).count() == 1


def test_clean_sync_clears_an_earlier_review_flag(db_session, default_portfolio):
    conn = _connect(db_session, default_portfolio, needs_attention=True, last_error="old review")
    _run_sync(db_session, default_portfolio)
    db_session.refresh(conn)
    assert conn.needs_attention is False and conn.last_error is None


def test_openfigi_outage_defers_ledger_without_failing_sync(db_session, default_portfolio, monkeypatch):
    _connect(db_session, default_portfolio)

    def unavailable(*_args, **_kwargs):
        raise OpenFigiUnavailable("Instrument lookup is rate-limited")
    monkeypatch.setattr(ibkr_ledger, "parse_flex_statement", unavailable)
    result = _run_sync(db_session, default_portfolio)
    assert result["ledger"]["status"] == "deferred"
    assert _txns(db_session, default_portfolio) == []


def test_options_only_statement_keeps_working(db_session, default_portfolio):
    _connect(db_session, default_portfolio)
    xml = ("<FlexQueryResponse><FlexStatements><FlexStatement><Trades>"
           f"{OPTION_PAIR}</Trades></FlexStatement></FlexStatements></FlexQueryResponse>")
    result = _run_sync(db_session, default_portfolio, xml)
    assert result["ledger"] == {"status": "imported", "imported": 0, "already_present": 0, "errors": []}
    assert result["imported"] == 1
