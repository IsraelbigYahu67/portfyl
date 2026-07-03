"""Single source of identity + the app's password gate.

Identity: anything that needs the current user calls get_current_user(). The app
is single-user, so it returns the sentinel owner id "default" (the value the
startup migration stamps on every row). When real multi-user auth lands, only
get_current_user() changes.

Auth: one shared password (APP_PASSWORD) protects the whole app. A successful
login sets an HMAC-signed, httponly session cookie; verify_session() checks the
signature (constant-time) and the 30-day age on every request via the middleware
in main.py. There is no username -- the session just proves "the one user is
logged in", so the owner id stays "default".

Secrets come from the environment (APP_PASSWORD, SESSION_SECRET). Local dev falls
back to clearly-marked insecure defaults and logs a warning (never the value).
"""
import base64
import hashlib
import hmac
import logging
import os
import time

from fastapi import Request, Response

logger = logging.getLogger("snowball.auth")

DEFAULT_OWNER_ID = "default"

# --- secrets / config (env first, clearly-marked dev fallback) ----------------
_DEV_PASSWORD = "snowball-dev"  # obvious placeholder; never used once APP_PASSWORD is set
_DEV_SESSION_SECRET = "insecure-dev-session-secret-change-me"

APP_PASSWORD = os.getenv("APP_PASSWORD") or _DEV_PASSWORD
SESSION_SECRET = os.getenv("SESSION_SECRET") or _DEV_SESSION_SECRET

if not os.getenv("APP_PASSWORD"):
    logger.warning("APP_PASSWORD not set -- using an INSECURE dev password. Set APP_PASSWORD before deploying.")
if not os.getenv("SESSION_SECRET"):
    logger.warning("SESSION_SECRET not set -- using an INSECURE dev signing secret. Set SESSION_SECRET before deploying.")

SESSION_COOKIE = "sb_session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60  # 30 days, in seconds

# Secure cookies require HTTPS; localhost dev is HTTP, where a Secure cookie would
# be dropped. Default: secure only when a real APP_PASSWORD is configured (i.e. a
# deployment). Override explicitly with SESSION_COOKIE_SECURE=true/false.
_secure_override = os.getenv("SESSION_COOKIE_SECURE")
if _secure_override is not None:
    COOKIE_SECURE = _secure_override.strip().lower() in ("1", "true", "yes", "on")
else:
    COOKIE_SECURE = bool(os.getenv("APP_PASSWORD"))


# --- identity -----------------------------------------------------------------
def get_current_user() -> str:
    """FastAPI dependency: the current owner_id. Single-user, so always "default".

    Adding a `request: Request` parameter here later (to read the owner from the
    verified session) will not affect existing `Depends(get_current_user)` call
    sites -- FastAPI injects by dependency, not by signature.
    """
    return DEFAULT_OWNER_ID


# --- password -----------------------------------------------------------------
def check_password(submitted: str) -> bool:
    """Constant-time comparison of the submitted password against APP_PASSWORD."""
    return hmac.compare_digest((submitted or "").encode("utf-8"), APP_PASSWORD.encode("utf-8"))


# --- scheduler machine token (Cloud Scheduler) --------------------------------
SCHEDULER_TOKEN = os.getenv("SCHEDULER_TOKEN")  # no dev fallback; unset => disabled


def check_scheduler_token(submitted: str) -> bool:
    """Constant-time check of the scheduler machine token. Returns False when
    SCHEDULER_TOKEN is unset, so the endpoint is inert in local dev and can never
    be triggered without the configured secret."""
    if not SCHEDULER_TOKEN:
        return False
    return hmac.compare_digest((submitted or "").encode("utf-8"), SCHEDULER_TOKEN.encode("utf-8"))


# --- signed session cookie ----------------------------------------------------
def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64: str) -> str:
    mac = hmac.new(SESSION_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(mac)


def issue_session(owner_id: str = DEFAULT_OWNER_ID) -> str:
    """Build a signed cookie value: base64(owner:issued_at).base64(hmac-sha256)."""
    payload_b64 = _b64encode(f"{owner_id}:{int(time.time())}".encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_session(token: str) -> str | None:
    """Return the owner_id if the signature is valid and the token is not older
    than SESSION_MAX_AGE, else None. Signature check is constant-time."""
    if not token or token.count(".") != 1:
        return None
    payload_b64, sig = token.split(".", 1)
    if not hmac.compare_digest(sig, _sign(payload_b64)):
        return None
    try:
        owner_id, issued = _b64decode(payload_b64).decode("utf-8").rsplit(":", 1)
        if time.time() - int(issued) > SESSION_MAX_AGE:
            return None
        return owner_id
    except Exception:
        return None


def is_authenticated(request: Request) -> bool:
    return verify_session(request.cookies.get(SESSION_COOKIE, "")) is not None


def set_session_cookie(response: Response, owner_id: str = DEFAULT_OWNER_ID) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=issue_session(owner_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


# --- login page (server-rendered; no React, no external assets) ---------------
def login_page_html(error: bool = False) -> str:
    error_html = '<p class="err">Incorrect password. Try again.</p>' if error else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Portfyl - Sign in</title>
<style>
  :root {{ --brand:#059669; --brand-hover:#047857; --bg:#F8FBF9; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:var(--bg); color:#111827;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .card {{ background:#fff; padding:2rem 2.25rem; border-radius:16px; width:100%; max-width:360px;
          box-shadow:0 10px 30px rgba(0,0,0,.08); }}
  .brand {{ display:flex; align-items:center; gap:.5rem; font-weight:700; font-size:1.25rem; margin-bottom:1.25rem; }}
  .dot {{ width:14px; height:14px; border-radius:50%; background:var(--brand); display:inline-block; }}
  label {{ display:block; font-size:.85rem; font-weight:600; margin-bottom:.4rem; color:#374151; }}
  input {{ width:100%; padding:.7rem .8rem; border:1px solid #D1D5DB; border-radius:10px; font-size:1rem; }}
  input:focus {{ outline:none; border-color:var(--brand); box-shadow:0 0 0 3px rgba(5,150,105,.15); }}
  button {{ width:100%; margin-top:1rem; padding:.7rem; border:0; border-radius:10px; cursor:pointer;
           background:var(--brand); color:#fff; font-size:1rem; font-weight:600; }}
  button:hover {{ background:var(--brand-hover); }}
  .err {{ color:#DC2626; font-size:.85rem; margin:.75rem 0 0; }}
</style>
</head>
<body>
  <form class="card" method="post" action="/login">
    <div class="brand"><span class="dot"></span> Portfyl</div>
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" autofocus required />
    <button type="submit">Sign in</button>
    {error_html}
  </form>
</body>
</html>"""
