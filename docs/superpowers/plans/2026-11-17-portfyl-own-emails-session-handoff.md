# Portfyl's own e-mails: handoff for the next session (2026-11-17)

Kontext pro novou session. Stav k 2026-11-17, `origin/main` = `44cb810`. Nic z toho
není tajné; žádné klíče ani adresy uživatelů tu nejsou (jen testovací účet
`tom.zoubek+1@…`, viz níže).

## 1. Co je hotové a v `main`

| Část | Obsah | Kde |
|---|---|---|
| Wave 1 | ověřovací e-mail a reset hesla přes Brevo, 9 jazyků, Firebase jako fallback | `backend/emails/`, `backend/routers/auth_email.py`, `frontend/src/auth/authEmail.js` |
| Review fixes A–C | zdravotní sonda mailera, odkazy s kódem ve **fragmentu** (`#`), jednotná odpověď resetu | plán `2026-11-16-portfyl-own-emails-review-fixes.md` |
| Wave 2 | `password_changed`, `account_deletion_scheduled`, `account_deleted`, detekce změny hesla (`users.password_changed_seen_at`, migrace `0028_password_changed_seen`), sdílený mailer (`emails.notify.set_default_mailer` v `main.py`) | plán `2026-11-16-portfyl-own-emails-wave2.md` |
| Ukončení session hned po resetu | nový `POST /api/auth/email/password-reset-done`; stránka `/auth/action` ho volá po úspěšném resetu; backend ověří změnu u Firebase, nevěří prohlížeči | commit `8598496`…`d305680` |
| Dokumentace cache tržních dat | dva starší commity sloučené z větví `ccr-1cb3d215-c3ic2x` a `docs/market-data-cache-design` (design z `main` ponechán, přibyl jen plán z 9. 11.) | `docs/superpowers/plans/2026-11-09-portfyl-market-data-cache.md` |

Testy na sloučeném stavu před posledním merge: backend rychlá sada 2247 (po
posledním úkolu 2301 hlášeno na větvi), PostgreSQL sada 492, frontend 1553. Python 3.14
se nespouštěl. Docker v cloudovém kontejneru není, PostgreSQL sada běžela na
dočasném clusteru z `/usr/lib/postgresql/16/bin` (port 55441).

## 2. Co je v produkci a co ne

- Projekt `portfyl-prod-f6shqb`, region `europe-west1`, služba `portfyl`, gcloud
  konfigurace `newgcp` (nastavovat přes `$env:CLOUDSDK_ACTIVE_CONFIG_NAME`).
- **Běží revize `portfyl-00029-txk`**, image `portfyl:59f401a` (wave 1 + review fixes + wave 2 +
  sdílený mailer). Migrace `0028` v produkci proběhla (job `portfyl-migrate-p257j`).
- **Neběží**: endpoint `password-reset-done` (commity po `59f401a`). Je jen v `main`.
- Revize 28 (`57d17bd`) je záloha pro rychlé vrácení.
- Na službě ověřeny: `RATE_LIMIT_AUTH_EMAIL_LIMIT=10`, `_WINDOW_SECONDS=600`,
  `_TARGET_LIMIT=3`, `_TARGET_WINDOW_SECONDS=900`, `PORTFYL_EMAIL_APP_URL=https://app.portfyl.com`.
- Platby jsou vypnuté (`PORTFYL_BILLING_ENABLED` se nezapínalo).
- Nasazení: čistý `git archive` lokální větve `main` (musí být po `git pull`), build přes
  `gcloud builds submit` s `--build-arg VITE_*` z `frontend/.env.local`, pak
  `deploy/run-migrations.ps1`, pak `gcloud run deploy portfyl --image $IMAGE`.
  Celý postup je v `deploy/cloudrun.md` sekce „Routine redeploy“ (řádek ~531).

## 3. Ověřeno ručně v produkci (reálná schránka, testovací účet)

Ověřovací e-mail dorazil do 1 s do hlavní složky, česky, od `Portfyl <noreply@mail.portfyl.com>`.
SPF, DKIM (`mail.portfyl.com`) a DMARC = PASS. Odkaz prošel a stránka ukázala „Váš e-mail je ověřený“.
Reset hesla: e-mail, formulář „Zvolte nové heslo“, „Heslo změněno“. Po přihlášení novým heslem
přišlo `password_changed` a druhá session (anonymní okno) byla odhlášena. `account_deletion_scheduled`
přišlo s datem +30 dní. Odpověď z Gmailu na `support@portfyl.com` byla Cloudflare přijata.

## 4. Otevřené věci (v pořadí, jak je dává smysl dělat)

1. **Oprava přetékajících tlačítek** na `/auth/action` (stránky „e-mail ověřen“ a „heslo změněno“).
   Příčina: `ContinueButton` v `frontend/src/pages/AuthAction.jsx` používá `<a>`/`<Link>`
   s `btn-primary w-full`; `.btn-primary` v `index.css` nemá `display`, inline prvek ignoruje `w-full`
   i `space-y-4`. Oprava: přidat `block`. Zkontrolovat i další `btn-primary` na odkazech. Před úpravou
   přečíst `DESIGN.md`, ověřit v Playwrightu (cs i en). Uživatel chtěl nasadit s dalším deployem.
2. **Nasazení** (viz 2): po bodu 1. Potom zopakovat krok 2 wave 2 checklistu v novém chování
   (prohlížeč A odhlášen už po resetu, ještě před přihlášením v B).
3. **Lhůta u mazání účtu**: uživatel chce 24 hodin nebo okamžité smazání. Doporučení bylo 24 hodin:
   `DELETION_GRACE_DAYS = 30` v `backend/account_deletion.py`, plus texty v dialogu
   (`frontend/src/components/DataPrivacySettings.jsx`, 9 jazyků), testy, runbook, spec. Purge běží
   denně, takže skutečné smazání je do ~2 dnů. Okamžité smazání je větší zásah (nová cesta mimo job,
   ztráta pojistky). Zásady ochrany osobních údajů musí uvádět zálohy Neon (viz
   `docs/operations/neon-backup-restore.md`). **Čeká na uživatelovo „ano“ a hodnotu.**
4. **Brevo přepisuje odkazy** (sledovací doména `sendibt2.com`). Samoobslužný přepínač kliků
   u transakčních e-mailů není; vypnutí jen přes podporu (možná Enterprise). Uživatel byl
   navigován na Transactional → Tracking („Anonymous email tracking“ → Yes) a Retention rules
   (1 měsíc, „Never store previews“); **uložení jsme nepotvrdili**. Podporu zatím nikdo nekontaktoval.
5. **Zbývající položky checklistu**: reset pro neexistující adresu (stejná hláška, žádný e-mail);
   Outlook, Seznam a Gmail v telefonu (fragment `#` přes Brevo jen v Chrome na PC); odkaz po
   61 minutách (věta „Odkaz platí 1 hodinu“ ve všech jazycích, ověřit); odpověď na `support@portfyl.com`
   z jiné schránky než cílové (Gmail deduplikuje); hlavička `List-Unsubscribe` nezkontrolována.
6. **`account_deleted`** nebyl odeslán. Testovací účet `tom.zoubek+1@gmail.com` je naplánovaný ke smazání
   na 17. 12. 2026. Buď počkat, nebo zkrátit lhůtu přes administrativní job (zásah do produkčních dat,
   jen s výslovným souhlasem a jen na tomto účtu).
7. **Oprava runbooku** (neudělána): „Not checked until then: whether Brevo rewrites links“ a bod 2
   checklistu (Brevo odkazy přepisuje); `support@portfyl.com` je přeposílání přes Cloudflare Email
   Routing na `tom.zoubek@gmail.com` + deduplikace při testu ze stejné adresy; **`PORTFYL_APP_URL` pro
   Stripe** v runbooku (řádek ~1021 a návratové URL portálu) má být `https://app.portfyl.com`, ne apex
   `https://portfyl.com` (apex nepřidává edge token a `/api` tam selhává, cookie je jen pro `app.`).
8. **Firebase fallback** (`authEmail.js`) odstranit nejdřív kolem 30. 11., podle logů
   (`auth_email … outcome=sent|failed`, 503 `email_unavailable`) a až po záložním plánu pro Brevo
   (Free tarif má limit 300 e-mailů denně, sdílený s Firebase). Připomínka nenastavena.
9. **Rozhodnutí z posledního úkolu**: per-IP limit u `password-reset-done` vrací `429` (ponecháno);
   uživatelé s `password_changed_seen_at = NULL` (neviděni od `0028`) se berou jako „první setkání“
   (nic se neukončí). Agent navrhl možné rozšíření, nikdo nerozhodl.
10. **Beta pozvánka `+1`**: zapsána v `beta_invites` (30 dní), ale Cloudflare Access politika
    „Portfyl private beta testers“ se skriptem neaktualizovala (chybí `CLOUDFLARE_ACCOUNT_ID` a
    `CLOUDFLARE_API_TOKEN`). Ověřit shodu seznamů: `manage-beta-tester.ps1 -Action list -CheckCloudflare`.
11. **Před veřejnou registrací**: placený tarif Brevo, zapnutí plateb.

## 5. Pracovní poznámky

- Uživatel je na Windows (PowerShell, `C:\Users\…\claude\ptf\portfyl`), `grep` tam není; příkazy chce
  **po jednom** a posílá výstup. Příkazy mu dávat s `Select-String`, ne s `grep`.
- V cloudovém kontejneru **není přihlášený `gcloud`**, Docker nefunguje, DNS/DoH jde zablokovat.
  Produkci tedy mění jen uživatel. Do Cloudflare ani Brevo se přihlásit nedá; Brevo MCP konektor
  hlásí `invalid_scope` a stejně by nejspíš neuměl nastavení sledování.
- Do konverzace nevkládat odkazy z e-mailů ani kódy (reset odkaz nese použitelný jednorázový kód).
- Souběžné agenty pouštět do worktrees; commity bez pushe, merge a push až po schválení. Moje dev
  větev je `claude/youthful-hopper-civpjc`; ostatní pracovní větve (`feat/own-emails-w2-*`,
  `feat/revoke-sessions-on-reset`) jsou už v `main`.
- Nastavení uživatele: odpovídat česky nebo anglicky; **začínat každou zprávu jeho jménem**. Jméno
  se v této session nikdy nezjistilo (z cesty a adresy lze jen odhadovat) — příště se na něj zeptat.
- Uživatel je zvyklý schvalovat po částech; rozhodnutí o produktu (lhůta mazání, Brevo tarif) jsou na něm.
