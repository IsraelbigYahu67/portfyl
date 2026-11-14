"""'Notify me when my broker is supported' (onboarding-flow plan, Task 3).
Router functions are called directly, as elsewhere in the fast suite; the HTTP
surface and tenant isolation are covered by tests/postgres/test_broker_requests_rls.py."""

import json

import pytest

from models import BrokerRequest
from routers.broker_requests import BrokerRequestPayload, create_broker_request


@pytest.fixture
def ctx(db_session, request_context):
    return db_session, request_context


def post(ctx, name):
    db, context = ctx
    response = create_broker_request(BrokerRequestPayload(broker_name=name), db=db, context=context)
    return response.status_code, json.loads(response.body)


def test_creates_normalized_request(ctx):
    assert post(ctx, "  trade   republic ") == (201, {"broker_name": "trade republic", "created": True})


def test_row_is_linked_to_workspace_and_user(ctx):
    db, context = ctx
    post(ctx, "Revolut")
    row = db.query(BrokerRequest).one()
    assert row.workspace_id == context.workspace.id
    assert row.user_id == context.user.id
    assert row.public_id is not None


def test_same_name_other_case_is_idempotent(ctx):
    post(ctx, "Revolut")
    assert post(ctx, "REVOLUT") == (200, {"broker_name": "Revolut", "created": False})
    assert ctx[0].query(BrokerRequest).count() == 1


def test_rejects_empty_and_too_long(ctx):
    assert post(ctx, "   ") == (422, {"code": "invalid_broker_name"})
    assert post(ctx, "x" * 61) == (422, {"code": "invalid_broker_name"})
    assert ctx[0].query(BrokerRequest).count() == 0


def test_sixty_characters_is_accepted(ctx):
    assert post(ctx, "x" * 60)[0] == 201


def test_length_is_checked_after_whitespace_is_collapsed(ctx):
    assert post(ctx, "a" + " " * 100 + "b") == (201, {"broker_name": "a b", "created": True})


def test_markup_is_stored_as_plain_text(ctx):
    assert post(ctx, "<script>")[1]["broker_name"] == "<script>"


def test_limit_per_workspace(ctx):
    for i in range(20):
        assert post(ctx, f"b{i}")[0] == 201
    assert post(ctx, "b21") == (429, {"code": "broker_request_limit"})
    assert ctx[0].query(BrokerRequest).count() == 20


def test_existing_name_still_idempotent_at_the_limit(ctx):
    for i in range(20):
        post(ctx, f"b{i}")
    assert post(ctx, "B3") == (200, {"broker_name": "b3", "created": False})
