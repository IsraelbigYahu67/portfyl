"""Behavioral checks for the standalone repository statistics report."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import code_stats
from code_stats import Record, collect, render, summarize


TOKENS = (
    "DATE", "LINES", "CHARS", "COUNT", "NONBLANK", "HEAD", "GROUPS",
    "TOTAL", "BARS", "TESTSHARE", "LANGS", "LARGEST", "EXTENSIONS",
)
TEMPLATE = "\n".join(f"{token}=%%{token}%%" for token in TOKENS)


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
    )


def write(root: Path, name: str, content: str = "value = 1\n") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "--quiet")
    return tmp_path


def test_collect_includes_tracked_and_untracked_source_once(repo: Path) -> None:
    write(repo, "backend/app/main.py")
    git(repo, "add", "backend/app/main.py")
    write(repo, "frontend/src/main.tsx")
    write(repo, "scripts/rebuild.ps1")
    write(repo, "README.md")

    records = collect(repo)

    assert isinstance(records, tuple)
    assert {item.path: item.group for item in records} == {
        "backend/app/main.py": "Backend",
        "frontend/src/main.tsx": "Frontend",
        "scripts/rebuild.ps1": "Ostatní kód a skripty",
    }
    assert len(records) == 3


def test_collect_excludes_ignored_generated_dependencies_and_deleted(repo: Path) -> None:
    write(repo, ".gitignore", "ignored/\n")
    write(repo, "ignored/hidden.py")
    removed = write(repo, "deleted.py")
    git(repo, "add", "deleted.py")
    removed.unlink()
    excluded = (
        "node_modules", "dist", "build", "coverage", ".venv", "venv",
        "__pycache__", ".firecrawl", ".playwright-mcp", "artifacts",
        "playwright-report", "test-results",
    )
    for directory in excluded:
        write(repo, f"nested/{directory}/generated.py")
    for name in (
        "docs/operations/code-stats.html",
        "docs/operations/code-stats.template.html", "bundle.min.js", "app.min.css",
    ):
        write(repo, name)
    write(repo, "keep.py")

    assert tuple(item.path for item in collect(repo)) == ("keep.py",)


@pytest.mark.parametrize("name", [
    "tests/check.py", "backend/test/check.py", "frontend/e2e/login.ts",
    "frontend/__tests__/widget.tsx", "backend/test_api.py",
    "frontend/widget.test.ts", "frontend/widget.spec.tsx", "backend/conftest.py",
])
def test_test_paths_take_precedence_over_application_group(repo: Path, name: str) -> None:
    write(repo, name)
    assert collect(repo)[0].group == "Testy"


@pytest.mark.parametrize(("content", "lines", "nonblank", "chars"), [
    ("", 0, 0, 0),
    ("\ufeffž😀\r\n \r\nlast", 3, 2, 11),
    ("x\n", 1, 1, 2),
    ("x", 1, 1, 1),
])
def test_counts_unicode_line_endings_bom_and_empty_files(
    repo: Path, content: str, lines: int, nonblank: int, chars: int,
) -> None:
    write(repo, "source.py", content)
    record = collect(repo)[0]
    assert (record.extension, record.lines, record.nonblank, record.chars) == (
        ".py", lines, nonblank, chars,
    )


def test_next_collection_reflects_source_edits(repo: Path) -> None:
    write(repo, "source.py", "old\n")
    before = collect(repo)
    write(repo, "source.py", "new\n\nmore\n")
    after = collect(repo)
    assert summarize(before) == (1, 1, 1, 4)
    assert summarize(after) == (1, 3, 2, 10)


def test_collect_rejects_invalid_utf8_instead_of_reporting_partial_totals(repo: Path) -> None:
    write(repo, "valid.py")
    (repo / "invalid.py").write_bytes(b"\xff\xfe")

    with pytest.raises(ValueError, match="invalid.py"):
        collect(repo)


def test_records_are_immutable_and_totals_are_additive() -> None:
    first = Record("app.py", "Backend", ".py", 4, 3, 20)
    second = Record("test_app.py", "Testy", ".py", 2, 1, 9)
    assert summarize((first, second)) == (2, 6, 4, 29)
    assert summarize(()) == (0, 0, 0, 0)
    with pytest.raises(FrozenInstanceError):
        first.lines = 99


def test_render_replaces_all_tokens_and_escapes_paths() -> None:
    records = (Record('frontend/<img>&".tsx', "Frontend", ".tsx", 2, 1, 9),)
    result = render(records, TEMPLATE, "2026-09-23")
    assert "%%" not in result
    assert "DATE=2026-09-23" in result
    assert "LINES=2" in result
    assert "CHARS=9" in result
    assert "COUNT=1" in result
    assert "NONBLANK=1" in result
    assert "<img>" not in result
    assert "frontend/&lt;img&gt;&amp;&quot;.tsx" in result


def test_render_empty_repository_has_zero_totals() -> None:
    result = render((), TEMPLATE, "2026-09-23")
    assert "%%" not in result
    assert "LINES=0" in result
    assert "CHARS=0" in result
    assert "COUNT=0" in result
    assert "NONBLANK=0" in result
    assert "nan" not in result.lower()


def test_generate_writes_current_totals_into_repository_template(repo: Path) -> None:
    write(repo, "docs/operations/code-stats.template.html", TEMPLATE)
    write(repo, "source.py", "one\n\ntwo\n")

    output = code_stats.generate(repo)

    assert output == repo / "docs/operations/code-stats.html"
    result = output.read_text(encoding="utf-8")
    assert "COUNT=1" in result
    assert "LINES=3" in result
    assert "NONBLANK=2" in result
    assert "CHARS=9" in result
    assert "%%" not in result


@pytest.mark.parametrize(("platform", "no_open"), [("nt", False), ("posix", False), ("nt", True)])
def test_main_generates_at_script_root_and_optionally_opens_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str, no_open: bool,
) -> None:
    script = tmp_path / "docs/operations/code_stats.py"
    report = tmp_path / "docs/operations/code-stats.html"
    generate = Mock(return_value=report)
    browser = Mock(return_value=True)
    startfile = Mock()
    monkeypatch.setattr(code_stats, "__file__", str(script))
    monkeypatch.setattr(code_stats, "generate", generate)
    monkeypatch.setattr(code_stats, "os", SimpleNamespace(name=platform, startfile=startfile))
    monkeypatch.setattr(code_stats.webbrowser, "open", browser)
    monkeypatch.setattr("sys.argv", [str(script)] + (["--no-open"] if no_open else []))

    assert code_stats.main() == 0

    generate.assert_called_once_with(tmp_path)
    if no_open:
        browser.assert_not_called()
        startfile.assert_not_called()
    elif platform == "nt":
        startfile.assert_called_once_with(str(report))
        browser.assert_not_called()
    else:
        browser.assert_called_once_with(report.resolve().as_uri())
        startfile.assert_not_called()


def test_main_does_not_open_stale_report_when_generation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    script = tmp_path / "docs/operations/code_stats.py"
    write(tmp_path, "docs/operations/code-stats.html", "stale report")
    browser = Mock()
    startfile = Mock()
    monkeypatch.setattr(code_stats, "__file__", str(script))
    monkeypatch.setattr(code_stats, "generate", Mock(side_effect=OSError("disk unavailable")))
    monkeypatch.setattr(code_stats, "os", SimpleNamespace(name="nt", startfile=startfile))
    monkeypatch.setattr(code_stats.webbrowser, "open", browser)
    monkeypatch.setattr("sys.argv", [str(script)])

    assert code_stats.main() == 1

    browser.assert_not_called()
    startfile.assert_not_called()
    assert "OSError" in capsys.readouterr().err


def test_main_reports_browser_launch_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    report = tmp_path / "code-stats.html"
    monkeypatch.setattr(code_stats, "generate", Mock(return_value=report))
    monkeypatch.setattr(code_stats, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(code_stats.webbrowser, "open", Mock(return_value=False))
    monkeypatch.setattr("sys.argv", ["code_stats.py"])

    assert code_stats.main() == 1
    assert "OSError" in capsys.readouterr().err
