# Dokončení rozdělané práce (stav k 2026-10-13)

V hlavním checkoutu `C:\Users\tomzo\claude\portfyl` leží na `main` tři
necommitnuté, navzájem nezávislé kusy práce. Tento plán je dotáhne do `main`
a pak je nasadí jedním společným deployem.

| Úkol | Oblast | Soubory | Do produkce |
|---|---|---|---|
| 1 | Úklid demo dat po připojení brokera | `backend/demo_cleanup.py`, `backend/routers/broker.py`, `backend/tests/test_broker.py` | ano |
| 2 | Úpravy dashboardu | `frontend/src/components/dashboard/InsiderBuysCard.jsx`, `frontend/src/components/ui/ZoomDialog.jsx`, `frontend/src/pages/Dashboard.jsx`, `frontend/src/components/DashboardGrid.jsx`, `frontend/src/components/PerformanceChart.jsx`, `frontend/src/components/layout/AppShell.jsx`, `frontend/src/components/layout/DesktopSidebar.jsx`, testy `Dashboard.async.test.jsx`, `DesktopSidebar.test.jsx` | ano |
| 3 | Přehled statistik kódu | `docs/operations/code_stats.py`, `test_code_stats.py`, `code-stats.template.html`, `code-stats.html`, `otevrit-prehled.bat` | ne (interní nástroj) |

## Pořadí a souběh session

Rozdělaná práce existuje jen jako necommitnuté změny v hlavním checkoutu.
Nový git worktree ji nevidí, a dvě session ve stejném checkoutu by si
přepínaly větve pod rukama. Proto:

- **Vlna 1:** úkol 1, pak úkol 2, pak úkol 3, **postupně** v hlavním
  checkoutu. Každý pracuje na vlastní větvi a commituje jen své soubory.
  Ostatní necommitnuté soubory nechává ve working tree a nestashuje je.
  Sady souborů jsou disjunktní. Jedinou výjimkou je `.gitignore` /
  `.dockerignore`, které smí měnit jen úkol 3.
- **Paralelní varianta:** nejdřív commitnout každou část do vlastní větve
  `wip/…` z `main`. Potom může každá session běžet ve svém worktree. Dev
  servery, testovací PostgreSQL kontejner a porty pak musí mít každá session
  vlastní (viz CLAUDE.md, "Parallel session safety").
- **Vlna 2 (deploy):** až budou úkoly 1 a 2 v `main` a pushnuté. Viz níže.

Žádný úkol nepřidává Alembic migraci. `EXPECTED_ALEMBIC_HEAD` se nemění.

---

## Úkol 1: Úklid demo dat po připojení brokera

```text
Dokonči rozdělanou backendovou změnu v hlavním checkoutu C:\Users\tomzo\claude\portfyl (necommitnuté, na main). Řiď se CLAUDE.md.

KONTEXT
Když si uživatel připojí skutečný účet Trading 212 (POST connect v backend/routers/broker.py), mají se smazat ukázková data z onboardingu, protože vedle reálných dat matou. Rozdělané soubory:
- backend/demo_cleanup.py (nový): purge_demo_data(db, portfolio). Maže transakce se source="demo", maže "čisté" separátní demo portfolio, výchozí název "Portfyl demo" přejmenuje na "Trading 212" (vlastní název nechá), portfolio s demo názvem, které drží i reálná data, nesmaže. Vrací dict s počty.
- backend/routers/broker.py: volá purge_demo_data ve stejné transakci po db.flush() nového připojení. Když se něco smazalo, zapíše audit událost "onboarding.demo.removed".
- backend/tests/test_broker.py: nová třída TestDemoCleanupOnConnect, 4 testy.
V working tree jsou i jiné necommitnuté změny (frontend dashboard, docs/operations/code_stats*). NESAHEJ na ně, necommituj je a nestashuj je.

ÚKOL
1. Založ větev feat/demo-cleanup-on-connect z main (git checkout -b; ostatní necommitnuté soubory zůstanou ve working tree, to je v pořádku).
2. Pečlivě zkontroluj demo_cleanup.py. Mění produkční data, takže:
   - Nikdy nesmaže nic jiného než demo data. Najdi, kde onboarding demo data vytváří (hledej source="demo" a "Portfyl demo"), a ověř, že se značky shodují.
   - Je striktně omezený na workspace daného portfolia (aplikační predikát; RLS je jen druhá vrstva, viz CLAUDE.md).
   - Když connect po purge selže, všechno se rollbackne.
   - Smazání demo portfolia, které bylo is_default, správně přesune výchozí portfolio.
   - Projdi i reconnect a další cesty, které volají connect.
3. Frontend: když bylo aktivní portfolio právě to smazané demo, localStorage sb_portfolio_id ukazuje na neexistující UUID. Ověř, co se stane (interceptor v frontend/src/api.js, PortfolioSwitcher), a zařiď, aby se po connect přenačetla portfolia a přepnulo se na platné. Pokud to vyžaduje frontend změnu, drž ji malou a jen v souborech, které nemění dashboard práce (Dashboard.jsx, DashboardGrid.jsx, PerformanceChart.jsx, AppShell.jsx, DesktopSidebar.jsx).
4. Doplň testy: tenant izolace (demo data jiného workspace zůstanou), rollback při chybě, audit událost. Pokud je to v souladu s docs/security/tenant-isolation-matrix.md, přidej případ i do tests/postgres/.
5. Ověř, že connect zůstává synchronní `def` (pravidlo event loopu v CLAUDE.md).
6. Spusť z backend/: python -m pytest tests/ -v --ignore=tests/postgres. Pak PostgreSQL suite: docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait a python -m pytest tests/postgres/ -v. Kontejner pak zastav.
7. Commitni jen soubory této změny. Na konci zprávy: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
8. Mergni do main (--no-ff) a znovu pusť rychlou suite.
NEPUSHUJ a NEDEPLOYUJ. Až budeš hotový, napiš shrnutí: co jsi změnil, co jsi našel při review, výsledky testů. Zeptej se mě na push.
```

---

## Úkol 2: Úpravy dashboardu

```text
Dokonči rozdělanou frontendovou změnu dashboardu v hlavním checkoutu C:\Users\tomzo\claude\portfyl (necommitnuté, na main). Řiď se CLAUDE.md.

KONTEXT
Rozdělané soubory:
- frontend/src/components/dashboard/InsiderBuysCard.jsx (nový) a frontend/src/components/ui/ZoomDialog.jsx (nový, zvětšené zobrazení karty).
- frontend/src/pages/Dashboard.jsx: insider nákupy už nejsou samostatný sbalitelný widget "insiderBuys" s tabulkou. Jsou to karta v řádku "concentration" vedle heatmapy, místo Top 10 Holdings. Jen pro Pro capability "advanced_research". Ostatní vidí dál Top 10 Holdings. Dotaz fetchInsiderBuys má enabled: hasResearch. Dokud se capabilities načítají, ukazuje se skeleton insider karty.
- frontend/src/components/DashboardGrid.jsx: widget "insiderBuys" odebrán z ALL_WIDGETS a DEFAULT_LAYOUTS, "concentration" přejmenován na "Insider buys & heatmap". Komentář tvrdí, že normalizeWidgetOrder zahodí uložené id "insiderBuys".
- frontend/src/components/PerformanceChart.jsx: tooltip "Period % (TWR)" / "Total % (TWR)" a poznámka "% = time-weighted return, excludes deposits/withdrawals".
- frontend/src/components/layout/AppShell.jsx + DesktopSidebar.jsx: sidebar je sticky (h-dvh), odebrán podtitul "Institutional Grade" a text "Live data via Yahoo Finance".
- Testy: frontend/src/pages/Dashboard.async.test.jsx, frontend/src/components/layout/DesktopSidebar.test.jsx.
V working tree jsou i jiné necommitnuté změny (backend demo_cleanup/broker, docs/operations/code_stats*). NESAHEJ na ně, necommituj je a nestashuj je.

ÚKOL
1. Založ větev feat/dashboard-insider-card z main.
2. Ověř a případně oprav:
   - normalizeWidgetOrder opravdu zahodí uložené "insiderBuys" z localStorage (sb_dashboard_layout_v3 a order klíč), bez pádu a bez díry v layoutu. Přidej na to test.
   - Capability "advanced_research" existuje v backendu (backend/edition.py, entitlements) a /api/capabilities ji vrací pro Pro. Ověř chování ve local i cloud edici.
   - Popisek TWR je pravdivý: dohledej v backendu, jak se počítá pnl_pct / total_pnl_pct pro výkonový graf. Pokud to není time-weighted return, popisek oprav podle skutečnosti, ne naopak.
   - Odebrání "Live data via Yahoo Finance": zkontroluj, jestli atribuci datového zdroje nevyžaduje něco v docs/ (Workstream A, market-data rights). Pokud ano, vrať ji jinam, třeba do patičky nebo Settings, a řekni mi to.
   - Sticky sidebar na nízkém okně: nav se musí scrollovat a AccountMenu zůstat vidět.
   - Přístupnost ZoomDialog: focus trap, Esc, aria, návrat fokusu.
   - V Dashboard.jsx nezůstaly nepoužité importy a proměnné (TickerLink, SkeletonRows...).
3. Z frontend/ spusť: npm test, npm run test:cloud, npm run build, npm run build:cloud.
4. Vizuálně ověř podle sekce "Verifying UI changes" v CLAUDE.md: dashboard s Pro i bez Pro, zoom dialog, sidebar, tooltip grafu. Pokud dev servery nebo DB nejsou k dispozici, napiš to místo hádání.
5. Commitni jen soubory této změny. Na konci zprávy: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
6. Mergni do main (--no-ff) a znovu pusť npm test.
NEPUSHUJ a NEDEPLOYUJ. Na konci napiš shrnutí: co jsi změnil, co jsi našel, výsledky testů a buildů. Zeptej se mě na push.
```

---

## Úkol 3: Přehled statistik kódu

```text
Dokonči a ukliď pomocný nástroj na statistiky kódu v hlavním checkoutu C:\Users\tomzo\claude\portfyl (necommitnuté soubory na main, vytvořené 2026-09-23). Řiď se CLAUDE.md.

KONTEXT
Necommitnuté soubory v docs/operations/:
- code_stats.py: generátor statistik kódu
- test_code_stats.py: jeho testy
- code-stats.template.html: HTML šablona
- code-stats.html: vygenerovaný výstup
- otevrit-prehled.bat: otevře přehled
Je to interní nástroj pro vlastníka. S aplikací nesouvisí a do Docker image ani produkce nepatří.
V working tree jsou i jiné necommitnuté změny (backend demo_cleanup/broker, frontend dashboard). NESAHEJ na ně, necommituj je a nestashuj je.

ÚKOL
1. Přečti všechny soubory a popiš mi, co nástroj dělá a jak se spouští.
2. Spusť test_code_stats.py (pytest) a code_stats.py. Ověř, že generování funguje na aktuálním stavu repa a že .bat funguje z libovolného pracovního adresáře.
3. Ověř, že nic nečte ani nevypisuje .env, secrets, DATABASE_URL apod. a že ignoruje node_modules, .venv, dist, __pycache__.
4. Rozhodni a zdůvodni, jestli code-stats.html commitovat. Je to generovaný výstup, takže spíš přidat do .gitignore a generovat lokálně. Pokud .gitignore měníš, je to sdílený soubor, tak jen jeden řádek.
5. Ověř, že .dockerignore tyto soubory do image nezahrne, případně je doplň.
6. Založ větev chore/code-stats-tool z main, commitni jen tyto soubory (+ případně .gitignore/.dockerignore). Na konci zprávy: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
7. Mergni do main (--no-ff).
NEPUSHUJ. Na konci napiš shrnutí a zeptej se mě na push.
```

---

## Vlna 2: Deploy

Spustit, až budou úkoly 1 a 2 v `main` a `main` bude pushnutý. Postup je
routine redeploy z `deploy/cloudrun.md`:

- projekt `portfyl-prod-f6shqb`, region `europe-west1`
- gcloud konfigurace `newgcp`, předávaná jako `--configuration newgcp`
- build z čistého `git archive main`
- migrační Job na stejném image: head se nemění, Job se přesto spustí
- `gcloud.cmd run deploy`
- kontrola startup logů nové revize a přihlášení na `app.portfyl.com`

Povolená `gcloud.cmd` pravidla a jejich úskalí popisuje paměť
`prod-gcloud-access`. Návrat zpět: `gcloud.cmd run services update-traffic`
na předchozí revizi. Před deployem se vždy potvrzuje v chatu.
