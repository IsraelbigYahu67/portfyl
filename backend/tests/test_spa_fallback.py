from __future__ import annotations

import pytest
from fastapi import HTTPException

from main import _spa_file_response


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Portfyl</title>", encoding="utf-8")
    (tmp_path / "theme-init.js").write_text("// theme", encoding="utf-8")
    return str(tmp_path)


def test_client_routes_get_index_html_that_browsers_must_revalidate(dist):
    response = _spa_file_response("dashboard", dist)

    assert response.path.endswith("index.html")
    assert response.headers["cache-control"] == "no-cache"


def test_unhashed_public_files_are_revalidated_too(dist):
    response = _spa_file_response("theme-init.js", dist)

    assert response.path.endswith("theme-init.js")
    assert response.headers["cache-control"] == "no-cache"


def test_path_traversal_falls_back_to_index_html(dist):
    response = _spa_file_response("../secret.txt", dist)

    assert response.path.endswith("index.html")


def test_missing_build_is_a_404(tmp_path):
    with pytest.raises(HTTPException) as exc:
        _spa_file_response("dashboard", str(tmp_path))

    assert exc.value.status_code == 404
