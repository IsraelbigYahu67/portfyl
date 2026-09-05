from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PAYMENT_TABLES = {
    "billing_actions",
    "billing_customers",
    "stripe_events",
    "subscriptions",
    "trial_grants",
}
RETAINED_PLAN_TABLES = {
    "notification_outbox",
    "usage_counters",
    "usage_reservations",
}


def _offline_config(monkeypatch) -> Config:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://portfyl_test:portfyl_test@localhost/test",
    )
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def test_upgrade_drops_only_payment_runtime_tables(monkeypatch, capsys):
    command.upgrade(
        _offline_config(monkeypatch),
        "0010_billing_entitlements:0011_remove_payment_runtime",
        sql=True,
    )

    sql = capsys.readouterr().out
    for table in PAYMENT_TABLES:
        assert f"DROP TABLE {table}" in sql
    for table in RETAINED_PLAN_TABLES:
        assert f"DROP TABLE {table}" not in sql


def test_downgrade_recreates_payment_tables_without_dropping_retained_plan_data(
    monkeypatch, capsys
):
    command.downgrade(
        _offline_config(monkeypatch),
        "0011_remove_payment_runtime:0010_billing_entitlements",
        sql=True,
    )

    sql = capsys.readouterr().out
    for table in PAYMENT_TABLES:
        assert f"CREATE TABLE {table}" in sql
    for table in RETAINED_PLAN_TABLES:
        assert f"DROP TABLE {table}" not in sql
