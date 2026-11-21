# Free trial: živý průchod (Step 5 ověřovacího plánu)

Stav: **čeká na ruční provedení** (nelze automatizovat: nemáme Firebase emulátor
a agent nemůže vytvářet Firebase účty ani klikat na ověřovací e-maily).
Navazuje na `2026-11-19-free-trial-verification.md` (Step 5) a na
`2026-11-19-portfyl-free-trial-completion.md`. Nic se při něm nenasazuje a
nesahá se na produkční Cloud Run, Secret Manager ani Cloudflare.

Cíl: v prohlížeči proti lokálně spuštěné **cloud edici** ověřit scénáře a až i
z kapitoly D a u každého zapsat **prošlo / neprošlo**. Pak (Krok F) se oba plány
o trialu přesunou do `docs/finished.md`.

Pozor: scénář (d) smaže účet i **ve Firebase** (projekt `portfyl-cloud-fstxby`,
pravděpodobně sdílený s produkcí). Použij pro (d) schránku, o kterou ti nevadí
přijít, a nikdy ne produkční účet.

## Dohodnuté účty

| Označení | E-mail | Scénáře |
|---|---|---|
| A | `tomas@jzd.cz` | a, b, c, d (a import IBKR pro e) |
| B | `tom@jzd.cz` | e |
| C | `tom.zoubek@gmail.com` | f, g |

(Změň podle sebe. Pozvánky v databázi musí odpovídat; viz krok A.6. Ověřovací
e-maily musí do schránek skutečně dorazit.)

## Co potřebuješ mít na novém zařízení

- Git, **Docker Desktop**, **uv** (https://docs.astral.sh/uv/), **Node 22**.
- Přístup k repozitáři (`git fetch`).
- Soubory, které **nejsou v gitu** (zkopíruj z původního počítače, nebo je vytvoř):
  - `.env` v kořeni repozitáře. Pro tento průchod stačí `GOOGLE_CLOUD_PROJECT=<id Firebase projektu>`
    (ostatní proměnné nastavuje krok B). Když backend nenastartuje, název chybějící
    proměnné je v poslední řádce chyby.
  - `frontend/.env.local` s `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`,
    `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID` (a volitelně
    `VITE_FIREBASE_GOOGLE_SIGN_IN`, `VITE_GOOGLE_OAUTH_CLIENT_ID`).
    Bez něj se v prohlížeči objeví `invalid-api-key`.
  - Pro (d) (smazání Firebase identity) backend potřebuje oprávnění správce
    Firebase: `gcloud auth application-default login` jako uživatel s přístupem
    do projektu. Bez něj smazání účtu skončí chybou; ostatní scénáře to
    nepotřebují.
- PowerShell. Všechny příkazy níže jsou PowerShell; `$REPO` je tvoje klonovaná
  složka Portfylu, `$E2E` je jednorázový worktree.

Každý příkaz spouštěj v okně, které je u něj uvedeno. Okno č. 1 = backend,
č. 2 = frontend, č. 3 = databáze a příkazy kolem.

---

## A. Příprava (jednou, okno č. 3)

### A.1 Jednorázový worktree z `main`

```powershell
$REPO = "C:\cesta\k\portfyl"
git -C $REPO fetch origin
git -C $REPO worktree add --detach "$REPO\..\portfyl-trial-e2e" origin/main
$E2E = (Resolve-Path "$REPO\..\portfyl-trial-e2e").Path
```

- **Správně:** `HEAD is now at …` a složka `portfyl-trial-e2e` existuje.
- **Špatně:** `fatal: … is already checked out` nebo složka existuje. Smaž starý worktree
  (`git -C $REPO worktree remove --force <cesta>`) a zopakuj.

### A.2 Soubory mimo git

Zkopíruj `.env` do `$E2E\.env` a `frontend\.env.local` do `$E2E\frontend\.env.local`
(viz „Co potřebuješ“).

```powershell
Copy-Item "$REPO\.env" "$E2E\.env"
Copy-Item "$REPO\frontend\.env.local" "$E2E\frontend\.env.local"
```

- **Špatně:** `Cannot find path` → soubor v `$REPO` není; vytvoř ho podle seznamu výše.

### A.3 Python prostředí (čerstvé, z uzamčených verzí)

```powershell
Set-Location "$E2E\backend"
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe --require-hashes -r requirements.lock
$py = "$E2E\backend\.venv\Scripts\python.exe"
```

- **Správně:** `uv` doinstaluje balíčky bez chyby. Důležité je mít čerstvé prostředí
  (starý `.venv` v repozitáři nemusí mít `openpyxl` a import brokerů pak selže).
- **Špatně:** `uv: command not found` → nainstaluj uv. Chyba hashe → zkus znovu s čistou cache
  (`uv cache clean`).

### A.4 Databáze Postgres v Dockeru

```powershell
docker compose -f "$E2E\deploy\docker-compose.postgres-dev.yml" up -d --wait
docker compose -f "$E2E\deploy\docker-compose.postgres-dev.yml" exec postgres psql -U portfyl_dev -d portfyl_dev -c "CREATE DATABASE portfyl_trial_e2e"
```

- **Správně:** `CREATE DATABASE`; kontejner je `healthy`. Databáze je **jen testovací**,
  neovlivní žádná skutečná data. Postgres poslouchá na portu **15432**.
- **Špatně:** `database "portfyl_trial_e2e" already exists` je v pořádku (přeskoč).
  `port is already allocated` → jiný Postgres už běží na 15432; zastav ho.

### A.5 Migrace na nejnovější verzi

```powershell
$env:DATABASE_URL = "postgresql+psycopg://portfyl_dev:portfyl_dev@localhost:15432/portfyl_trial_e2e"
Set-Location "$E2E\backend"
& $py -m alembic upgrade head
& $py -m alembic current
```

- **Správně:** poslední řádek `0028_password_changed_seen (head)`.
- **Špatně:** jiná verze, nebo chyba spojení → zkontroluj, že kontejner běží (A.4).

### A.6 Pozvánky (beta gate pustí jen pozvané e-maily)

```powershell
docker compose -f "$E2E\deploy\docker-compose.postgres-dev.yml" exec postgres psql -U portfyl_dev -d portfyl_trial_e2e -c "INSERT INTO beta_invites (id, email) VALUES (gen_random_uuid(), 'tomas@jzd.cz'), (gen_random_uuid(), 'tom@jzd.cz'), (gen_random_uuid(), 'tom.zoubek@gmail.com') ON CONFLICT (email) DO NOTHING"
docker compose -f "$E2E\deploy\docker-compose.postgres-dev.yml" exec postgres psql -U portfyl_dev -d portfyl_trial_e2e -c "SELECT email, status FROM beta_invites ORDER BY email"
```

- **Správně:** výpis tří adres, všechny `invited`. (E-maily musí být malými písmeny.)
- **Špatně:** `violates check constraint ck_beta_invites_email_normalized` → v e-mailu je
  velké písmeno nebo mezera.

### A.7 Úprava Vite proxy (jen pro tento test, necommituj)

Cloud backend přijímá `/api` jen s hlavičkou od Cloudflare. Pro lokální test ji vkládá Vite.
V `$E2E\frontend\vite.config.js` rozšiř objekt `"/api"` v `server.proxy` (za `changeOrigin: true,`):

```js
          // E2E only (not for the repo): stand in for the Cloudflare edge.
          ...(env.VITE_E2E_EDGE_TOKEN
            ? { headers: { "X-Portfyl-Edge-Token": env.VITE_E2E_EDGE_TOKEN, "CF-Connecting-IP": "127.0.0.1" } }
            : {}),
```

- **Správně:** soubor vypadá jako blok `"/api": { target: …, changeOrigin: true, …tento kus… }`.
- **Špatně:** bez této úpravy API volání v prohlížeči končí `403 untrusted_edge`.

### A.8 Ukázkový IBKR soubor pro scénář (e)

Syntetický export je v repozitáři:
`$E2E\backend\tests\fixtures\brokers\ibkr\flex_2025_sample.xml`.

---

## B. Backend na portu 8010 (okno č. 1)

```powershell
Set-Location "$E2E\backend"
Get-Content ..\.env | ForEach-Object { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item "env:$($Matches[1].Trim())" $Matches[2] } }
$env:DATABASE_URL = "postgresql+psycopg://portfyl_dev:portfyl_dev@localhost:15432/portfyl_trial_e2e"
$env:PORTFYL_EDITION = "cloud"
$env:PORTFYL_TRIAL_FINGERPRINT_KEY = "e2e-trial-fingerprint-key-0123456789abcdef"
$env:PORTFYL_TURNSTILE_SECRET = "1x0000000000000000000000000000000AA"
$env:PORTFYL_TURNSTILE_TEST_KEYS = "1"
$env:PORTFYL_APP_URL = "http://localhost:5180"
$env:PORTFYL_EDGE_TOKEN = "e2e-edge-token-0123456789abcdef"
$env:RATE_LIMIT_KEY_SECRET = "e2e-rate-limit-key-secret-0123456789"
$env:PORTFYL_ACCOUNT_FINGERPRINT_KEY = "e2e-account-fingerprint-key-0123456789abcdef"
foreach ($r in "GLOBAL","AUTH_SESSION","BROKER_SYNC","AUTH_EMAIL","AUTH_EMAIL_TARGET") { Set-Item "env:RATE_LIMIT_${r}_LIMIT" "1000"; Set-Item "env:RATE_LIMIT_${r}_WINDOW_SECONDS" "60" }
Remove-Item env:PORTFYL_BILLING_ENABLED -ErrorAction SilentlyContinue
$py = "$E2E\backend\.venv\Scripts\python.exe"
& $py -m uvicorn main:app --port 8010
```

(Pokud jsi v tomto okně nenastavil `$E2E`, nastav ho jako v A.1.)

- **Správně:** `Application startup complete.` a `Uvicorn running on http://127.0.0.1:8010`.
  Okno nech běžet.
- **Špatně:** dlouhý `Traceback` a poslední řádek `RuntimeError: … is required …`. Název
  proměnné je v té řádce. Zkontroluj, že jsi nevynechal řádek výše. Chyba
  `alembic_version` → neproběhl krok A.5 se stejnou `DATABASE_URL`.

## C. Frontend na portu 5180 (okno č. 2)

```powershell
Set-Location "$E2E\frontend"
npm install
$env:VITE_API_PROXY_TARGET = "http://localhost:8010"
$env:VITE_TURNSTILE_SITE_KEY = "1x00000000000000000000AA"
$env:VITE_E2E_EDGE_TOKEN = "e2e-edge-token-0123456789abcdef"
npm run dev -- --mode edition-cloud --port 5180
```

- **Správně:** `Local: http://localhost:5180/`; v prohlížeči se otevře landing nebo přihlášení Portfylu.
- **Špatně:** bílá stránka nebo `invalid-api-key` (chybí `frontend\.env.local`); v síťovém
  panelu `403 untrusted_edge` (chybí `VITE_E2E_EDGE_TOKEN` nebo úprava A.7);
  `Port 5180 is already in use`.

---

## D. Scénáře (prohlížeč `http://localhost:5180`, databáze v okně č. 3)

Zkratka pro příkazy do databáze (okno č. 3):

```powershell
function Invoke-E2eSql($sql) { docker compose -f "$E2E\deploy\docker-compose.postgres-dev.yml" exec postgres psql -U portfyl_dev -d portfyl_trial_e2e -c $sql }
```

### (a) Účet A dostane trial
Přihlas se / zaregistruj účet A (u nového účtu klikni na odkaz v ověřovacím e-mailu).

- **Správně:** může na okamžik naskočit ověření „nejste robot“ (testovací klíč projde sám).
  Pak se dostaneš do aplikace a nahoře je banner **„Zkušební Pro – zbývající dny: 10“**.
  V databázi: `Invoke-E2eSql "SELECT ends_at FROM trial_grants"` vrátí jeden řádek zhruba za 10 dní.
- **Špatně:**
  - „Před přihlášením prosím ověřte e-mail…“ → odklikni odkaz z e-mailu.
  - „Ověření při registraci neprošlo. Zkuste to prosím znovu.“ → chybný `PORTFYL_TURNSTILE_SECRET` v okně č. 1.
  - Hláška o pozvánce → e-mail není v `beta_invites`.
  - Žádný banner → pošli screenshot a poslední řádky okna č. 1 (hledej 403/500).

Hned po (a), **dokud trial běží** (kvůli (e)): na účtu A naimportuj
`flex_2025_sample.xml` (Import → IBKR Flex XML → náhled → potvrdit).

- **Správně:** náhled ukáže řádky a po potvrzení se objeví transakce.
- **Špatně:** chyba importéru (typicky chybějící `openpyxl` → viz A.3) → pošli text chyby.

### (b) Odhlášení a přihlášení
- **Správně:** žádné ověření „nejste robot“, banner „zbývající dny: 10“ zůstává.
- **Špatně:** dialog ověření naskočí znovu, nebo banner zmizí.

### (c) Konec trialu
```powershell
Invoke-E2eSql "UPDATE trial_grants SET ends_at = now() - interval '1 day'"
```
Do minuty obnov stránku (F5).

- **Správně:** místo banneru oznámení **„Vaše zkušební Pro skončilo. Účet je nyní na tarifu Free: data zůstávají a vše nad limity Free je jen ke čtení.“** Dashboard ukáže jen Free widgety, bez chybové stránky.
- **Špatně:** dál „zbývající dny“ ani po 2 minutách s F5; nebo chybová stránka místo Dashboardu.

### (d) Smazání a znovu registrace stejné schránky
Nastavení → smazat účet A (opiš název workspace, počkej 10 s odpočet). Pak se zaregistruj znovu
se stejným e-mailem (nová pozvánka není potřeba) a ověř ho.

- **Správně:** účet na Free a oznámení **„Tento účet začíná na tarifu Free, protože pro tuto e-mailovou adresu nebo síť už bylo zkušební období využito.“**
- **Špatně:**
  - znovu banner „zbývající dny: 10“ (trial přidělen podruhé) → **chyba v kódu**, pošli mi to;
  - smazání skončí chybou o přihlašovacích údajích → chybí `gcloud auth application-default login`.

### (e) Stejný broker ve druhém účtu (nepovinné)
Přihlas účet B a naimportuj stejný `flex_2025_sample.xml`.

- **Správně:** oznámení **„Vaše zkušební Pro skončilo předčasně, protože tento účet u brokera už měl zkušební období…“**
- **Špatně:** trial u B normálně běží dál. (Podmínka: A naimportoval soubor *během* trialu, viz (a).)

### (f) Neprošlé ověření „nejste robot“
V okně č. 1 zastav backend (Ctrl+C) a spusť znovu s „špatným“ klíčem:

```powershell
$env:PORTFYL_TURNSTILE_SECRET = "2x0000000000000000000000000000000AA"; & $py -m uvicorn main:app --port 8010
```
Přihlas účet C a zkontroluj databázi:
```powershell
Invoke-E2eSql "SELECT email FROM users"
```

- **Správně:** hláška **„Ověření při registraci neprošlo. Zkuste to prosím znovu.“** a C v seznamu uživatelů **není**.
- **Špatně:** přihlášení projde, nebo se C v `users` objeví → **chyba v kódu**.

### (g) Trial vypnutý
Ctrl+C a spusť s vrácenými klíči a vypnutým trialem:

```powershell
$env:PORTFYL_TURNSTILE_SECRET = "1x0000000000000000000000000000000AA"; $env:PORTFYL_TRIAL_DAYS = "0"; & $py -m uvicorn main:app --port 8010
```
Přihlas účet C.

- **Správně:** účet se vytvoří a nikde není nic o trialu (banner ani zmínka na Ceníku).
- **Špatně:** banner o trialu se zobrazí.

### (h) Start bez klíče Turnstile
Ctrl+C a spusť bez klíče:

```powershell
Remove-Item env:PORTFYL_TURNSTILE_SECRET, env:PORTFYL_TURNSTILE_DISABLED, env:PORTFYL_TRIAL_DAYS -ErrorAction SilentlyContinue; & $py -m uvicorn main:app --port 8010
```

- **Správně:** server **nenastartuje**; chyba končí `PORTFYL_TURNSTILE_SECRET is required in the cloud edition (or set PORTFYL_TURNSTILE_DISABLED=1 to run without the sign-up bot check)`.
- **Špatně:** `Application startup complete` (server běží bez klíče) → **chyba v kódu**.

### (i) Lokální edice
Zastav obě okna a v hlavním repozitáři spusť běžné `start.bat` (porty 8000 a 5173), přihlas se obvyklým lokálním účtem.

- **Správně:** žádný banner o trialu a `/pricing` vypadá jako dřív.
- **Špatně:** banner o trialu je vidět, nebo se Ceník změnil.

Omezení: trial má limit 3 přidělení na IP za 30 dní a při testu přicházejí všechny
požadavky jako `127.0.0.1`. Kdyby se trial u nového účtu najednou nepřidělil, zkontroluj
`Invoke-E2eSql "SELECT count(*) FROM trial_ip_marks"` (a případně tabulku vyprázdni).

---

## E. Úklid

Zastav servery (Ctrl+C) a smaž testovací data:

```powershell
git -C $REPO worktree remove --force $E2E
docker compose -f "$REPO\deploy\docker-compose.postgres-dev.yml" exec postgres psql -U portfyl_dev -d portfyl_dev -c "DROP DATABASE portfyl_trial_e2e"
```

(Při chybě „Filename too long“ při mazání `node_modules` použij cestu s prefixem `\\?\`.)

## F. Po průchodu (to udělá Claude)

1. Zapiš do tabulky níže výsledek každého scénáře (prošlo / neprošlo, screenshot při selhání).
2. Neprošlé scénáře opravit. Pokud vše prošlo: přesunout `2026-11-19-portfyl-free-trial-completion.md` a
   `2026-11-19-free-trial-verification.md` do `docs/finished.md` a odškrtnout Tasks 1c, 3, 4 a 6
   v `2026-11-15-portfyl-landing-redesign-free-trial.md`. **Nenasazovat.**

| Scénář | Výsledek | Poznámka |
|---|---|---|
| a | | |
| b | | |
| c | | |
| d | | |
| e | | |
| f | | |
| g | | |
| h | | |
| i | | |
