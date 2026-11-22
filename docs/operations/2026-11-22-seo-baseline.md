# SEO live baseline (task S0) — 2026-11-22

Measured on 2026-11-22 from a machine in the Czech Republic against the live
site `https://portfyl.com`. Everything here was read-only: `curl`, a Chrome
DevTools session, and Cloudflare API `GET` calls. Nothing was changed, and no
captcha or bot check was bypassed. Plan: `docs/superpowers/plans/2026-11-09-portfyl-seo.md`
(section 5, Wave 0 / S0, and section 4a).

## 1. HTTP checks (`curl -sI`)

| URL | Status | Content-Type | X-Robots-Tag | Location | Cache-Control |
|---|---|---|---|---|---|
| `https://portfyl.com/` | 200 | text/html; charset=utf-8 | none | none | no-cache |
| `https://portfyl.com/en` | **301** | text/html | none | `/en/` | none |
| `https://portfyl.com/en/` | 200 | text/html; charset=utf-8 | none | none | no-cache |
| `https://portfyl.com/de/` | 200 | text/html; charset=utf-8 | none | none | no-cache |
| `https://portfyl.com/robots.txt` | 200 | text/plain; charset=utf-8 | none | none | max-age=14400 (CF `EXPIRED`) |
| `https://portfyl.com/sitemap.xml` | 200 | text/xml; charset=utf-8 | none | none | no-cache |
| `https://portfyl.com/foo` | 200 (soft 404) | text/html; charset=utf-8 | `noindex, nofollow` | none | no-cache |
| `https://portfyl.com/demo` | **301** | text/html | none | `/` | none |
| `https://portfyl.com/dashboard` | 302 | text/html | none | Cloudflare Access login (`portfyl.cloudflareaccess.com`) | private, no-store |
| `https://app.portfyl.com/` | 302 | text/html | none | Cloudflare Access login | private, no-store |

Extra paths checked:

| URL | Result |
|---|---|
| `/pricing`, `/login` | 302 to Cloudflare Access (see finding 2) |
| `/terms`, `/privacy` | 200 HTML, `noindex, nofollow` (lawyer-review drafts, as planned) |
| `/llms.txt` | 200 HTML app shell, `noindex, nofollow` (not a real llms.txt) |
| `/og/portfyl-en.jpg` | 200 `image/jpeg` |

`/` has no `<meta name="robots">`. Its canonical is `https://portfyl.com/`.
The three pages have reciprocal hreflang in the sitemap (cs `/`, en `/en/`,
de `/de/`, `x-default` `/en/`), all `lastmod` 2026-11-19. The sitemap lists
exactly 3 URLs.

### robots.txt

The live file has three parts, in this order:

1. Cloudflare-managed block (between `BEGIN`/`END Cloudflare Managed content`):
   `User-agent: *`, `Content-Signal: search=yes,ai-train=no,use=reference`,
   `Allow: /`, then about 30 named training crawlers with `Disallow: /`
   (Amazonbot, Applebot-Extended, Bytespider, CCBot, ClaudeBot, Diffbot,
   Google-Extended, GPTBot, GoogleOther, Baiduspider, PetalBot and others).
2. Portfyl's own training-bot group (GPTBot, ClaudeBot, anthropic-ai,
   Google-Extended, Applebot-Extended, CCBot, Bytespider, meta-externalagent:
   `Disallow: /`).
3. Portfyl's own `User-agent: *` group: `Disallow:` `/api/`, `/dashboard`,
   `/login`, `/register`, `/onboarding`, `/settings`, then
   `Sitemap: https://portfyl.com/sitemap.xml`.

Googlebot, Bingbot and SeznamBot are not named anywhere, so they fall under
`*` and may crawl `/`, `/en/` and `/de/`. The two `User-agent: *` groups do not
conflict (one allows `/`, the other disallows only private paths); crawlers
merge groups with the same user-agent.

### Bot user-agents

Fetched `/`, `/en/` and `/robots.txt` with the user-agents Googlebot/2.1,
`SeznamBot/4.0`, `Seznam.cz-bot`, bingbot/2.0 and plain curl. Every one got the
same response: 200, `text/html`, identical size (14,989 B for `/`, 14,723 B for
`/en/`, 3,057 B for `/robots.txt`), and no Cloudflare challenge markers
("just a moment", `challenge-platform`, `cf-chl`) in any body.

Limit: this uses the user-agent string only. Real Googlebot and SeznamBot
come from verified IP ranges, which Cloudflare treats as verified bots. The
result for a spoofed user-agent from a home IP is not proof for the real
crawlers, but it shows no rule treats the user-agent string itself as hostile.

## 2. Lighthouse, mobile (Chrome DevTools MCP)

The `lighthouse_audit` tool in this environment does not return a Performance
score (it covers Accessibility, Best Practices, SEO and agentic browsing only).
Performance was measured with a DevTools performance trace instead: mobile
viewport 412x823, Fast 4G, 4x CPU slowdown. A Lighthouse Performance score was
**not obtained** (running the Lighthouse CLI was declined by the permission
system). Treat Performance below as lab LCP/CLS only.

| Page | SEO | Accessibility | Best Practices | Performance score | LCP (trace) | CLS (trace) |
|---|---|---|---|---|---|---|
| `/` (cs) | 100 | 95 | 100 | unverified | 0.78 s | 0.00 |
| `/en/` | 100 | 99 | 100 | unverified | 0.86 s | 0.16 |
| `/de/` | 100 | 99 | 100 | unverified | 0.80 s | 0.11 |

Targets: SEO 100 is met on all three. Performance >= 90 cannot be confirmed
(score not measured); LCP is under 1 s everywhere, which is well inside "good".
CLS is above the 0.1 "good" limit on `/en/` and `/de/` in this lab run, and was
0.00 on `/` (one run each; CLS varies with load order, so this needs a repeat).

Details:

- CLS cause on `/en/` and `/de/` (from the DevTools insight): the main content
  (`main#obsah`) shifts at about 1.1 to 1.3 s. The trace names the hero image
  `/landing/performance-live-20260911.png` as an "unsized image" and, on `/en/`,
  also the late-loading web fonts (Inter, Plus Jakarta Sans, JetBrains Mono).
  The served HTML does have `width="1004" height="455"` on that image, so the
  cause may be CSS overriding its aspect ratio or the font swap; the exact cause
  is **unverified**.
- Accessibility on `/` (95): colour contrast of the cookie banner (text 4.34:1,
  "Podrobnosti" link 3.57:1, accept button 3.76:1; needs 4.5:1) and the footer
  `<h4>` heading order. On `/en/` and `/de/` only the `<h4>` heading order
  fails (the banner did not appear in those runs).
- The "agentic browsing" category scored 50 on all pages: no `llms.txt`
  (the path returns the HTML app shell) and no ARD manifest. These are not SEO
  signals; recorded only for completeness.
- Reports (local, not committed): scratchpad `lh-cs`, `lh-en`, `lh-de`.

## 3. Cloudflare (zone `portfyl.com`, Free plan, read-only API `GET`s)

Read through the Cloudflare MCP. Account and zone IDs are deliberately not
recorded here.

| Item | Value | Effect on search bots |
|---|---|---|
| Bot Fight Mode (`fight_mode`) | **off** | No bot challenge from this feature |
| Super Bot Fight Mode / bot management | not on a Free plan; `crawler_protection`, `ai_bots_protection`, `content_bots_protection` all `disabled` | None |
| JavaScript detections (`enable_js`) | off | None |
| AI training bots (`ai_training`) | `disallow` | Blocks training bots only, via robots.txt |
| `ai_search` | `disabled` | Meaning of this value is **unverified** (see below) |
| `ai_user` | `only_on_ad_pages` | Unverified meaning |
| AI agents (Anthropic, Google, OpenAI, others) | all `disabled` | Unverified meaning |
| Managed robots.txt (`is_robots_txt_managed`) | **true**; `bot_preference_sync_enabled` true; `cf_robots_variant` `off` | Produces part 1 of the live robots.txt |
| Content Signals | `search=yes, ai-train=no, use=reference` (no `ai-input` signal) | Search allowed, training refused |
| Browser Integrity Check (`browser_check`) | on | Standard; known search bots are not affected |
| Security level | medium | Standard |
| Zone `waf` setting | off | Legacy flag, not the managed ruleset |
| Managed rulesets | Free Managed Ruleset (v88), DDoS L7, Normalization, Response Firewall: all Cloudflare defaults | No custom changes |
| Custom WAF rules, rate limiting, redirect, cache and config rules | **none** (those phases return 404 = no ruleset exists) | Nothing that can challenge a bot |
| Request-header transform | one rule that sets a trusted-edge header toward the origin | Not a crawl issue (token value intentionally omitted) |
| SSL mode / HTTP3 / Brotli | strict / on / on | Fine |
| Cache level / browser TTL | aggressive / 4 h | Fine for static assets; HTML responses are `no-cache` |
| Always Use HTTPS | **off** | See finding 5 |
| Min TLS version | 1.0 | Not an SEO item; see finding 5 |

Cloudflare Access applications (account level, read-only list):

- `app.portfyl.com` (whole host, "private beta"), with open exceptions for
  `/api/billing/webhook` and `/auth/action` plus its assets.
- "Portfyl testing" on `portfyl.com`: `/api`, `/dashboard`, `/overview`,
  `/allocation`, `/transactions`, `/cash`, `/import`, `/dividends`,
  `/analytics`, `/search`, `/stock`, `/watchlists`, `/assistant`, `/settings`,
  **`/pricing`, `/login`, `/register`, `/verify-email`, `/forgot-password`**,
  `/health`, `/docs`, `/redoc`, `/openapi.json`.
  `/`, `/en/`, `/de/`, `/robots.txt`, `/sitemap.xml`, `/og/*`, `/terms`,
  `/privacy` are not in the list, which matches the live curl results.

What the API could not tell me, and what the owner should check in the
dashboard (Security > Bots, and AI Crawl Control):

- What `ai_search: disabled` means for the AI answer/search crawlers
  (OAI-SearchBot, PerplexityBot, Claude-SearchBot). The plan wants them
  allowed. Confirm in AI Crawl Control that none of them is set to "Block".
  The live `robots.txt` does not disallow them.
- Whether the "AI Labyrinth" / "Block AI bots" toggles are off (only the
  fields above were readable; a dashboard glance settles it).
- Verified-bot handling for Bingbot and SeznamBot: with Bot Fight Mode off and
  no custom rules there is no setting that would block them, but this is the
  absence of a rule, not a positive confirmation. Re-check after any change to
  Bot Fight Mode or Security level.

## 4. Indexing status

| Engine | Query | Result |
|---|---|---|
| Google | `site:portfyl.com` | **Blocked**: Google showed its "unusual traffic" CAPTCHA page (`/sorry/`). Not bypassed. Result **unverified**. |
| Seznam | `site:portfyl.com` | **No results** ("Bohuzel jsem nic nenasel"). The site is not in Seznam's index. |

The Google index state needs the owner's Google Search Console (S1) or a
manual `site:` search from a normal logged-in browser. Bing was not checked
(not requested).

## 5. Findings, risks, recommended actions

1. **Nothing found that blocks Google or Seznam from crawling the three
   landing pages.** They return 200 HTML, have no `noindex`, are allowed by
   robots.txt, are listed in the sitemap, and the bot user-agents got normal
   pages with no challenge. SEO score is 100 on all three.
2. **`/pricing`, `/login`, `/register`, `/verify-email`, `/forgot-password`,
   `/docs` are behind Cloudflare Access on `portfyl.com`.** Search bots get a
   302 to a login page. Fine today (they are not meant to be indexed), but a
   future public pricing page would be unreachable until its path is removed
   from the "Portfyl testing" Access application. Also, those private-looking
   paths are not covered by `noindex`, only by the Access redirect. Action:
   when S-wave tasks add a public pricing or content page, change the Access
   path list in the same release.
3. **Seznam has zero indexed pages.** Expected for a site this new. Action: S1
   (register in Seznam Webmaster and submit the sitemap). Google's state is
   unknown (blocked); check it in Search Console.
4. **CLS is above 0.1 on `/en/` and `/de/` in the lab run** (0.16, 0.11), with
   a hero-image or font-swap shift around 1.2 s. Verify with a repeat run; if it
   is real, fix the image's reserved space in CSS and preload or `size-adjust`
   the fonts. Also fix the cookie-banner contrast on `/` (up to about 1 contrast
   point short) and the footer `<h4>` heading order.
5. **Always Use HTTPS is off and minimum TLS is 1.0.** Not a ranking problem
   today, but `http://portfyl.com/` was confirmed to answer 200 over plain HTTP
   with no redirect to HTTPS, so two URL versions exist (the canonical tag
   points to https). Recommend
   turning Always Use HTTPS on and raising the minimum TLS version; these are
   Cloudflare changes for the owner to decide, not part of S0.
6. **Unknown paths return 200 with `noindex, nofollow`, not 404** (known and
   accepted in plan 4a). `/llms.txt` is the same: an HTML shell, not a real file.
   Low risk, crawl hygiene only.
7. **robots.txt is double-sourced** (Cloudflare managed block plus Portfyl's own
   groups, with the training-bot list partly duplicated). It is valid and
   behaves as intended, but any future robots.txt change must be made in
   `frontend/scripts/prerender.mjs` (the build) and checked against the Cloudflare managed
   block, since Cloudflare prepends its own.
8. **Content Signals say `search=yes, ai-train=no` and say nothing about
   `ai-input`.** If the owner wants AI answer engines to quote the site, decide
   whether to add `ai-input=yes` (plan decision O4); that is a Cloudflare
   setting, not changed here.
9. **Unverified:** Lighthouse Performance score (not available from this
   tool), real-crawler behaviour from verified Googlebot/SeznamBot IPs, Google
   index count, the meaning of the `ai_search` and `ai_agents` settings.

## Related

- [[Deploy and operations]]
- [[operations/2026-09-10-public-landing]]
