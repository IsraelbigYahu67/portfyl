"""What search engines may index: prerendered public pages on portfyl.com only,
the app shell never, nothing on any other host. See spa_serving.py and
docs/superpowers/plans/2026-11-09-portfyl-seo.md (Wave 1, S3)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import spa_serving
from main import _spa_file_response


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path / "robots.txt").write_text("User-agent: *\nDisallow: /api/\n", encoding="utf-8")
    (tmp_path / "sitemap.xml").write_text("<urlset/>", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"png")
    pages = tmp_path / "prerendered"
    (pages / "en").mkdir(parents=True)
    (pages / "de").mkdir()
    (pages / "index.html").write_text("<h1>Vaše investice.</h1>", encoding="utf-8")
    (pages / "en" / "index.html").write_text("<h1>Your investments.</h1>", encoding="utf-8")
    (pages / "de" / "index.html").write_text("<h1>Deine Investments.</h1>", encoding="utf-8")
    (tmp_path / ".vite").mkdir()
    (tmp_path / ".vite" / "manifest.json").write_text("{}", encoding="utf-8")
    return str(tmp_path)


PUBLIC = spa_serving.PUBLIC_HOST


@pytest.mark.parametrize(("path", "page"), [("", "prerendered/index.html"), ("en/", "prerendered/en/index.html"), ("de/", "prerendered/de/index.html")])
def test_public_pages_are_prerendered_and_indexable_on_the_public_host(dist, path, page):
    response = _spa_file_response(path, dist, host=PUBLIC)

    assert response.path.replace("\\", "/").endswith(page)
    assert "x-robots-tag" not in response.headers
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(("path", "query", "location"), [("en", "", "/en/"), ("de", "utm_source=x", "/de/?utm_source=x")])
def test_a_page_has_one_url_the_slashless_form_redirects(dist, path, query, location):
    response = _spa_file_response(path, dist, host=PUBLIC, query=query)

    assert response.status_code == 301
    assert response.headers["location"] == location


@pytest.mark.parametrize("path", ["dashboard", "login", "demo", "demo/allocation", "terms", "fr/", "en/extra", "nonsense"])
def test_every_other_route_gets_the_noindex_app_shell(dist, path):
    response = _spa_file_response(path, dist, host=PUBLIC)

    assert response.path.endswith("index.html")
    assert "prerendered" not in response.path
    assert response.headers["x-robots-tag"] == spa_serving.NOINDEX


@pytest.mark.parametrize("path", ["prerendered/en/index.html", "prerendered/index.html", ".vite/manifest.json"])
def test_build_bookkeeping_is_not_served_as_a_page(dist, path):
    response = _spa_file_response(path, dist, host=PUBLIC)

    assert response.path.endswith("index.html") and "prerendered" not in response.path
    assert response.headers["x-robots-tag"] == spa_serving.NOINDEX


def test_robots_and_sitemap_are_real_files_on_the_public_host(dist):
    robots = _spa_file_response("robots.txt", dist, host=PUBLIC)
    sitemap = _spa_file_response("sitemap.xml", dist, host=PUBLIC)

    assert robots.path.endswith("robots.txt")
    assert sitemap.path.endswith("sitemap.xml")
    assert "x-robots-tag" not in robots.headers


@pytest.mark.parametrize("host", [spa_serving.TRACKER_HOST, "portfyl-812512242326.europe-west1.run.app", "localhost", ""])
def test_other_hosts_disallow_everything_and_are_noindex(dist, host):
    robots = _spa_file_response("robots.txt", dist, host=host)
    logo = _spa_file_response("logo.png", dist, host=host)

    assert robots.body.decode() == spa_serving.DISALLOW_ALL_ROBOTS
    assert robots.headers["x-robots-tag"] == spa_serving.NOINDEX
    assert logo.headers["x-robots-tag"] == spa_serving.NOINDEX


def test_the_tracker_host_never_gets_the_landing_html(dist):
    response = _spa_file_response("", dist, host=spa_serving.TRACKER_HOST)

    assert response.path.endswith("index.html") and "prerendered" not in response.path
    assert response.headers["x-robots-tag"] == spa_serving.NOINDEX


def test_preview_hosts_still_render_landing_pages_but_noindex(dist):
    response = _spa_file_response("en/", dist, host="portfyl-812512242326.europe-west1.run.app")

    assert response.path.replace("\\", "/").endswith("prerendered/en/index.html")
    assert response.headers["x-robots-tag"] == spa_serving.NOINDEX


def test_path_traversal_cannot_leave_dist(dist):
    response = _spa_file_response("../secret.txt", dist, host=PUBLIC)

    assert response.path.endswith("index.html")


@pytest.mark.parametrize(
    ("headers", "host"),
    [
        ({"host": "portfyl.com"}, "portfyl.com"),
        ({"host": "PORTFYL.com:443"}, "portfyl.com"),
        ({"host": "portfyl-1.europe-west1.run.app", "x-forwarded-host": "app.portfyl.com"}, "app.portfyl.com"),
        ({"x-forwarded-host": "app.portfyl.com, proxy.internal"}, "app.portfyl.com"),
        ({}, ""),
    ],
)
def test_request_host_prefers_the_worker_forwarded_host(headers, host):
    assert spa_serving.request_host(headers) == host


def test_the_spa_fallback_route_applies_the_rules_end_to_end(dist):
    """The real FastAPI route, not just the helper: host and query come from the request."""
    app = FastAPI()

    @app.get("/{full_path:path}")
    def spa(full_path: str, request: Request):
        return _spa_file_response(full_path, dist, host=spa_serving.request_host(request.headers), query=request.url.query)

    client = TestClient(app)
    landing = client.get("/en/", headers={"host": "portfyl.com"})
    redirect = client.get("/de?x=1", headers={"host": "portfyl.com"}, follow_redirects=False)
    tracker = client.get("/", headers={"host": "portfyl-1.run.app", "x-forwarded-host": "app.portfyl.com"})

    assert landing.status_code == 200 and "Your investments." in landing.text
    assert "x-robots-tag" not in landing.headers
    assert redirect.status_code == 301 and redirect.headers["location"] == "/de/?x=1"
    assert tracker.headers["x-robots-tag"] == spa_serving.NOINDEX and "Vaše" not in tracker.text
