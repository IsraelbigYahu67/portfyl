"""``main`` shares the application's mailer with the account-notice helper, so
a notice sent outside an e-mail route uses the same transport and health flag."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent

_SCRIPT = """
import main
from emails import notify

mailer = main.app.state.portfyl_mailer
assert mailer is not None, "mailer was not built"
assert notify._resolve_default_mailer() is mailer, "notify builds its own mailer"
print("shared")
"""


def test_main_shares_its_mailer_with_the_account_notice_helper():
    env = dict(os.environ)
    env.update(
        PORTFYL_EDITION="local",
        PORTFYL_EMAIL_TRANSPORT="console",
        PORTFYL_EMAIL_APP_URL="http://localhost:5173",
    )
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=_BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "shared" in result.stdout
