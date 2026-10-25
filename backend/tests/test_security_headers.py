"""backend/security_headers.py: the SecurityHeadersMiddleware that stamps a
Content-Security-Policy (plus nosniff/Referrer-Policy) on rendered HTML only,
exercised against a minimal FastAPI fixture so each check is isolated."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.testclient import TestClient

from security_headers import SecurityHeadersMiddleware, build_content_security_policy


NO_ENV: dict[str, str] = {}
AUTH_ENV = {"PORTFYL_FIREBASE_AUTH_DOMAIN": "portfyl-prod.firebaseapp.com"}


def _make_app(env: dict[str, str] = NO_ENV) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, env=env)

    @app.get("/html")
    def html():
        return HTMLResponse("<html></html>")

    @app.get("/api/data")
    def api_data():
        return JSONResponse({"ok": True})

    @app.get("/assets/logo.png")
    def image():
        return Response(content=b"binary", media_type="image/png")

    @app.get("/html-with-existing-csp")
    def html_with_existing_csp():
        response = HTMLResponse("<html></html>")
        response.headers["Content-Security-Policy"] = "default-src *"
        return response

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


def test_html_response_gets_the_exact_approved_csp(client):
    response = client.get("/html")
    assert response.headers["content-security-policy"] == build_content_security_policy(NO_ENV)


def test_html_response_gets_nosniff_and_referrer_policy(client):
    response = client.get("/html")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_json_api_response_has_no_security_headers(client):
    response = client.get("/api/data")
    assert "content-security-policy" not in response.headers
    assert "x-content-type-options" not in response.headers
    assert "referrer-policy" not in response.headers


def test_static_image_response_has_no_security_headers(client):
    response = client.get("/assets/logo.png")
    assert "content-security-policy" not in response.headers
    assert "x-content-type-options" not in response.headers
    assert "referrer-policy" not in response.headers


def test_pre_existing_csp_is_replaced_by_the_approved_value_not_appended(client):
    response = client.get("/html-with-existing-csp")
    csp_values = response.headers.get_list("content-security-policy")
    assert csp_values == [build_content_security_policy(NO_ENV)]
    assert "default-src *" not in csp_values[0]


def test_policy_allows_eu_posthog_hosts_and_excludes_us_posthog(client):
    policy = build_content_security_policy(NO_ENV)
    assert "https://eu.i.posthog.com" in policy
    assert "https://eu-assets.i.posthog.com" in policy
    assert "us.i.posthog.com" not in policy
    assert "app.posthog.com" not in policy


def test_policy_script_src_is_self_only_no_unsafe_eval(client):
    policy = build_content_security_policy(NO_ENV)
    assert "unsafe-eval" not in policy
    script_src = next(d for d in policy.split("; ") if d.startswith("script-src"))
    assert script_src == "script-src 'self'"


def test_policy_connect_src_has_no_bare_wildcard(client):
    policy = build_content_security_policy(NO_ENV)
    connect_src = next(d for d in policy.split("; ") if d.startswith("connect-src"))
    assert "*" not in connect_src.split()


def _directive(policy: str, name: str) -> str | None:
    return next((d for d in policy.split("; ") if d.split(" ", 1)[0] == name), None)


def test_without_auth_domain_policy_has_no_frame_src_or_google_scripts():
    policy = build_content_security_policy(NO_ENV)
    assert _directive(policy, "frame-src") is None
    assert "apis.google.com" not in policy


def test_auth_domain_enables_firebase_popup_hosts_only():
    policy = build_content_security_policy(AUTH_ENV)
    assert _directive(policy, "script-src") == "script-src 'self' https://apis.google.com"
    assert _directive(policy, "frame-src") == "frame-src https://portfyl-prod.firebaseapp.com"
    # Embedding Portfyl itself stays forbidden.
    assert _directive(policy, "frame-ancestors") == "frame-ancestors 'none'"
    assert "unsafe-eval" not in policy


def test_only_the_local_edition_may_frame_itself():
    assert _directive(build_content_security_policy({"PORTFYL_EDITION": "local"}), "frame-ancestors") == "frame-ancestors 'self'"
    for env in (NO_ENV, {"PORTFYL_EDITION": "cloud"}, {"PORTFYL_EDITION": "preview"}):
        assert _directive(build_content_security_policy(env), "frame-ancestors") == "frame-ancestors 'none'"


def test_auth_domain_is_normalized():
    policy = build_content_security_policy(
        {"PORTFYL_FIREBASE_AUTH_DOMAIN": "  Portfyl-Prod.FirebaseApp.com "}
    )
    assert _directive(policy, "frame-src") == "frame-src https://portfyl-prod.firebaseapp.com"


@pytest.mark.parametrize("value", [
    "",
    "   ",
    "evil.com; script-src *",
    "https://portfyl-prod.firebaseapp.com",
    "portfyl-prod.firebaseapp.com/__/auth",
    "portfyl-prod.firebaseapp.com:443",
    "*.firebaseapp.com",
    "localhost",
    "portfyl prod.firebaseapp.com",
    "-bad.firebaseapp.com",
])
def test_invalid_auth_domain_fails_closed_to_the_strict_policy(value: str):
    policy = build_content_security_policy({"PORTFYL_FIREBASE_AUTH_DOMAIN": value})
    assert policy == build_content_security_policy(NO_ENV)


def test_middleware_stamps_the_auth_domain_policy():
    response = TestClient(_make_app(AUTH_ENV)).get("/html")
    assert response.headers["content-security-policy"] == build_content_security_policy(AUTH_ENV)
    assert "frame-src https://portfyl-prod.firebaseapp.com" in response.headers["content-security-policy"]


def test_script_src_never_allows_inline_scripts():
    for env in (NO_ENV, AUTH_ENV):
        script_src = _directive(build_content_security_policy(env), "script-src")
        assert "'unsafe-inline'" not in script_src


def test_spa_shell_has_no_inline_scripts_the_policy_would_block():
    # The policy above blocks inline <script> blocks, so the SPA shell must
    # load everything (including the pre-paint theme snippet,
    # frontend/public/theme-init.js) from same-origin files.
    from html.parser import HTMLParser
    from pathlib import Path

    index_html = Path(__file__).resolve().parents[2] / "frontend" / "index.html"

    class _ScriptCollector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.scripts: list[dict[str, str | None]] = []

        def handle_starttag(self, tag, attrs):
            if tag == "script":
                self.scripts.append(dict(attrs))

    collector = _ScriptCollector()
    collector.feed(index_html.read_text(encoding="utf-8"))
    assert collector.scripts, "expected index.html to load scripts"
    assert all(attrs.get("src") for attrs in collector.scripts), collector.scripts
    assert {"src": "/theme-init.js"} in collector.scripts
