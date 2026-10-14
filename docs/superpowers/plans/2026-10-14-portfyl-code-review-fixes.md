# Opravy z hloubkové code review (2026-10-14)

Hloubková review celého repa (stav `main` @ `061a681`) našla 15 problémů.
Tento plán je rozděluje do úkolů pro souběžné session podle pravidel v
CLAUDE.md, sekce "Parallel session safety". Každý úkol má vlastní větev a
worktree, disjunktní sadu souborů a vlastní testovací PostgreSQL. Sdílené
hotspoty vlastní vždy nejvýš jeden úkol: `backend/requirements.txt` úkol B2,
`backend/alembic/versions/` a `EXPECTED_ALEMBIC_HEAD` úkol C1.

Čísla řádků v textu odpovídají commitu `061a681`.

## Rozhodnutí

Schválená rozhodnutí (2026-10-14). Session je znovu neotevírají. Kdyby
narazily na důvod je změnit, zastaví se a zeptají.

- **R1, CSRF (úkol A2):** token odvozený ze session:
  `base64url(HMAC-SHA256(key=raw session token, msg="portfyl-csrf-v1"))`.
  - Všechny taby jedné session mají stejný token. `GET /auth/me` nic
    nerotuje ani nezapisuje.
  - Nepotřebuje nový secret ani migraci.
  - Tokeny vydané před nasazením (náhodné, digest v
    `auth_sessions.csrf_digest`) se dál přijímají 30 dní, tedy po
    maximální stáří session (`SESSION_MAX_AGE`). Pak se legacy větev
    odstraní (navazující úklid v sekci Nasazení).
- **R2, runtime (úkol B2):**
  - Produkční image zůstává na `python:3.14-slim` a `node:22-alpine`.
  - Backend joby v CI běží jako matrix Python 3.12 (dev) a 3.14
    (produkce). Frontend v CI běží na Node 22.
  - Lock závislostí je univerzální (platí pro 3.12 i 3.14) a s hashi.
  - Sjednocení na jednu verzi je navazující úklid: po dvou týdnech zelené
    matrix přejde dev (`start.bat`) na 3.14 a 3.12 z CI zmizí.
- **R3, DB kontrola (úkol C1):** ano, jako pojistka k validaci v aplikaci.
  Ledger je zdroj pravdy a jedna NaN hodnota rozbije každý výpočet nad
  portfoliem.
  - Jedna migrace `0024` přidá CHECK constraint `NOT VALID` a ve stejné
    migraci ho `VALIDATE`.
  - Tabulka je v private betě malá a DDL v PostgreSQL je transakční. Když
    migrace najde špatná data, selže celá, nic se nezmění a deploy se
    zastaví.
  - Předpoklad: A7 a B1 jsou v produkci a dotaz z přílohy A vrací 0 řádků.
  - B1 proto přidává `allow_inf_nan=False` i na číselná pole v `/cash` a
    `/alerts`. Jinak by šlo přes API poslat `Infinity`: Starlette parsuje
    JSON přes `json.loads`, který literály `NaN` a `Infinity` přijme.

## Nálezy

| # | Nález | Závažnost | Úkol |
|---|---|---|---|
| N1 | SSRF přes Discord webhook URL. PATCH ji nevaliduje vůbec, POST jen podřetězcem a `/webhook/test` vrací 200 znaků cizí odpovědi | vysoká (security) | A1 |
| N2 | `GET /auth/me` rotuje jediný CSRF token session. Druhý tab zneplatní ostatní a odhlášení v nich jen předstírá úspěch | vysoká | A2 |
| N3 | Advisory lock cloudových jobů leží na spojení, které Session při commitu vrací do poolu. Výsledkem je dvojí běh nebo falešné „already running“ | střední | A3 |
| N4 | T212 history run, který selhává deterministicky, se opakuje navždy a blokuje nové runy | střední | A4 |
| N5 | Nativní CSV import a `POST /portfolio/transactions` přijmou NaN a nevalidní typ, pak padá holdings/summary na 500 | střední | A7 (+ C1) |
| N6 | Dashboard na Free plánu volá Investor endpointy (movers, earnings, heatmap), dostane 403 a ukáže upgrade prompt | střední | A5 |
| N7 | Přibližně 21 mutujících `/api` endpointů nemá CSRF kontrolu | střední (zmírněno SameSite a CORS) | A2 |
| N8 | Zámek workspace (FOR UPDATE z capacity dependencies) zůstává držený přes volání Yahoo, T212 a KMS | střední | B1 |
| N9 | `_live_to_usd` padá na kurz 1.0 a kurz cachuje navždy | střední | A7 |
| N10 | Read-only a kvóty jdou obejít: UUID velkými písmeny, chybějící `portfolio_id`, `/cash` bez kvóty | nízká (před spuštěním plateb střední) | B1 |
| N11 | `claim_or_create_run` při kolizi rollbackne celou transakci včetně snapshotu | nízká | A4 |
| N12 | Časový test 3 let v tax reportu je posunutý o den | nízká | A6 |
| N13 | Výkonová řada přepočítává cash ledger pro každý den, tedy O(dní × transakcí) | výkon | A6 |
| N14 | In-process cache nikdy nevyřazují záznamy | výkon | A8 |
| N15 | CI testuje Python 3.12 a Node 20, produkce běží na 3.14 a 22 s neukotvenými závislostmi | proces | B2 |

## Úkoly a vlastnictví souborů

| Úkol | Nálezy | Větev | Soubory (ve své vlně jen tento úkol) | Migrace | Test DB port | Rozsah |
|---|---|---|---|---|---|---|
| A1 | N1 | `fix/discord-webhook-ssrf` | `backend/routers/discord.py`, nový `backend/discord_webhooks.py`, `frontend/src/components/DiscordSettings.jsx`, testy discordu | ne | 55451 | S |
| A2 | N2, N7 | `fix/csrf-session-token` | `backend/auth.py`, `backend/routers/auth.py`, `backend/tenancy.py`, `backend/main.py`, `frontend/src/api.js`, `frontend/src/auth/AuthProvider.jsx`, `backend/tests/postgres/test_auth_sessions.py`, nový `backend/tests/test_csrf_coverage.py`, `frontend/src/api.auth.test.js`, `frontend/src/auth/AuthProvider.test.jsx` | ne | 55452 | M |
| A3 | N3 | `fix/job-advisory-lock` | `backend/routers/internal_jobs.py`, `backend/tests/postgres/test_job_advisory_lock.py`, `backend/tests/test_internal_jobs.py` | ne | 55453 | S |
| A4 | N4, N11 | `fix/t212-backfill-dead-letter` | `backend/jobs.py`, `backend/t212_sync.py`, `backend/tests/test_broker_backfill.py`, `backend/tests/test_t212_sync_runs.py`, nový test v `backend/tests/postgres/` | ne | 55454 | M |
| A5 | N6 | `fix/dashboard-free-plan-gating` | `frontend/src/pages/Dashboard.jsx`, `frontend/src/pages/Dashboard.async.test.jsx`, případně `frontend/src/components/Heatmap.jsx` | ne | — | S |
| A6 | N12, N13 | `fix/tax-time-test-perf-series` | `backend/routers/analytics.py`, testy analytiky a tax reportu, případně `frontend/src/pages/TaxReport.jsx` | ne | (55456) | M |
| A7 | N5, N9 | `fix/ledger-input-validation` | `backend/routers/portfolio.py` (parser importu, `_live_to_usd`), `backend/schemas.py`, `backend/tests/test_import_workflow.py`, nové testy | ne | 55457 | M |
| A8 | N14 | `fix/bounded-caches` | `backend/cache.py`, `backend/market_data.py`, `backend/fx.py`, `backend/routers/market.py` (jen deklarace a přístup ke cache), nové testy | ne | — | S |
| B1 | N8, N10 (+ R3) | `fix/capacity-lock-scope` | `backend/entitlements.py`, `backend/routers/{portfolio,portfolios,watchlists,alerts,cash,broker,polymarket,ibkr}.py`, testy | ne | 55461 | L |
| B2 | N15 | `chore/ci-runtime-lock` | `Dockerfile`, `.github/workflows/ci.yml`, `backend/requirements.txt`, nové `backend/requirements*.lock`, `start.bat`, `CLAUDE.md` (sekce Run it a Tests) | ne | — | M |
| C1 | N5 | `feat/ledger-finite-check` | nová `backend/alembic/versions/0024_*.py`, `backend/database.py` (`EXPECTED_ALEMBIC_HEAD`), test v `backend/tests/postgres/` | **ano** | 55471 | S |

## Vlny a souběh

- **Vlna 1 (A1–A8):** sady souborů jsou disjunktní, úkoly mohou běžet
  paralelně. Každá session pracuje ve vlastním worktree z aktuálního `main`:
  buď nová session aplikace v režimu worktree, nebo z hlavního checkoutu
  `git worktree add ..\portfyl-a1 -b fix/discord-webhook-ssrf main`.
- **Vlna 2 (B1, B2):** B1 smí začít až po merge A7 (oba mění
  `backend/routers/portfolio.py`) a A8 (B1 přepíná `_quote` na
  `market_data.get_infos`). B2 vlastní hotspot `backend/requirements.txt`.
  Patří do samostatné vlny, aby se změna závislostí nemíchala s opravami
  chyb.
- **Nasazení 1:** po integraci vln 1 a 2, bez migrace. Jen na výslovný
  pokyn vlastníka.
- **Vlna 3 (C1):** až po nasazení 1 (A7 a B1 jsou v produkci) a až dotaz z
  přílohy A vrátí 0 řádků (rozhodnutí R3). Jediný úkol s migrací.
- **Nasazení 2:** C1. Migration job běží před deployem služby.

Pravidla pro všechny session:

1. Vlastní worktree a vlastní větev, nikdy commit přímo do `main`. V novém
   worktree vytvoř venv stejně jako `start.bat` (`uv venv .venv --python 3.12`,
   pak `uv pip install -r backend/requirements-dev.txt`) a ve `frontend/` spusť
   `npm ci`.
2. Měň jen soubory svého úkolu. Když je potřeba sáhnout jinam, zastav se a
   zeptej se.
3. PostgreSQL suite spouštěj jen proti vlastnímu kontejneru s portem z
   tabulky. Sdílený `deploy/docker-compose.postgres-test.yml` (port 55441)
   nepoužívej. Postup (port a jméno podle úkolu):

   ```powershell
   docker run -d --rm --name portfyl-pg-a1 -e POSTGRES_DB=portfyl_test -e POSTGRES_USER=portfyl_test -e POSTGRES_PASSWORD=portfyl_test -p 55451:5432 postgres:16
   do { Start-Sleep 1 } until ((docker exec portfyl-pg-a1 pg_isready -U portfyl_test -d portfyl_test) -match "accepting")
   $env:TEST_DATABASE_URL = "postgresql+psycopg://portfyl_test:portfyl_test@localhost:55451/portfyl_test"
   python -m pytest tests/postgres/ -v
   docker stop portfyl-pg-a1
   ```

4. Dev servery spouštěj jen pro UI ověření (A2, A5) a s vlastními porty:
   backend `python -m uvicorn main:app --port 80xx`, frontend
   `$env:VITE_API_PROXY_TARGET="http://localhost:80xx"; npm run dev -- --port 51xx --strictPort`.
   Dev databázi nesdílej souběžně. Buď vlastní DB (`alembic upgrade head`
   proti ní s migration-owner credential), nebo UI ověření A5 a A2 po sobě.
5. Před označením úkolu za hotový spusť `git merge main` do své větve a znovu
   testy svého úkolu a rychlou backend suite. U frontendových změn navíc
   `npm test`, `npm run test:cloud`, `npm run build` a `npm run build:cloud`.
   Úkol končí na své větvi. Do `main` merguje integrační session (viz níže),
   postupně, aby dvě session nesahaly na hlavní checkout zároveň.
6. Commit končí řádkem `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
   Nepushovat, nedeployovat.

---

## Úkol A1: SSRF přes Discord webhook (N1)

```text
Oprav SSRF v Discord webhook integraci. Řiď se CLAUDE.md (hlavně "Parallel session safety") a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/discord-webhook-ssrf z aktuálního main.

KONTEXT (review 2026-10-14, nález N1)
- backend/routers/discord.py: create_webhook (POST /discord/webhook) ověřuje URL jen podřetězcem "discord.com/api/webhooks" kdekoli v URL, takže projde i http://10.0.0.5/x?discord.com/api/webhooks. update_webhook (PATCH) URL nevaliduje vůbec (ř. 122).
- test_webhook (POST /discord/webhook/test) pošle POST na uloženou URL a při chybě vrátí "Discord returned {status}: {resp.text[:200]}", tedy tělo cizí odpovědi.
- send_discord_notification (volají ji routers/alerts.py run_check a jobs.py) posílá na uloženou URL bez kontroly. URL jsou v DB šifrované, takže starší špatné záznamy SQL dotazem nenajdeš.

ÚKOL
1. Nový modul backend/discord_webhooks.py: validate_webhook_url(url) -> str (normalizovaná URL) a výjimka InvalidWebhookUrl. Pravidla:
   - urlsplit, scheme přesně https;
   - hostname (lowercase) z {discord.com, discordapp.com, ptb.discord.com, canary.discord.com};
   - žádný port kromě 443, žádný username/password, žádný fragment;
   - path přesně /api/webhooks/{id}/{token} nebo /api/v{N}/webhooks/{id}/{token} (id jen číslice, token [A-Za-z0-9_-]+);
   - query jen klíče wait a thread_id.
   IP adresy, jiné domény, discord.com.evil.com ani discord.com@evil.com neprojdou.
2. Validátor použij v create_webhook i update_webhook (400 s jasnou hláškou). Navíc URL znovu ověř těsně před odesláním v test_webhook a v send_discord_notification. Neplatnou uloženou URL nepošli: send_discord_notification vrátí None (jako "nenakonfigurováno") a zaloguje varování BEZ URL. Signaturu send_discord_notification NEMĚŇ, volají ji jobs.py a alerts.py, které patří jiným úkolům.
3. test_webhook nevrací tělo odpovědi, jen status (např. "Discord returned 404"). httpx explicitně s follow_redirects=False a timeoutem.
4. GET /discord/webhook vrací navíc "valid": bool, aby UI vyzvalo k novému zadání u starých neplatných URL. frontend/src/components/DiscordSettings.jsx: zobraz chybu validace z backendu a upozornění při valid=false. Jiné frontendové soubory neměň.
5. Testy (nový backend/tests/test_discord_webhook_validation.py a doplnění testů discord routeru):
   - projdou: discord.com, discordapp.com, ptb./canary., /api/v10/, ?wait=true, ?thread_id=123;
   - odmítnou se: http://, jiný host, discord.com.evil.com, discord.com@evil.com, IP literál, port :8080, chybějící token, cesta mimo /api/webhooks, fragment, jiný query klíč;
   - PATCH s neplatnou URL vrátí 400 a uložená URL se nezmění;
   - test endpoint nevrací tělo odpovědi;
   - send_discord_notification s neplatnou uloženou URL neudělá žádný HTTP request (mock httpx).
6. Z backend/: python -m pytest tests/ -v --ignore=tests/postgres. PostgreSQL suite proti vlastnímu kontejneru na portu 55451 (pravidlo 3 v plánu). Z frontend/: npm test, npm run test:cloud, npm run build, npm run build:cloud.
7. Commitni jen soubory tohoto úkolu, zpráva končí Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>. Pak git merge main do své větve a testy znovu (pravidlo 5).
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci napiš shrnutí změn, výsledky testů a jestli může nová validace odříznout nějaké dnes fungující webhooky.
```

---

## Úkol A2: CSRF token vázaný na session a CSRF pro všechny mutace (N2, N7)

```text
Přestav CSRF tak, aby fungoval ve více tabech, a vynucuj ho na všech mutujících /api endpointech. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/csrf-session-token z aktuálního main.

KONTEXT (review 2026-10-14, nálezy N2 a N7)
- backend/routers/auth.py get_me (GET /auth/me, ř. 232) volá rotate_csrf_token a přepíše jediný csrf_digest session. SPA (frontend/src/auth/AuthProvider.jsx) volá /auth/me při každém načtení tabu a token drží jen v paměti. Druhý tab proto zneplatní token prvního:
  - mutace v prvním tabu končí 403 csrf_failed a frontend/src/api.js na to nereaguje;
  - "Odhlásit" pošle /auth/logout se starým tokenem, dostane 403, ale AuthProvider.logout ve finally stejně smaže stav. Session cookie zůstane platná a reload uživatele znovu přihlásí.
  Rotaci jde vyvolat i cross-site navigací na /api/auth/me (GET s SameSite=Lax cookie).
- CSRF se vynucuje jen per-route přes Depends(require_csrf) (backend/tenancy.py). Nemají ho:
  - celé routers/alerts.py, routers/cash.py, routers/notes.py, routers/watchlists.py;
  - routers/benchmarks.py (create, update, delete);
  - routers/settings.py PUT /sync-schedule;
  - routers/discord.py POST /webhook/test;
  - routers/portfolio.py POST a DELETE /transactions a DELETE /transactions bez id (smaže celý ledger);
  - local-edition POST a DELETE /market/screener/jobs.
  Dnes to tlumí SameSite=Lax a CORS preflight, ale bez těla jde padělat například POST /api/alerts/check.

NÁVRH (schválené rozhodnutí R1 v plánu)
A) Token odvozený ze session: csrf = base64url(HMAC-SHA256(key=raw session token z cookie, msg="portfyl-csrf-v1")). Server ho umí kdykoli spočítat z cookie, JS ho z HttpOnly cookie spočítat nemůže a všechny taby jedné session dostanou stejný token. Nový secret ani migrace nejsou potřeba.
   - backend/auth.py: derive_csrf_token(raw_token). create_session vrací odvozený token a do csrf_digest ukládá _digest(odvozeného tokenu), takže ho přijmou i staré instance během rolling deploye. csrf_matches(session, raw_session_token, header): nejdřív hmac.compare_digest s odvozeným tokenem, pak legacy porovnání digestu (tokeny vydané před nasazením). Legacy větev označ komentářem, že se 30 dní po nasazení odstraní (R1). rotate_csrf_token odstraň.
   - backend/routers/auth.py get_me: už nerotuje a nic nezapisuje (kromě last_seen), vrací odvozený token. _require_csrf bere raw token z cookie. Během krátkého okna rolling deploye může stará instance odvozený token odmítnout. Nový frontend to zvládne retry po csrf_failed (bod C).
   - backend/tenancy.py require_csrf: totéž, raw token přes session_token_from_request.
B) Centrální guard v tenancy.py: csrf_guard(request, db=Depends(get_db)).
   - Pro GET, HEAD a OPTIONS nedělá nic.
   - Bez session cookie nedělá nic (autentizace route vrátí 401).
   - Jinak porovná odvozený token z cookie s X-CSRF-Token. Při neshodě zkusí legacy digest (DB lookup jen v tomto případě). Při další neshodě vyhodí RequestContextError(403, "csrf_failed").
   V backend/main.py ho přidej do dependencies KAŽDÉHO include_router pod /api kromě auth routeru: ten má vlastní kontroly a /auth/session musí fungovat bez tokenu. internal_jobs (mimo /api) se nemění. Stávající Depends(require_csrf) na routách nech.
C) Frontend:
   - frontend/src/api.js: v response interceptoru při 403 a code === "csrf_failed" jednou zavolej registrovaný refresh handler, doplň nový token do hlavičky a request zopakuj. Opakování hlídej příznakem v configu, aby nevznikla smyčka. Exportuj setCsrfRefreshHandler(fn).
   - frontend/src/auth/AuthProvider.jsx registruje handler: zavolá fetchMe a aktualizuje csrfToken (stav i configureRequestContext).
   - logout a logoutAll: když server odhlášení nepotvrdí ani po retry, NEMAŽ lokální stav, jako by se uživatel odhlásil. Ukaž chybu a nech ho přihlášeného (do komentáře napiš proč). 401 dál vede na /login.
   - Pokud docs/security/tenant-isolation-matrix.md popisuje CSRF, aktualizuj ho (patří jen tomuto úkolu).

TESTY
- backend/tests/postgres/test_auth_sessions.py: test test_me_bootstraps_account_and_rotates_usable_csrf přejmenuj a uprav:
  - dvě volání /auth/me vrátí stejný token a oba platí;
  - token z /auth/session platí i po /auth/me;
  - GET /auth/me nemění csrf_digest;
  - legacy token (náhodný, digest v DB) projde;
  - cizí nebo špatný token vrátí 403;
  - token jiné session neplatí.
- Nový backend/tests/test_csrf_coverage.py projde main.app.routes a ověří, že každá APIRoute pod /api s POST/PUT/PATCH/DELETE (kromě /api/auth/*) má v dependency stromu csrf_guard nebo require_csrf. Pusť ho pro local i cloud edici, pokud to fixture dovolí (cloud registruje test_plans, local local_features).
- E2E vzorek (TestClient, postgres):
  - POST /api/alerts bez hlavičky vrátí 403 csrf_failed;
  - DELETE /api/portfolio/transactions bez hlavičky vrátí 403 a ledger zůstane beze změny;
  - s platnou hlavičkou obojí projde.
- Frontend:
  - api.auth.test.js: retry po csrf_failed proběhne jednou, podruhé už ne;
  - AuthProvider.test.jsx: nepovedený logout nesmaže stav.

OVĚŘENÍ
- Z backend/: python -m pytest tests/ -v --ignore=tests/postgres. PostgreSQL suite proti vlastnímu kontejneru na portu 55452.
- Z frontend/: npm test, npm run test:cloud, npm run build, npm run build:cloud.
- Ruční ověření ve dvou tabech podle sekce "Verifying UI changes" v CLAUDE.md, na vlastních portech: backend 8012, vite 5182 ($env:VITE_API_PROXY_TARGET="http://localhost:8012"; npm run dev -- --port 5182 --strictPort). Vlastní dev DB, nebo až po UI ověření A5.
  Scénář: otevři tab A, pak tab B, v tabu A vytvoř transakci a odhlas se. Obojí musí projít a po reloadu musíš být odhlášený. Pokud dev servery nebo Firebase test účet nejsou k dispozici, napiš to místo hádání.
- Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci shrnutí a výsledky testů.
```

---

## Úkol A3: Advisory lock cloudových jobů (N3)

```text
Oprav zámek cloudových jobů tak, aby platil po celou dobu passu. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/job-advisory-lock z aktuálního main.

KONTEXT (review 2026-10-14, nález N3)
backend/routers/internal_jobs.py: with_job_lock(db, job_name) volá session-level pg_try_advisory_lock přes job Session. Ta je vázaná na engine (sessionmaker(bind=build_engine(...))), takže při každém commitu vrací spojení do poolu (QueuePool, FIFO). Pass v jobs.py commituje mnohokrát a zbytek passu pak běží na jiném spojení. pg_advisory_unlock ve finally se může vykonat na spojení, které zámek nedrží: vrátí false a zámek visí na spojení v poolu až do pool_recycle=300 s.
Následky:
- další invokace stejného jobu dostane jiné spojení, zaloguje "skipped, already running", job neběží a heartbeat stárne;
- nebo dostane právě to spojení, pg_try_advisory_lock vrátí re-entrantně true a dva passy běží souběžně (duplicitní Discord notifikace, souběžné synce).
tests/postgres/test_job_advisory_lock.py to nevidí, protože session váže na jedno explicitní Connection.

ÚKOL
1. Zámek drž na dedikovaném spojení mimo job Session po celou dobu passu:
   - samostatný engine s poolclass=NullPool (stejná JOB_DATABASE_URL a stejná kontrola na -pooler);
   - with engine.connect() as lock_conn: pg_try_advisory_lock, hned lock_conn.commit() (ať spojení nevisí idle-in-transaction), yield;
   - ve finally pg_advisory_unlock na lock_conn a spojení zavři. NullPool spojení opravdu zavře, takže zámek nemůže uniknout do poolu. Rovnocenná alternativa je Connection.invalidate().
2. Pass dál používá normální job Session s poolem. _run_job bere zámek přes nový mechanismus. V SQLite fast suite zůstává zámek no-op.
3. Testy:
   - backend/tests/postgres/test_job_advisory_lock.py: přidej test ve tvaru produkce. Job Session ze sessionmaker(bind=engine) s poolem, pass několikrát commitne a mezitím nechá jiné session vzít spojení z poolu. Souběžný pokus o stejný job musí během passu dostat False. Po skončení musí být pg_locks (locktype='advisory') prázdné a nová invokace musí dostat True. Stávající testy uprav na nové API.
   - backend/tests/test_internal_jobs.py: no-op cesta a mark_job_succeeded jen po úspěšném passu.
4. Z backend/: python -m pytest tests/ -v --ignore=tests/postgres a PostgreSQL suite proti vlastnímu kontejneru na portu 55453.
5. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci shrnutí a výsledky testů.
```

---

## Úkol A4: T212 backfill, dead-letter a savepoint (N4, N11)

```text
Zastav nekonečné opakování selhávajících T212 history runů a oprav rollback v claim_or_create_run. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/t212-backfill-dead-letter z aktuálního main.

KONTEXT (review 2026-10-14, nálezy N4 a N11)
- backend/jobs.py broker_backfill_pass (ř. 558–576): při výjimce z advance_run nebo finalize_run jen nastaví run.retry_count += 1 a last_error = HISTORY_RETRY_ERROR. retry_count se nikde nečte a run zůstane v ne-terminálním stavu. history_run_decision (t212_sync.py) i POST /broker/trading212/history/retry (force=True) vrací tentýž run. Historie se tak nikdy nedokončí a každý tick (lokálně 10 s, v cloudu 1×/min) znovu volá T212 nebo znovu finalizuje.
  Typické deterministické chyby: 401/403 od T212 (zneplatněný klíč) a ValueError z _finalize_dividend_event (chybí amount nebo currency).
- backend/t212_sync.py claim_or_create_run (ř. 622–637): při kolizi s partial unique indexem uq_broker_sync_run_one_active_per_connection (migrace 0015) volá db.rollback() celé transakce.
  - V routers/broker.py sync_transactions tím zahodí už zapsaný snapshot (_upsert_t212_balance, replace_positions, _bind_verified_account), ale odpověď přesto hlásí cash_updated a positions_updated = true.
  - V job session (RLS kontext jen přes raw set_config, viz jobs._set_job_workspace_context) rollback smaže i kontext, re-query nic nenajde, kód vyhodí výjimku a připojení dostane consecutive_failures++.

ÚKOL
1. Klasifikuj chyby v broker_backfill_pass:
   - Odmítnuté přihlašovací údaje (HTTPException 401 z _fetch_stream_page, httpx.HTTPStatusError 401 nebo 403): run přepni na failed s novou konstantou (např. HISTORY_CREDENTIALS_ERROR). Na připojení nastav needs_attention=True a last_error s výzvou k novému připojení (zobrazí ho GET /broker/trading212/status). Neopakuj.
   - Deterministická chyba dat při finalizaci (ValueError z finalize_run): run přepni na needs_review s vlastní konstantou last_error a s review_details bez payloadu (stream, datum, typ chyby; NIKDY raw payload). history_run_decision pak další automatické runy blokuje až do explicitního retry.
   - Přechodné chyby (síť, timeout, 5xx, DB): exponenciální backoff podle retry_count (např. 1, 2, 4 … max 60 min). Run v backoff okně vůbec neclaimuj. Filtruj podle retry_count a updated_at PŘED claim_lease, protože claim bumpne updated_at. Po BROKER_BACKFILL_MAX_RETRIES (např. 8) přepni run na failed s HISTORY_RETRY_EXHAUSTED_ERROR.
   - Po úspěšném kroku (staged stránky nebo dokončená finalizace) retry_count vynuluj.
   - Žádná migrace. Použij existující sloupce retry_count, updated_at, last_error, review_details a state.
   - routers/broker.py NEMĚŇ, patří úkolu B1. get_history_status pro state=failed vrací obecnou hlášku, konkrétní důvod uvidí uživatel přes needs_attention a last_error připojení. Nové konstanty dej do t212_sync.py.
2. claim_or_create_run: insert v SAVEPOINTu (with db.begin_nested(): db.add(run); db.flush()). Chytej jen IntegrityError, po kolizi znovu načti aktivní run a vrať ho. Rollbackne se jen savepoint, takže snapshot i RLS kontext (set_config proběhl před savepointem) zůstanou. Ověř, jestli SAVEPOINT funguje v SQLite fast suite. Pokud ne, použij begin_nested jen pro postgresql, stejným vzorem jako jinde v kódu.
3. Testy:
   - backend/tests/test_broker_backfill.py:
     - 401 přepne run na failed a připojení na needs_attention, další tick run neclaimne;
     - ValueError ve finalize přepne run na needs_review a history_run_decision vrátí "blocked";
     - přechodná chyba zvýší retry_count a v backoff okně se run neclaimuje;
     - po max pokusech je run failed;
     - úspěch vynuluje retry_count;
     - po failed vytvoří příští sync nový run.
   - backend/tests/postgres/: dvě session zavolají claim_or_create_run souběžně a druhý insert narazí na index. Musí se vrátit existující run a snapshot zapsaný dřív ve stejné transakci musí po commitu existovat. Varianta s job kontextem (_set_job_workspace_context) nesmí ztratit RLS kontext.
4. Fast suite a PostgreSQL suite na vlastním kontejneru (port 55454).
5. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci shrnutí: nové stavy a konstanty, jak se projeví v UI, výsledky testů.
```

---

## Úkol A5: Free plán na dashboardu (N6)

```text
Dashboard nesmí na plánu bez standard_research volat Investor endpointy. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/dashboard-free-plan-gating z aktuálního main.

KONTEXT (review 2026-10-14, nález N6)
- frontend/src/pages/Dashboard.jsx: dotazy fetchMovers (ř. 84) a fetchEarnings (ř. 94) nemají enabled a <Heatmap /> (ř. 462) se renderuje vždy.
- Backend tyto endpointy chrání capability standard_research (Investor, backend/plans.py MINIMUM_PLAN): /portfolio/movers, /portfolio/earnings, /portfolio/heatmap v routers/portfolio.py.
- Na Free plánu v cloudu proto každé načtení dashboardu vrátí 3× 403 plan_upgrade_required (s retry: 1 dvakrát). Karty ukážou chybu a interceptor v api.js vyvolá portfyl:entitlement-denied, takže vyskočí UpgradePrompt.
- Commit 3578967 ("no paid requests before the plan loads") ohlídal jen widgety insider, analytics a dividend.

ÚKOL
1. hasStandardResearch = capabilities.has("standard_research"). Dotazy movers a earnings dostanou enabled: hasStandardResearch a <Heatmap /> se renderuje jen s touto capability (jeho useQuery se pak nespustí). Dokud se plán načítá (capabilitiesPending), ukaž skeleton bez requestu, stejně jako u insider karty.
2. Bez capability ukaž v těch slotech kartu bez síťového volání: krátký text "Dostupné od plánu Investor" a odkaz na /pricing. Místo heatmapy můžeš použít i něco z už načtených holdings, rozhodni a zdůvodni. Layout DashboardGrid nesmí poskočit.
3. Proveď rychlý audit ostatních stránek (Analytics, Dividends, Stock, Watchlists…). Hledej další dotazy na endpointy nad Free, které nejsou gatované podle plánu. NEOPRAVUJ je, jen je vypiš ve shrnutí, protože ty soubory patří jiným úkolům a vlnám.
4. Testy ve frontend/src/pages/Dashboard.async.test.jsx:
   - Free plán: fetchMovers, fetchEarnings a fetchHeatmap se nezavolají a nevznikne portfyl:entitlement-denied;
   - Investor: všechny tři se zavolají;
   - plán se ještě načítá: nezavolá se žádný.
5. Z frontend/: npm test, npm run test:cloud, npm run build, npm run build:cloud. Volitelně vizuálně na vlastních portech (backend 8015, vite 5185) s vlastní dev DB nebo před či po UI ověření A2.
6. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci shrnutí, výsledky a seznam z auditu (bod 3).
```

---

## Úkol A6: Časový test a výkon výkonové řady (N12, N13)

```text
Oprav časový test 3 let v tax reportu a kvadratický výpočet výkonové řady. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/tax-time-test-perf-series z aktuálního main.

KONTEXT (review 2026-10-14, nálezy N12 a N13)
- backend/routers/analytics.py _compute_capital_gains (ř. 322): cz_exempt_time_test = holding_days > CZ_TIME_TEST_DAYS, kde CZ_TIME_TEST_DAYS = 365*3+1 = 1096.
  - §4 odst. 1 písm. w) ZDP osvobozuje převod, "přesáhne-li doba mezi nabytím a převodem 3 roky". Rozhoduje kalendářní výročí, ne počet dní.
  - Příklad: nákup 2021-01-10, prodej 2024-01-11 je 1096 dní. Kód ho označí jako zdanitelný, správně je osvobozený.
  - _compute_unrealized_gains naopak hlásí cz_exempt_time_test=True už v den výročí (days_to_exemption <= 0).
  - cz_exempt_date je dnes výročí. frontend/src/pages/TaxReport.jsx ho popisuje jako "Tax-free if sold on or after {date}".
- _build_value_cashflow_series (ř. 722) v cash-aware větvi volá pro každý obchodní den cash_balance_by_currency(cash_txns_to_date) nad všemi dosavadními transakcemi a každý den skenuje všechny zbylé klíče txns_by_date. Složitost je O(dní × transakcí). Funkci volá /portfolio/performance, /analytics/risk-metrics i /analytics/benchmarks/comparison.

ÚKOL
1. Časový test:
   - první osvobozený den = _add_years(buy_date, 3) + 1 den; ověř chování _add_years pro nákup 29. 2.;
   - realizované obchody: exempt = sell_date >= první osvobozený den;
   - nerealizované loty: days_to_exemption = (první osvobozený den - today).days, exempt = days_to_exemption <= 0;
   - cz_exempt_date = první osvobozený den (sedí s textem "on or after" v TaxReport.jsx);
   - CZ_TIME_TEST_DAYS odstraň, pokud ji už nic nepoužívá. TaxReport.jsx měň jen tehdy, když text nebude odpovídat.
2. Výkonová řada: udržuj průběžný dict zůstatků (start = cash_balance_by_currency(pre_window_cash)) a přičítej signed_cash jen transakcí daného dne. Transakce procházej jedním ukazatelem po seřazených datech místo skenování klíčů každý den, i v ne-cash větvi. Výsledky musí být bitově stejné, proto sčítej ve stejném pořadí.
3. Testy:
   - časový test: 2021-01-10 → 2024-01-10 neosvobozeno, → 2024-01-11 osvobozeno; období s 29. 2.: 2021-03-01 → 2024-03-01 ne, → 2024-03-02 ano; nákup 2020-02-29; nerealizovaný lot v den výročí ne, den poté ano; souhrn czech_tax se přepočítá;
   - výkon: test ekvivalence nové a staré implementace (starou zkopíruj do testu jako referenci) na generovaných ledgerech: více měn, depozita a výběry, splity, transakce před prvním obchodním dnem, víc transakcí v jednom dni. Porovnej V i C. Do shrnutí změř čas před a po (např. 5 000 transakcí × 5 let).
4. Z backend/: python -m pytest tests/ -v --ignore=tests/postgres. PostgreSQL suite potřeba není; pokud ji spustíš, tak na vlastním kontejneru na portu 55456. Když měníš TaxReport.jsx: npm test a npm run build (TaxReport existuje jen v local edici).
5. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci shrnutí, výsledky testů a měření.
```

---

## Úkol A7: Validace vstupů ledgeru a kurz do USD (N5, N9)

```text
Zabraň uložení NaN a nevalidních typů do ledgeru a oprav fallback kurzu do USD. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/ledger-input-validation z aktuálního main.

KONTEXT (review 2026-10-14, nálezy N5 a N9)
- backend/routers/portfolio.py _parse_import_content, nativní formát (ř. 396–414): float(row["shares"]) a float(row["price"]) projdou i s prázdnou buňkou (pandas NaN). Prázdný ticker se uloží jako "NAN" a type se nekontroluje. build_preview (import_workflow.py) NaN nevaliduje.
  - Řádek s NaN cenou mimo 20řádkový vzorek náhledu se commitne. Pak GET /portfolio/holdings a /summary padají na 500, protože JSONResponse má allow_nan=False.
  - NaN v shares pozici tiše vyřadí z holdings.
  - NaN ve vzorku shodí na 500 už náhled.
- backend/schemas.py TransactionCreate (POST /portfolio/transactions): type je libovolný str, shares a price float bez omezení (projde i JSON NaN). POZOR: TransactionResponse z něj dědí. Omezení by se tak aplikovala i na odpovědi a stará data by shodila GET /portfolio/transactions na 500. Modely odděl.
- backend/routers/portfolio.py _live_to_usd (ř. 1656–1671): při chybě Yahoo vrátí 1.0 a úspěšný kurz cachuje v _USD_FX_CACHE navždy. T212 CZK dividendy (cash_currency CZK) se pak počítají jako USD, tedy asi 23× víc, v get_dividend_forecast i v analytics.py (_ccy_to_usd a _lifetime_money_weighted importují _live_to_usd).

ÚKOL
1. Nativní CSV, kontrola každého řádku:
   - ticker neprázdný a ne "NAN";
   - type ∈ {buy, sell, dividend}; jiný typ je chyba řádku s výčtem podporovaných typů;
   - shares a price konečná čísla > 0 (math.isfinite);
   - platné datum (NaT je chyba);
   - currency 3 písmena.
   Chyby sbírej per řádek jako dnes (max 100) a celý import odmítni. T212 parser neměň, ten prázdné hodnoty už odmítá.
2. Schemas:
   - TransactionCreate: type jako Literal["buy","sell","dividend"]; ticker se strip a délkou 1–32; shares a price Field(gt=0, allow_inf_nan=False); currency s patternem.
   - TransactionResponse jako samostatný model bez těchto omezení, tvar odpovědi beze změny.
   - Ověř frontendový formulář přidání transakce (frontend/src/pages/Transactions.jsx apod.), jestli neposílá jiný type. Jen zjisti a napiš, nic tam neměň.
3. _live_to_usd:
   - TTL cache (např. 10 min) a last-known-good jako u _live_fx_to_czk;
   - když chybí přímý kurz, zkus pivot přes CZK: _live_fx_to_czk(ccy) / _live_fx_to_czk("USD");
   - pro ne-USD měnu nikdy tiše nevracej 1.0 bez warning logu.
   Signaturu (vrací float) NEMĚŇ, analytics.py patří úkolu A6.
4. Do shrnutí přidej read-only SQL z přílohy A plánu pro kontrolu existujících NaN a Inf řádků v produkci. Sám ho na produkci NESPOUŠTĚJ.
5. Testy:
   - backend/tests/test_import_workflow.py: prázdná cena na řádku 30 vrátí 400 s číslem řádku a nic se neuloží; dál prázdné shares, prázdný ticker, neznámý typ, NaT datum; preview nikdy nevrací NaN;
   - POST /portfolio/transactions s NaN, záporným nebo nulovým množstvím a s neznámým type vrátí 422;
   - GET /portfolio/transactions dál vrací staré řádky (např. dividendu s price 0);
   - _live_to_usd: při výpadku použije last-known-good, při studeném startu s výpadkem pivot, cache expiruje.
6. Fast suite a PostgreSQL suite na vlastním kontejneru (port 55457).
7. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci shrnutí, výsledky testů a zjištění z bodu 2.
```

---

## Úkol A8: Omezené in-process cache (N14)

```text
Omez velikost in-process cache, aby paměť instance nerostla bez konce. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/bounded-caches z aktuálního main.

KONTEXT (review 2026-10-14, nález N14)
backend/cache.py ttl_cache ukládá do _store a expirované položky jen přepisuje pro stejný klíč, nikdy je neodstraní. Klíče vznikají z uživatelských vstupů (q, ticker, period, view) na /market/search, /market/history/{ticker}, /market/fundamentals/{ticker}, /market/quote/{ticker}, /market/fx/{pair} a dalších. Totéž platí pro:
- backend/market_data.py (_cache, _attr_cache, _inflight);
- backend/routers/market.py (_SEARCH_CACHE, _FUND_CACHE a další modulové dicty);
- backend/fx.py (_DAILY_CACHE).
Paměť dlouho žijící Cloud Run instance tak roste až k OOM.

ÚKOL
1. V backend/cache.py napiš malou thread-safe BoundedTTLCache (OrderedDict + Lock, maxsize, TTL, vyřazování LRU, prořez expirovaných položek při zápisu). BEZ nové závislosti, backend/requirements.txt patří úkolu B2.
2. ttl_cache(seconds, maxsize=…) postav nad ní. Zachovej async variantu i to, že se výjimky necachují.
3. Nahraď neomezené dicty v market_data.py, routers/market.py a fx.py. V routers/market.py měň jen deklarace cache a přístup k nim, nic jiného. maxsize nastav podle velikosti hodnot (fundamentals malé, search větší). _inflight v market_data uklízej i u futures, které nikdo nevyzvedne.
4. Veřejné API market_data (get_info, get_infos, download, ticker_attrs, quote) a fx (fetch_fx_to_czk, bulk_fetch_fx, convert_amount) zůstane beze změny, používají ho jiné úkoly.
5. Testy: vyřazování podle velikosti a TTL, pořadí LRU, výjimky se necachují, základní souběh vláken, async varianta. Existující testy market a fx musí projít.
6. Z backend/: python -m pytest tests/ -v --ignore=tests/postgres. PostgreSQL suite potřeba není.
7. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci shrnutí a výsledky testů.
```

---

## Integrace vlny 1

```text
Integruj vlnu 1 opravy z code review do main. Řiď se CLAUDE.md a docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Pracuj v hlavním checkoutu C:\Users\tomzo\claude\portfyl, který musí mít čistý git status.

1. Pro každou hotovou větev v pořadí fix/discord-webhook-ssrf, fix/csrf-session-token, fix/job-advisory-lock, fix/t212-backfill-dead-letter, fix/dashboard-free-plan-gating, fix/tax-time-test-perf-series, fix/ledger-input-validation, fix/bounded-caches:
   - git merge --no-ff <větev>;
   - při konfliktu se zastav a zeptej se;
   - po každém merge pusť z backend/: python -m pytest tests/ -v --ignore=tests/postgres.
2. Na konci pusť celé ověření:
   - PostgreSQL suite na vlastním kontejneru (port 55491);
   - z frontend/: npm test, npm run test:cloud, npm run build, npm run build:cloud;
   - zkontroluj, že alembic heads vrací 0023_allocation_targets a sedí s EXPECTED_ALEMBIC_HEAD.
3. Worktree hotových větví neodstraňuj bez mého souhlasu.
NEPUSHUJ a NEDEPLOYUJ. Na konci shrnutí a výsledky.
```

Vlny 2 a 3 integruj stejným promptem, jen s jinými větvemi:

- vlna 2: `fix/capacity-lock-scope`, `chore/ci-runtime-lock`;
- vlna 3: `feat/ledger-finite-check`. Kontrola `alembic heads` pak musí vrátit
  novou revizi `0024_…`, shodnou s `EXPECTED_ALEMBIC_HEAD`.

---

## Úkol B1: Zámek workspace a obcházení entitlementů (N8, N10)

Spustit až po integraci A7 a A8 do `main`.

```text
Zkrať držení zámku workspace na samotný zápis a zavři díry v entitlementech. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev fix/capacity-lock-scope z aktuálního main (obsahuje už A7 a A8).

KONTEXT (review 2026-10-14, nálezy N8 a N10)
- backend/entitlements.py require_capacity a require_broker_capacity berou SELECT … FOR UPDATE na řádek workspaces (stejný zámek jako ledger_mutation.acquire_workspace_ledger_lock) a nechávají transakci otevřenou. Handlery pak před commitem volají síť:
  - routers/portfolio.py create_transaction: market_data.get_info a fetch_fx_to_czk;
  - routers/watchlists.py add_item: flush a pak _quote(), tedy neomezené yfinance .info;
  - routers/broker.py connect: KMS decrypt a až 3 HTTP volání T212 po 10–15 s;
  - routers/polymarket.py connect a routers/ibkr.py connect.
  database.release_request_connections spojení neuvolní: buď existuje flushnutý zápis, nebo dependency běžela v jiné kopii contextvar (viz komentář v require_capability). Mezitím čeká každý zápis ve workspace, včetně finalize_run v broker_backfill jobu.
  CLAUDE.md: "Call `database.release_connection` before slow outbound calls."
- require_writable_resource porovnává surový path string se str(row.public_id). UUID velkými písmeny nebo bez pomlček kontrolu obejde, FastAPI ho přesto rozparsuje.
- require_writable_broker bez query portfolio_id kontrolu přeskočí, ale route použije default portfolio.
- POST /cash (routers/cash.py) nemá require_capacity, takže obchází limit transakcí.

ÚKOL
1. entitlements.py:
   - require_capacity a require_broker_capacity udělej jako rychlou kontrolu BEZ zámku (pro brzkou 403), na konci release_connection(db);
   - nové enforce_capacity_locked(db, workspace_id, entitlements, resource, model, increase=1) a enforce_broker_capacity_locked(...): acquire_workspace_ledger_lock, count a ensure_count_limit (u brokerů overflow logika). Je to autoritativní kontrola v zapisující transakci;
   - require_writable_resource: UUID(raw) (neplatné vrací 404) a porovnání UUID, ne stringů;
   - require_writable_broker a require_broker_capacity berou Portfolio přes Depends(require_portfolio), aby kontrolovaly přesně to portfolio, které použije route, i bez portfolio_id.
2. Handlery: nejdřív veškerá síť, bez zámku a bez drženého spojení (release_connection(db) před voláním). Pak zámek, enforce_*_locked, znovu načíst stav, který se mezitím mohl změnit, zápis a commit. Týká se:
   - portfolio.create_transaction, portfolios.create_portfolio, alerts.create_alert;
   - watchlists.create_watchlist a add_item: quote až po commitu nebo předem, přes market_data.get_infos místo _quote a .info. list_watchlists taky přes get_infos;
   - cash.create_cash, včetně kvóty "transactions";
   - broker.connect: ověření klíče a account summary před zámkem, po zámku znovu načti connection a znovu _bind_verified_account. Clash kontrola přes decrypt klíčů zůstane jen před zámkem jako UX, autoritativní je fingerprint binding pod zámkem;
   - polymarket.connect a ibkr.connect.
   Bonus ve stejném souboru: broker.get_status dešifruje api_key 3× (3 KMS volání), dešifruj jednou.
3. Konečná čísla na vstupu (rozhodnutí R3, předpoklad pro migraci C1): CashCreate.amount a RateItem.annual_rate (routers/cash.py) a AlertCreate/AlertUpdate.target_price (routers/alerts.py) dostanou allow_inf_nan=False. Starlette parsuje JSON přes json.loads, který přijme literály NaN a Infinity, a pydantic je u float polí bez tohoto omezení pustí dál.
4. Testy:
   - backend/tests/postgres: dva souběžné create na limitu-1 (transakce, watchlist item, broker connect) a projde právě jeden. Během mocku síťového volání ověř, že workspace řádek není zamčený (např. FOR UPDATE NOWAIT z druhého spojení).
   - Bypassy: PATCH a POST na overflow watchlist s UUID velkými písmeny i bez pomlček vrátí 403 resource_read_only; sync bez portfolio_id na overflow default portfoliu vrátí 403; POST /cash nad limitem Free vrátí 403 quota_exceeded.
   - Neplatná čísla: POST /cash s amount Infinity, PUT /cash/interest-rates s annual_rate Infinity a POST /alerts s target_price NaN (JSON literály) vrátí 422 a nic se neuloží.
   - Uprav existující testy, které spoléhaly na zámek v require_capacity (např. backend/tests/postgres/test_billing_concurrency.py).
5. Fast suite a PostgreSQL suite na vlastním kontejneru (port 55461).
6. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Na konci shrnutí a výsledky testů.
```

---

## Úkol B2: Runtime CI vs. produkce a lock závislostí (N15)

```text
Sjednoť runtime CI s produkcí a zamkni závislosti. Řiď se CLAUDE.md a pravidly v docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md. Vlastní worktree, větev chore/ci-runtime-lock z aktuálního main. V tu dobu nesmí backend/requirements.txt měnit nikdo jiný.

KONTEXT (review 2026-10-14, nález N15)
- Dockerfile: runtime python:3.14-slim, build frontendu node:22-alpine.
- .github/workflows/ci.yml: Python 3.12, Node 20.
- backend/requirements.txt má jen dolní meze (fastapi>=0.115, pandas>=2.0, …) a lock neexistuje. Každý docker build může přitáhnout jinou major verzi a produkční kombinace se v CI nikdy netestuje.
- start.bat instaluje přes uv do Pythonu 3.12.

ÚKOL
1. Podle rozhodnutí R2 v plánu: joby backend-fast i backend-postgres v CI jako matrix Python [3.12, 3.14], frontend job na Node 22. Dockerfile zůstává na python:3.14-slim a node:22-alpine. Na jednu verzi Pythonu se zatím nesjednocuje, to je navazující úklid v sekci Nasazení. Pokud něco na 3.14 v CI selže, oprav to jen v rámci souborů tohoto úkolu, jinak se zastav a zeptej.
2. Lock: uv pip compile backend/requirements.txt --universal --generate-hashes -o backend/requirements.lock, obdobně pro dev extras (např. backend/requirements-dev.lock). requirements.txt zůstává vstupní specifikace.
3. Dockerfile instaluje z backend/requirements.lock (pip install --require-hashes). CI instaluje z locků. Bootstrap ve start.bat taky z locku.
4. CLAUDE.md, krátce do sekcí "Run it" a "Tests": jak lock aktualizovat a že requirements*.txt a *.lock jsou hotspot (jen jeden úkol najednou).
5. Ověř:
   - lokálně fast suite na 3.12 i 3.14 (uv venv --python 3.14);
   - docker build, pokud je Docker k dispozici (jinak to napiš);
   - YAML workflow (actionlint, pokud je, jinak pečlivě ručně).
6. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. CI se ověří po pushi, který udělám já. Na konci shrnutí.
```

---

## Úkol C1: DB CHECK na konečná čísla v ledgeru (N5)

Předpoklad (rozhodnutí R3): A7 i B1 jsou nasazené v produkci (nasazení 1) a
dotaz z přílohy A vrátil 0 řádků, případně data opravil vlastník. Jediný
úkol s migrací. V tu dobu nikdo jiný nemění `backend/alembic/versions/` ani
`EXPECTED_ALEMBIC_HEAD`.

```text
Přidej do DB pojistku proti NaN a Inf v transakcích. Řiď se CLAUDE.md (pravidla pro migrace a "Parallel session safety") a docs/superpowers/plans/2026-10-14-portfyl-code-review-fixes.md (hlavně rozhodnutí R3). Vlastní worktree, větev feat/ledger-finite-check z aktuálního main.

Než začneš, ověř se mnou, že nasazení 1 (A7 a B1) je v produkci a dotaz z přílohy A vrátil 0 řádků.

ÚKOL
1. Nová migrace backend/alembic/versions/0024_transactions_finite_numbers.py:
   - ALTER TABLE transactions ADD CONSTRAINT ck_transactions_finite_numbers CHECK (...) NOT VALID;
   - podmínka: shares a price NOT IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8); amount, cash_amount a fx_to_czk jsou NULL nebo splňují totéž;
   - ve stejné migraci hned potom ALTER TABLE transactions VALIDATE CONSTRAINT ck_transactions_finite_numbers (rozhodnutí R3: při špatných datech selže celá migrace a nic se nezmění);
   - downgrade: DROP CONSTRAINT;
   - constraint jen v migraci, ne v models.py. SQLite fast suite by PostgreSQL syntaxi neunesla, stejný vzor jako partial index v 0015.
2. backend/database.py: EXPECTED_ALEMBIC_HEAD = přesná nová head revize. alembic heads musí vrátit jedinou head.
3. Vlastní testovací DB (port 55471): alembic upgrade head s migration-owner credential, pak downgrade -1 a znovu upgrade head. Test v backend/tests/postgres/: insert NaN do transactions selže a platný insert projde; assert_alembic_head projde.
4. Forward-compatibility podle CLAUDE.md: NOT VALID constraint neblokuje platné zápisy starších instancí, neplatné odmítne, a to je žádoucí.
5. Commit jen souborů tohoto úkolu (Co-Authored-By řádek), pak git merge main a testy znovu.
NEPUSHUJ, NEDEPLOYUJ a NEMERGUJ do main. Pro produkci se Cloud Run migration job (deploy/run-migrations.ps1) pouští PŘED deployem služby, to udělám já.
```

---

## Nasazení

Vždy jen na výslovný pokyn vlastníka.

**Nasazení 1 (vlny 1 a 2, bez migrace)**

1. Push `main`, zelená CI (po B2 včetně matrix 3.12 a 3.14) a deploy podle
   `deploy/cloudrun.md`. `EXPECTED_ALEMBIC_HEAD` zůstává
   `0023_allocation_targets`, migration job není potřeba.
2. Po nasazení ověř:
   - `/health`: všechny joby `ok`;
   - v logu nepřibývá `skipped, already running` (A3);
   - T212 history runy se neopakují donekonečna (A4);
   - testovací Free účet nevidí na dashboardu žádnou 403 (A5);
   - mutace a odhlášení fungují ve dvou tabech (A2). Během rolling deploye
     může v otevřených tabech jednou proběhnout retry po `csrf_failed`, to
     je očekávané (R1).
3. Spusť dotaz z přílohy A. Až vrátí 0 řádků, může začít vlna 3 (C1).

**Nasazení 2 (vlna 3, s migrací)**

1. Po integraci C1: push `main`, zelená CI.
2. Cloud Run migration job (`deploy/run-migrations.ps1`) s migration-owner
   credential, teprve potom deploy služby (CLAUDE.md).
3. Ověř `/health` a to, že backend nastartoval s novou
   `EXPECTED_ALEMBIC_HEAD`.

**Navazující úklid**

- R1: 30 dní po nasazení 1 (maximální stáří session) odstranit legacy větev
  v `csrf_matches`. Sloupec `auth_sessions.csrf_digest` zůstává (nové
  session do něj dál ukládají digest odvozeného tokenu). Jeho případné
  odstranění je destruktivní krok pro samostatnou pozdější vlnu.
- R2: po dvou týdnech zelené matrix přepnout dev (`start.bat`, CLAUDE.md) na
  Python 3.14 a 3.12 z CI odstranit.

## Příloha A: kontrola existujících NaN a Inf v produkci (read-only)

Spouští vlastník v Neon konzoli pod migration-owner rolí. Runtime role by
bez RLS kontextu neviděla žádné řádky.

```sql
SELECT workspace_id, portfolio_id, count(*) AS bad_rows
FROM transactions
WHERE shares      IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8)
   OR price       IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8)
   OR amount      IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8)
   OR cash_amount IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8)
   OR fx_to_czk   IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8)
GROUP BY workspace_id, portfolio_id;
```

V PostgreSQL platí `'NaN'::float8 = 'NaN'::float8`, takže `IN` NaN najde.
`NULL` se nevybere.
