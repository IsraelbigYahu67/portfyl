"""Discovers broker formats in importers/formats/ (one module per broker)."""
from __future__ import annotations

import importlib
import logging
import pkgutil

from importers import formats as _formats_package
from importers.base import ImportFile, ImportFormat

logger = logging.getLogger(__name__)


class AmbiguousFormat(ValueError):
    pass


def _load_formats() -> tuple[ImportFormat, ...]:
    found: list[ImportFormat] = []
    for info in sorted(pkgutil.iter_modules(_formats_package.__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue  # shared helpers of a broker family, not a format
        module = importlib.import_module(f"importers.formats.{info.name}")
        fmt = getattr(module, "FORMAT", None)
        if isinstance(fmt, ImportFormat):
            found.append(fmt)
    keys = [fmt.key for fmt in found]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise RuntimeError(f"Duplicate import format keys: {duplicates}")
    return tuple(found)


FORMATS: tuple[ImportFormat, ...] = _load_formats()


def detect_format(file: ImportFile) -> ImportFormat | None:
    matches = []
    for fmt in FORMATS:
        try:
            if fmt.detect(file):
                matches.append(fmt)
        except Exception:
            # A detector must never break another format's upload.
            logger.warning("Import format %s detector failed", fmt.key, exc_info=True)
    if len(matches) > 1:
        names = ", ".join(fmt.format_name for fmt in matches)
        raise AmbiguousFormat(f"File matches several broker formats: {names}")
    return matches[0] if matches else None
