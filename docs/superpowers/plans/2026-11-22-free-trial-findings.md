# Free trial: výsledek živého průchodu a nálezy

Průchod (a až i) proběhl 2026-11-22 ručně v prohlížeči proti lokální cloud edici
(backend :8010, frontend :5180, testovací databáze `portfyl_trial_e2e`,
Cloudflare testovací klíče, reálné Firebase účty). Postup byl v
`2026-11-21-free-trial-live-walkthrough.md`; ten je po dokončení smazán a je v
gitu (`git log --diff-filter=D -- docs/superpowers/plans/2026-11-21-free-trial-live-walkthrough.md`).
Nic se nenasazovalo.

## Výsledek scénářů

| Scénář | Výsledek | Co se ukázalo |
|---|---|---|
| a | prošlo | po prvním přihlášení banner „Zkušební Pro – zbývající dny: 10“ |
| b | prošlo | odhlášení a přihlášení: banner zůstal, bez nového ověření |
| c | prošlo | po `ends_at` v minulosti oznámení „Vaše zkušební Pro skončilo…“, Dashboard jen s Free widgety, bez chybové stránky |
| d | prošlo | po smazání účtu a nové registraci stejné schránky hláška „…už bylo zkušební období využito“, bez banneru; po smazání zůstaly otisky v `trial_identities`, `trial_ip_marks`, `trial_broker_marks` |
| e | prošlo | druhý účet naimportoval stejný IBKR soubor a trial skončil předčasně s hláškou o brokerovi |
| f | prošlo | s „špatným“ klíčem Turnstile: „Ověření při registraci neprošlo…“, účet se nevytvořil (`users` bez něj) |
| g | prošlo | `PORTFYL_TRIAL_DAYS=0`: žádný banner, na Ceníku nic o trialu |
| h | prošlo | start bez `PORTFYL_TURNSTILE_SECRET`: `RuntimeError … is required in the cloud edition` |
| i | prošlo | lokální edice: žádný banner, Tarify beze změny („Lokální edice: všechny funkce jsou zahrnuté“) |

Oprava postupu: u (c) nestačí měnit jen `ends_at`, protože `ck_trial_period_order`
chce `ends_at > started_at`. Je třeba posunout i `started_at`
(`SET started_at = now() - interval '11 days', ends_at = now() - interval '1 day'`).

## Nálezy mimo trial

Žádný nebrání trialu. Pořadí je podle dopadu.

**Stav k 2026-11-25:** všech šest bodů je vyřešených nebo se nepotvrdilo (viz níže
u každého). Bod 6 je ověřený v prohlížeči (2026-11-25: odhlášení i přímý odkaz na `/settings?...` skončí na `/login` bez dotazu). U bodu 5 chybí už jen průchod „smazat účet a znovu se zaregistrovat“ v prohlížeči, kryje ho test.

1. **[Opraveno, commit `5f57a44`: potvrzení posílá `previewed_replace`.] První import do nového portfolia selže 409.** Když je aktivní portfolio s
   ukázkovými daty, aplikace otevře nové prázdné portfolio a náhled spočítá s
   `replace=false`, ale potvrzení pošle původní `replace=true`
   (`frontend/src/pages/Import.jsx:147-174`). Backend přepočítá `preview_id` s
   `replace=true` (`backend/routers/portfolio.py:1094-1105`) a vrátí 409
   „Portfolio se změnilo“. Druhý pokus projde. Oprava: potvrzení má posílat
   stejné `replace`, s jakým se počítal náhled. Po neúspěchu navíc widget
   Složení portfolia na Dashboardu zůstal u starých ukázkových dat (stará cache).
2. **[Opraveno, commit `e342bf1`: endpoint vyžaduje capability `allocation`, test `test_free_allocation_access.py`.] Stránka Alokace na tarifu Free ukáže chybu.** Alokace je Free
   (`backend/plans.py:72`), ale stránka volá `/analytics/sector-breakdown`
   (`frontend/src/pages/Allocation.jsx:76`), který vyžaduje `portfolio_analytics`
   (Investor, `backend/routers/analytics.py:1510`). Free účet dostane „Tato data se
   nepodařilo načíst“ a toast „Potřebujete vyšší tarif“. Ten toast vyskočil i v
   Nastavení. Nesouvisí s trialem, týká se každého Free účtu.
3. **[Opraveno: dialog je v portálu se `z-[60]`, `DataPrivacySettings.jsx`.] Dialog smazání pracovního prostoru:** zatmavení nepokrývá horní pruh stránky.
4. **[Opraveno, commit `6195ae6`: panel analytiky čte jazyk aplikace; „My portfolio“ se nepotvrdilo, UI posílá přeložený název.] Překlady:** v Nastavení zůstal anglický text („…workspace, and security — always
   stays on.“) a výchozí portfolio se jmenuje „My portfolio“.
5. **[Opraveno, commit `9314af1`: smazání účtu maže zapamatovaného brokera, test v `AuthProvider.test.jsx`.] Onboarding po nové registraci** stejné schránky přeskočil výběr brokera a rovnou
   ukázal IBKR. Příčina: `portfyl_intended_broker` a `portfyl_onboarding_connect` v `localStorage` přežily smazání účtu.
6. **[Opraveno, commit `9314af1` a dřívější `b8a14b6`: neznámá adresa přejde na `/login`, kvůli `?verified=1` zůstává jen tento parametr, test v `App.routing.test.jsx`.] URL po odhlášení** zůstane na původní stránce (login se ukáže na místě) a po
   smazání účtu a nové registraci vrátí na `/settings?section=data`. Kosmetické.

## Další otevřené věci

- **Lighthouse a11y opravy** (větev `fix/landing-lighthouse-a11y`: kontrast cookie
  banneru, pořadí nadpisů ve footeru, popisky CZ/EN) jsou sloučené do `main`
  (merge `b6a386f`). Mobilní CLS 0,11 způsobuje
  `aside.welcome-language-suggestion` (vkládá se po hydrataci nad `main#obsah`).
- **Task 6, Step 4** v `2026-11-15-portfyl-landing-redesign-free-trial.md` (prohlížeč
  ve třech jazycích a numerický Performance Lighthouse) a **Step 6** (nasazení) zůstávají
  otevřené. Nasazení jen po souhlasu majitele.
- Lokální vývojová databáze `portfyl_dev` byla při průchodu migrována na
  `0028_password_changed_seen` (byla na `0026`, backend se kvůli tomu nespustil).
- Před nasazením: nastavit `PORTFYL_TURNSTILE_SECRET` (a `VITE_TURNSTILE_SITE_KEY` při buildu)
  nebo `PORTFYL_TURNSTILE_DISABLED=1`, vytvořit secret `portfyl-trial-fingerprint-key`
  před zvýšením `PORTFYL_TRIAL_DAYS` nad 0 (produkce jede s `0`) a nechat advokáta zkontrolovat
  koncepty (`docs/legal/poznamky-pro-pravnika.md`, bod 10).

## Related

- Architecture: [[Free trial]] · [[Billing and Stripe]] · [[Testing]]
- Code: [[trials]] · [[lib.trial]] · [[entitlements]] · [[0027_free_trial]] · [[trial_grants (table)]] · [[trial_identities (table)]] · [[trial_ip_marks (table)]] · [[trial_broker_marks (table)]]
- Docs: [[superpowers/plans/2026-11-15-portfyl-landing-redesign-free-trial]]
