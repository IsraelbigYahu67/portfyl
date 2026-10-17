from models import BrokerConnection
from broker_sources import broker_of_source, portfolio_brokers, rows_broker
from routers import portfolios as portfolios_router
from tests.helpers import make_txn


def test_sources_map_to_brokers():
    assert broker_of_source("t212_api") == broker_of_source("t212_csv") == "trading212"
    for source in ("ibkr", "etoro", "degiro", "xtb", "schwab", "fidelity"):
        assert broker_of_source(source) == source
    assert broker_of_source("demo") == "demo"
    for own in ("csv", "manual", None, ""):
        assert broker_of_source(own) == "own"


def test_rows_broker_is_none_for_own_or_mixed_rows():
    assert rows_broker([{"source": "xtb"}, {"source": "xtb"}]) == "xtb"
    assert rows_broker([{"source": "t212_csv"}]) == "trading212"
    assert rows_broker([{"source": "csv"}]) is None
    assert rows_broker([{"source": "xtb"}, {"source": "degiro"}]) is None
    assert rows_broker([]) is None


def test_portfolio_brokers_combines_transactions_and_connections(db_session, default_portfolio):
    db_session.add_all([
        make_txn("AAPL", source="t212_csv", portfolio_id=default_portfolio.id),
        make_txn("MSFT", source="manual", portfolio_id=default_portfolio.id),
        BrokerConnection(workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
                         broker="ibkr", api_key="k" * 20, environment="live"),
    ])
    db_session.commit()
    assert portfolio_brokers(db_session, default_portfolio.workspace_id) == {
        default_portfolio.id: ["ibkr", "own", "trading212"],
    }


def test_portfolio_list_reports_brokers(db_session, default_portfolio, request_context):
    db_session.add(make_txn("AAPL", source="xtb", portfolio_id=default_portfolio.id))
    db_session.commit()
    [row] = portfolios_router.list_portfolios(context=request_context, db=db_session)
    assert row["brokers"] == ["xtb"]


def test_empty_portfolio_has_no_brokers(db_session, default_portfolio, request_context):
    [row] = portfolios_router.list_portfolios(context=request_context, db=db_session)
    assert row["brokers"] == []


def test_preview_names_the_file_broker(db_session, default_portfolio, request_context, monkeypatch):
    import io

    from fastapi import UploadFile

    from routers import portfolio as portfolio_router
    from tests.test_xtb_import import ROWS, RESOLVER, _workbook

    monkeypatch.setattr(portfolio_router, "get_instrument_resolver", lambda: RESOLVER)

    def preview(name, content):
        return portfolio_router.preview_import_csv(
            file=UploadFile(filename=name, file=io.BytesIO(content)), replace=False,
            db=db_session, portfolio=default_portfolio, _context=request_context,
        )

    assert preview("xtb.xlsx", _workbook(ROWS[:2]).content)["broker"] == "xtb"
    native = b"date,ticker,type,shares,price,currency\n2026-01-02,AAPL,buy,1,100,USD\n"
    assert preview("portfolio.csv", native)["broker"] is None
