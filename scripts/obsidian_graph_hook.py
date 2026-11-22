#!/usr/bin/env python3
"""Claude Code Stop hook: keep the Obsidian architecture graph current.

Configured in ``.claude/settings.json``. When a Claude session finishes a reply,
this checks whether any input of ``build_obsidian_architecture.py`` (backend
code, frontend code, docs, deploy/ops files) changed since the last run in this
worktree. If so it regenerates ``docs/architecture/generated/`` (only files
whose content changes are rewritten) and tells the user how many notes changed.

It never blocks or fails a session: every error is swallowed and it always
exits 0. The "last run" stamp lives inside the worktree's git dir, so each
worktree tracks its own state and nothing new appears in ``git status``.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (folder, suffixes) the generator reads; pruned dirs are skipped while walking.
WATCHED_DIRS = [
    ("backend", {".py", ".ini"}),
    ("frontend/src", {".js", ".jsx"}),
    ("docs", {".md"}),
    ("deploy", None),
    (".github/workflows", {".yml", ".yaml"}),
]
WATCHED_FILES = ["Dockerfile", "start.bat", "CLAUDE.md", "DESIGN.md", "README.md", "frontend/vite.config.js"]
PRUNE = {".venv", "venv", "node_modules", "__pycache__", "site-packages", "dist", ".obsidian", ".pytest_cache"}
GENERATED = ROOT / "docs" / "architecture" / "generated"


def newest_input_mtime() -> float:
    newest = 0.0
    for name in WATCHED_FILES:
        try:
            newest = max(newest, (ROOT / name).stat().st_mtime)
        except OSError:
            pass
    for folder, suffixes in WATCHED_DIRS:
        for dirpath, dirnames, filenames in os.walk(ROOT / folder):
            if Path(dirpath) == GENERATED:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in PRUNE]
            for fn in filenames:
                if suffixes is None or os.path.splitext(fn)[1] in suffixes:
                    try:
                        newest = max(newest, os.stat(os.path.join(dirpath, fn)).st_mtime)
                    except OSError:
                        pass
    return newest


def stamp_path() -> Path | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--git-path", "obsidian-graph.stamp"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    p = Path(out.stdout.strip())
    return p if p.is_absolute() else ROOT / p


def main() -> None:
    try:
        sys.stdin.read()  # Stop-hook payload; not needed
    except Exception:
        pass
    stamp = stamp_path()
    if stamp is None:
        return
    started = time.time()
    try:
        last = stamp.stat().st_mtime
    except OSError:
        last = 0.0
    if newest_input_mtime() <= last:
        return

    sys.path.insert(0, str(ROOT / "scripts"))
    import build_obsidian_architecture as gen

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        changed = gen.write_generated(verbose=False)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    os.utime(stamp, (started, started))  # edits made while we ran trigger the next run
    if changed:
        print(json.dumps({"systemMessage": (
            f"Architecture graph: {changed} file(s) refreshed in docs/architecture/generated/ "
            "- commit them together with the code change.")}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
