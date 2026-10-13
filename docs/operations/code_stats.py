"""Refresh the local code report using Git's file inventory (stdlib only)."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable

EXTENSIONS = frozenset({
    '.py', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.css', '.scss',
    '.html', '.sql', '.sh', '.ps1', '.bat', '.mako',
})
EXCLUDED_DIRS = frozenset({
    'node_modules', 'dist', 'build', 'coverage', '.venv', 'venv',
    '__pycache__', '.git', '.firecrawl', '.playwright-mcp', 'artifacts',
    'playwright-report', 'test-results',
})
REPORT_FILES = frozenset({
    'docs/operations/code-stats.html',
    'docs/operations/code-stats.template.html',
})
GROUPS = ('Backend', 'Frontend', 'Testy', 'Ostatní kód a skripty')
LANGUAGES = {
    '.py': 'Python', '.js': 'JavaScript', '.jsx': 'React / JSX',
    '.ts': 'TypeScript', '.tsx': 'React / TSX', '.mjs': 'JavaScript moduly',
    '.cjs': 'CommonJS', '.css': 'CSS', '.scss': 'SCSS', '.html': 'HTML',
    '.ps1': 'PowerShell', '.sql': 'SQL', '.bat': 'Batch',
    '.mako': 'Mako šablony', '.sh': 'Shell',
}


@dataclass(frozen=True)
class Record:
    path: str
    group: str
    extension: str
    lines: int
    nonblank: int
    chars: int


def category(path: Path) -> str:
    test_dirs = {'tests', 'test', 'e2e', '__tests__'}
    is_test = (
        bool(test_dirs.intersection(path.parts))
        or path.name.startswith('test_')
        or '.test.' in path.name or '.spec.' in path.name
        or path.name == 'conftest.py'
    )
    if is_test:
        return 'Testy'
    return {'backend': 'Backend', 'frontend': 'Frontend'}.get(
        path.parts[0], 'Ostatní kód a skripty'
    )


def count_file(root: Path, name: str) -> Record | None:
    relative = Path(name)
    path = root / relative
    if (
        not name or relative.as_posix() in REPORT_FILES
        or EXCLUDED_DIRS.intersection(relative.parts)
        or relative.suffix.lower() not in EXTENSIONS
        or relative.name.endswith(('.min.js', '.min.css'))
        or not path.is_file() or path.is_symlink()
        or not path.resolve().is_relative_to(root.resolve())
    ):
        return None
    try:
        with path.open(encoding='utf-8-sig', newline='') as source:
            content = source.read()
    except (OSError, UnicodeError) as error:
        raise ValueError(f'Nelze přečíst soubor: {name}') from error
    lines = content.splitlines()
    return Record(
        name, category(relative), relative.suffix.lower(), len(lines),
        sum(bool(line.strip()) for line in lines), len(content),
    )


def collect(root: Path) -> tuple[Record, ...]:
    result = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=root, check=True, capture_output=True, timeout=30,
    )
    names = sorted(set(result.stdout.decode('utf-8').split('\0')))
    return tuple(
        record for name in names if (record := count_file(root, name)) is not None
    )


def summarize(records: Iterable[Record]) -> tuple[int, int, int, int]:
    items = tuple(records)
    return (
        len(items), sum(r.lines for r in items),
        sum(r.nonblank for r in items), sum(r.chars for r in items),
    )


def fmt(value: int) -> str:
    return f'{value:,}'.replace(',', '\u00a0')


def row(label: str, values: Iterable[int]) -> str:
    cells = ''.join(f'<td>{fmt(value)}</td>' for value in values)
    return f'<tr><th scope="row">{escape(label)}</th>{cells}</tr>'


def bars(records: tuple[Record, ...], total: int) -> str:
    parts = []
    for group in GROUPS:
        percent = sum(r.lines for r in records if r.group == group) * 100 / (total or 1)
        display = f'{percent:.1f}'.replace('.', ',')
        parts.append(
            '<div class="bar-row"><div class="bar-label">'
            f'<span>{escape(group)}</span><span>{display} %</span></div>'
            '<div class="track">'
            f'<div class="fill" style="width:{percent:.4f}%"></div></div></div>'
        )
    return ''.join(parts)


def render(records: tuple[Record, ...], template: str, measured: str) -> str:
    count, lines, nonblank, chars = summarize(records)
    extensions = sorted(
        {r.extension for r in records},
        key=lambda ext: (-sum(r.lines for r in records if r.extension == ext), ext),
    )
    headings = ('Oblast', 'Soubory', 'Řádky celkem', 'Neprázdné řádky', 'Znaky')
    test_share = sum(r.lines for r in records if r.group == 'Testy') * 100 / (lines or 1)
    values = {
        'DATE': escape(measured), 'LINES': fmt(lines), 'CHARS': fmt(chars),
        'COUNT': fmt(count), 'NONBLANK': fmt(nonblank),
        'HEAD': '<tr>' + ''.join(f'<th scope="col">{h}</th>' for h in headings) + '</tr>',
        'GROUPS': ''.join(row(g, summarize(r for r in records if r.group == g)) for g in GROUPS),
        'TOTAL': row('Celkem', summarize(records)), 'BARS': bars(records, lines),
        'TESTSHARE': f'{test_share:.1f}'.replace('.', ','),
        'LANGS': ''.join(
            row(f'{LANGUAGES.get(ext, ext)} ({ext})', summarize(r for r in records if r.extension == ext))
            for ext in extensions
        ),
        'LARGEST': ''.join(
            row(r.path, (r.lines, r.chars))
            for r in sorted(records, key=lambda r: (-r.lines, r.path))[:10]
        ),
        'EXTENSIONS': ', '.join(sorted(EXTENSIONS)),
    }
    # Substitute only template tokens, never token-like text inside file names.
    return re.sub(r'%%([A-Z]+)%%', lambda match: values[match[1]], template)


def generate(root: Path) -> Path:
    folder = root / 'docs' / 'operations'
    template = (folder / 'code-stats.template.html').read_text(encoding='utf-8')
    measured = datetime.now().astimezone().strftime('%d. %m. %Y v %H:%M:%S (%z)')
    page = render(collect(root), template, measured)
    output = folder / 'code-stats.html'
    output.write_text(page, encoding='utf-8')
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description='Refresh and open the Portfyl code report.')
    parser.add_argument('--no-open', action='store_true', help='Only update the HTML file.')
    args = parser.parse_args()
    try:
        output = generate(Path(__file__).resolve().parents[2])
        if not args.no_open:
            if os.name == 'nt':
                os.startfile(str(output))
            elif not webbrowser.open(output.as_uri()):
                raise OSError('Browser could not be opened.')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        # Keep filenames readable even in Windows consoles with legacy encoding.
        detail = str(error).encode('ascii', errors='backslashreplace').decode('ascii')
        print(f'Prehled nelze aktualizovat nebo otevrit ({type(error).__name__}). '
              'Overte Python, Git, UTF-8 soubory a pristup k projektu.', file=sys.stderr)
        print(detail, file=sys.stderr)
        return 1
    print('Prehled aktualizovan: docs/operations/code-stats.html')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
