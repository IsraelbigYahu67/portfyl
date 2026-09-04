"""One-off backfill: encrypt any plaintext secret column still present on a
database that predates the ciphertext columns added by
alembic/versions/0004_broker_secret_columns_expand.py (and, once Task 3
lands, the Discord webhook equivalent).

Sequencing (mirrors sqlite_to_postgres.py's dry-run/apply shape and
docs/operations/sqlite-to-neon-migration.md's rehearse-before-apply
discipline):

    1. `alembic upgrade head` through 0004_*_expand -- adds the new nullable
       ciphertext columns; old plaintext columns are untouched.
    2. Run this script with `--dry-run` (the default) to see what it would
       encrypt, then `--apply` to actually write ciphertext.
    3. Confirm the reconciliation report shows zero remaining plaintext rows.
    4. `alembic upgrade head` through 0005_*_contract -- makes the ciphertext
       columns required and drops the old plaintext columns. This step is
       destructive (plaintext is gone for good) and must not run before step
       3 confirms every row was backfilled.

This script talks to the plaintext columns via raw SQL (`text()`), never
through the ORM `BrokerConnection` model -- the model only maps the
ciphertext columns (see models.py), so the plaintext values are reachable
here and nowhere else in the running application.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import DatabaseSettings, build_engine  # noqa: E402
from edition import edition_from_env  # noqa: E402
from secrets_crypto import build_secret_cipher  # noqa: E402


@dataclass
class TableReport:
    table: str
    total_plaintext_rows: int
    encrypted: int = 0
    already_encrypted: int = field(default=0)


def _encrypt_broker_connections(engine: Engine, cipher, *, apply: bool) -> TableReport:
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, api_key, api_secret FROM broker_connections "
            "WHERE api_key_ciphertext IS NULL"
        )).all()
        already = conn.execute(text(
            "SELECT count(*) FROM broker_connections WHERE api_key_ciphertext IS NOT NULL"
        )).scalar_one()

    report = TableReport(
        table="broker_connections",
        total_plaintext_rows=len(rows),
        already_encrypted=already,
    )
    if not apply:
        return report

    with engine.begin() as conn:
        for row in rows:
            key_enc = cipher.encrypt(row.api_key)
            secret_enc = cipher.encrypt(row.api_secret) if row.api_secret else None
            conn.execute(
                text(
                    "UPDATE broker_connections SET "
                    "api_key_ciphertext = :api_key_ciphertext, "
                    "api_key_key_version = :api_key_key_version, "
                    "api_secret_ciphertext = :api_secret_ciphertext, "
                    "api_secret_key_version = :api_secret_key_version "
                    "WHERE id = :id"
                ),
                {
                    "api_key_ciphertext": key_enc.ciphertext,
                    "api_key_key_version": key_enc.key_version,
                    "api_secret_ciphertext": secret_enc.ciphertext if secret_enc else None,
                    "api_secret_key_version": secret_enc.key_version if secret_enc else None,
                    "id": row.id,
                },
            )
            report.encrypted += 1
    return report


def run(database_url: str, *, apply: bool) -> list[TableReport]:
    settings = DatabaseSettings.from_env({"DATABASE_URL": database_url})
    engine = build_engine(settings)
    cipher = build_secret_cipher(os.environ, edition_from_env(os.environ))
    try:
        return [_encrypt_broker_connections(engine, cipher, apply=apply)]
    finally:
        engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="Target PostgreSQL URL (defaults to $DATABASE_URL)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write ciphertext (default is a dry run that only reports).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    reports = run(args.database_url, apply=args.apply)
    mode = "APPLY" if args.apply else "DRY RUN"
    for report in reports:
        print(
            f"[{mode}] {report.table}: {report.encrypted}/{report.total_plaintext_rows} "
            f"row(s) encrypted this run, {report.already_encrypted} already had ciphertext"
        )
    if not args.apply:
        print("Dry run only -- no rows were written. Re-run with --apply to write ciphertext.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
