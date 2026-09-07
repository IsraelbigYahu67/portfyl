"""Execute due Portfyl workspace/account deletions.

Run this command from an external scheduler in cloud deployments or from the
local installation's scheduler. It emits a machine-readable summary and is
safe to retry.
"""

from __future__ import annotations

import json

from account_deletion import purge_due_workspace_deletions
from database import SessionLocal
from firebase_identity import FirebaseIdentityVerifier


def main() -> int:
    with SessionLocal() as db:
        summary = purge_due_workspace_deletions(
            db,
            FirebaseIdentityVerifier(),
        )
    print(json.dumps(summary, separators=(",", ":")))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
