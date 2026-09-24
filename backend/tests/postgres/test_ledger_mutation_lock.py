"""Real PostgreSQL coverage for the shared transaction-ledger mutex."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ledger_mutation import acquire_workspace_ledger_lock


def test_workspace_ledger_lock_blocks_a_second_writer(
    postgres_engine, matrix_tenants,
):
    workspace_id = matrix_tenants.alice.workspace_id
    with Session(postgres_engine) as first, Session(postgres_engine) as second:
        acquire_workspace_ledger_lock(first, workspace_id)
        second.execute(text("SET LOCAL lock_timeout = '100ms'"))

        with pytest.raises(OperationalError):
            acquire_workspace_ledger_lock(second, workspace_id)

        second.rollback()
        first.rollback()
