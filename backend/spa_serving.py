"""How the built SPA (frontend/dist) is served, and what search engines may
index. See docs/superpowers/plans/2026-11-09-portfyl-seo.md (Wave 1, S3).

The cloud build prerenders the public pages into ``dist/prerendered/``
(``frontend/scripts/prerender.mjs``): the landing pages ``/`` (Czech), ``/en/``,
``/de/`` and every registered content page (``/<slug>/``, ``/en/<slug>/``; the
registry is ``frontend/src/seo/pages/index.js``). No page list lives here: a
page is public exactly when its ``index.html`` was built. This module maps a
request to one of:

* a prerendered public page -- indexable only on the public marketing host;
* a real file in ``dist/`` (assets, images, robots.txt, sitemap.xml);
* a 301 to ``/`` for the retired public demo: ``/demo`` and ``/demo/*``
  (removed 2026-11-18, the landing page has mini demos instead), with the
  query string kept, on every host except the private tracker;
* the empty app shell ``dist/index.html`` -- always ``noindex``: it is the
  tracker, auth screens, legal drafts or an unknown path, none of which
  should appear in search results.

Every response on a host other than the public one (the private tracker
``app.portfyl.com``, the raw ``*.run.app`` URL, localhost) is ``noindex``, and
its robots.txt disallows everything, so the site never competes with itself.
Pure functions only: no I/O beyond ``os.path`` checks, no database.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

PUBLIC_HOST = "portfyl.com"
TRACKER_HOST = "app.portfyl.com"
PRERENDERED_DIR = "prerendered"
NOINDEX = "noindex, nofollow"
# Build bookkeeping that must not be served as a page of its own.
_PRIVATE_BUILD_PREFIXES = (f"{PRERENDERED_DIR}/", ".vite/")
DISALLOW_ALL_ROBOTS = "User-agent: *\nDisallow: /\n"
_NO_CACHE = "no-cache"
# The public demo is gone; its old URLs are redirected, never served.
RETIRED_DEMO_PREFIX = "demo"


@dataclass(frozen=True)
class SpaTarget:
    """What to send for one request. Exactly one of ``file``, ``redirect`` or
    ``body`` is set; ``None`` everywhere means 404."""

    file: str | None = None
    redirect: str | None = None
    body: str | None = None
    media_type: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


def request_host(headers) -> str:
    """The host the visitor asked for. The Cloudflare Worker in front of
    app.portfyl.com forwards to the run.app origin and names the original host
    in X-Forwarded-Host; the apex reaches Cloud Run directly with its own Host.
    A spoofed value only changes what the spoofer is told about indexing."""
    raw = headers.get("x-forwarded-host") or headers.get("host") or ""
    host = raw.split(",")[0].strip().lower()
    if host.startswith("["):  # IPv6 literal, keep as is
        return host
    return host.rsplit(":", 1)[0] if ":" in host else host


def _inside(dist: str, relative: str) -> str | None:
    candidate = os.path.normpath(os.path.join(dist, relative))
    if candidate.startswith(dist + os.sep) and os.path.isfile(candidate):
        return candidate
    return None


def _prerendered_page(full_path: str, dist: str) -> tuple[str, str] | None:
    """(file, canonical path) of the prerendered page for this path, if any.
    "" is the root; "en" and "en/" both find dist/prerendered/en/, whose
    canonical path is "en/". Content pages nest the same way ("slug/",
    "en/slug/"). An empty segment ("a//b") or one starting with a dot never
    names a page, and neither does an uppercase letter (built paths are
    lowercase; this keeps case-insensitive file systems from adding aliases), so
    a page has no alias URL besides the slashless one."""
    stripped = full_path.strip("/")
    segments = stripped.split("/") if stripped else []
    if stripped != stripped.lower() or any(not segment or segment.startswith(".") for segment in segments) or (segments and "." in segments[-1]):
        return None  # looks like a file or a traversal, never a page directory
    relative = os.path.join(PRERENDERED_DIR, *segments, "index.html")
    found = _inside(dist, relative)
    return (found, f"{stripped}/" if stripped else "") if found else None


def _is_retired_demo(full_path: str) -> bool:
    """/demo and /demo/..., but not /demolition, /demos or /demo.png."""
    return full_path == RETIRED_DEMO_PREFIX or full_path.startswith(f"{RETIRED_DEMO_PREFIX}/")


def resolve(full_path: str, dist: str, *, host: str, query: str = "") -> SpaTarget:
    public = host == PUBLIC_HOST
    host_headers = {} if public else {"X-Robots-Tag": NOINDEX}

    if not public and full_path == "robots.txt":
        return SpaTarget(body=DISALLOW_ALL_ROBOTS, media_type="text/plain", headers={"Cache-Control": _NO_CACHE, **host_headers})

    if host != TRACKER_HOST and _is_retired_demo(full_path):
        # One hop to the home page, query kept (utm_* of old campaigns).
        return SpaTarget(redirect="/" + (f"?{query}" if query else ""), headers=host_headers)

    if host != TRACKER_HOST:
        page = _prerendered_page(full_path, dist)
        if page:
            file, canonical = page
            if full_path != canonical:
                # "/en" -> "/en/": one URL per page, the one in canonical/hreflang.
                location = f"/{canonical}" + (f"?{query}" if query else "")
                return SpaTarget(redirect=location, headers=host_headers)
            return SpaTarget(file=file, headers={"Cache-Control": _NO_CACHE, **host_headers})

    if full_path and not full_path.startswith(_PRIVATE_BUILD_PREFIXES):
        found = _inside(dist, full_path)
        if found:
            return SpaTarget(file=found, headers={"Cache-Control": _NO_CACHE, **host_headers})

    shell = _inside(dist, "index.html")
    if shell:
        return SpaTarget(file=shell, headers={"Cache-Control": _NO_CACHE, "X-Robots-Tag": NOINDEX})
    return SpaTarget()
