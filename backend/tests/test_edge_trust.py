"""backend/edge_trust.py: the PORTFYL_EDGE_TOKEN origin-auth contract."""
from __future__ import annotations

import pytest
from starlette.requests import Request

import edge_trust
from edge_trust import UntrustedEdge, load_edge_token, verify_edge_token

_HEADER = "X-Portfyl-Edge-Token"


def _request(headers: list[tuple[str, str]]) -> Request:
    scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers]}
    return Request(scope)


def test_load_edge_token_rejects_blank():
    with pytest.raises(RuntimeError, match="PORTFYL_EDGE_TOKEN"):
        load_edge_token({"PORTFYL_EDGE_TOKEN": "   "})


def test_load_edge_token_rejects_missing():
    with pytest.raises(RuntimeError, match="PORTFYL_EDGE_TOKEN"):
        load_edge_token({})


def test_load_edge_token_returns_stripped_value():
    assert load_edge_token({"PORTFYL_EDGE_TOKEN": " secret-value "}) == "secret-value"


def test_local_edition_module_level_edge_token_is_none():
    assert edge_trust.EDGE_TOKEN is None


class TestVerifyEdgeToken:
    @pytest.fixture(autouse=True)
    def _token(self, monkeypatch):
        monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "correct-token")

    def test_valid_token_passes(self):
        verify_edge_token(_request([(_HEADER, "correct-token")]))  # does not raise

    def test_missing_header_raises(self):
        with pytest.raises(UntrustedEdge):
            verify_edge_token(_request([]))

    def test_wrong_token_raises(self):
        with pytest.raises(UntrustedEdge):
            verify_edge_token(_request([(_HEADER, "wrong-token")]))

    def test_duplicated_header_raises(self):
        req = _request([(_HEADER, "correct-token"), (_HEADER, "correct-token")])
        with pytest.raises(UntrustedEdge):
            verify_edge_token(req)


def test_untrusted_edge_response_shape():
    response = edge_trust.untrusted_edge_response()
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
