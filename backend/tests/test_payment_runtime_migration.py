from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REVISION = "0011_remove_payment_runtime"


def _stable(value):
    if isinstance(value, (str, bool, int, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_stable(item) for item in value)
    return str(value)


class _OperationRecorder:
    """Record the migration's complete operation list without a database."""

    def __init__(self):
        self.operations = []

    def drop_table(self, table):
        self.operations.append(("drop_table", table))

    def create_table(self, table, *columns, **kwargs):
        self.operations.append(("create_table", table))

    def create_index(self, name, table, columns, **kwargs):
        options = tuple(sorted((key, _stable(value)) for key, value in kwargs.items()))
        self.operations.append(
            ("create_index", name, table, tuple(columns), options)
        )

    def execute(self, statement):
        self.operations.append(("execute", " ".join(str(statement).split())))


def _revision_module():
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_revision(REVISION).module


def _record_operations(monkeypatch, direction):
    recorder = _OperationRecorder()
    revision_module = _revision_module()
    monkeypatch.setattr(revision_module, "op", recorder)
    getattr(revision_module, direction)()
    return recorder.operations


def _index(name, table, columns, **kwargs):
    options = tuple(sorted(kwargs.items()))
    return ("create_index", name, table, tuple(columns), options)


def _execute(statement):
    return ("execute", " ".join(statement.split()))


def _tenant_operations(table):
    workspace = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
    return [
        _execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} "
            "TO portfyl_runtime"
        ),
        _execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'),
        _execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'),
        _execute(
            f"CREATE POLICY {table}_workspace_policy ON {table} "
            f"USING (workspace_id = {workspace}) "
            f"WITH CHECK (workspace_id = {workspace})"
        ),
    ]


def test_upgrade_operation_set_only_drops_payment_runtime_tables(monkeypatch):
    assert _record_operations(monkeypatch, "upgrade") == [
        ("drop_table", "billing_actions"),
        ("drop_table", "stripe_events"),
        ("drop_table", "trial_grants"),
        ("drop_table", "subscriptions"),
        ("drop_table", "billing_customers"),
    ]


def test_downgrade_operation_set_only_recreates_payment_runtime(monkeypatch):
    expected = [
        ("create_table", "billing_customers"),
        _index(
            "ix_billing_customers_workspace_id",
            "billing_customers",
            ["workspace_id"],
        ),
        _index(
            "ix_billing_customers_stripe_customer_id",
            "billing_customers",
            ["stripe_customer_id"],
            unique=True,
        ),
        ("create_table", "subscriptions"),
        _index(
            "ix_subscriptions_public_id",
            "subscriptions",
            ["public_id"],
            unique=True,
        ),
        _index("ix_subscriptions_workspace_id", "subscriptions", ["workspace_id"]),
        _index(
            "ix_subscriptions_stripe_subscription_id",
            "subscriptions",
            ["stripe_subscription_id"],
            unique=True,
        ),
        _index("ix_subscriptions_status", "subscriptions", ["status"]),
        _index("ix_subscriptions_ended_at", "subscriptions", ["ended_at"]),
        _index(
            "uq_subscription_live_workspace",
            "subscriptions",
            ["workspace_id"],
            unique=True,
            postgresql_where="ended_at IS NULL",
        ),
        ("create_table", "trial_grants"),
        _index(
            "ix_trial_grants_public_id",
            "trial_grants",
            ["public_id"],
            unique=True,
        ),
        _index("ix_trial_grants_workspace_id", "trial_grants", ["workspace_id"]),
        _index(
            "ix_trial_grants_activated_by_user_id",
            "trial_grants",
            ["activated_by_user_id"],
        ),
        _index("ix_trial_grants_ends_at", "trial_grants", ["ends_at"]),
        ("create_table", "stripe_events"),
        _index(
            "ix_stripe_events_stripe_event_id",
            "stripe_events",
            ["stripe_event_id"],
            unique=True,
        ),
        _index("ix_stripe_events_event_type", "stripe_events", ["event_type"]),
        _index("ix_stripe_events_object_id", "stripe_events", ["object_id"]),
        _index("ix_stripe_events_status", "stripe_events", ["status"]),
        _index(
            "ix_stripe_events_next_attempt_at",
            "stripe_events",
            ["next_attempt_at"],
        ),
        ("create_table", "billing_actions"),
        _index(
            "ix_billing_actions_public_id",
            "billing_actions",
            ["public_id"],
            unique=True,
        ),
        _index("ix_billing_actions_workspace_id", "billing_actions", ["workspace_id"]),
        _index("ix_billing_actions_actor_user_id", "billing_actions", ["actor_user_id"]),
    ]
    for table in (
        "billing_customers",
        "subscriptions",
        "trial_grants",
        "billing_actions",
    ):
        expected.extend(_tenant_operations(table))
    expected.append(
        _execute("GRANT SELECT, INSERT, UPDATE ON TABLE stripe_events TO portfyl_runtime")
    )

    assert _record_operations(monkeypatch, "downgrade") == expected
