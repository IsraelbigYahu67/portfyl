---
slug: sledovani-portfolia-trading-212
target_query: "sledování portfolia trading 212" # GUESS, replace after the keyword research
title: "Sledování portfolia a dividend z Trading 212 | Portfyl"
meta_description: "Portfyl načte obchody a dividendy z Trading 212 přes API nebo CSV a spočítá výkonnost, rozložení a dividendy. Co umí a kde jsou limity."
h1: "Sledování portfolia a dividend z Trading 212"
language: cs
status: draft-needs-owner-review
---

# Sledování portfolia a dividend z Trading 212

Portfyl načte obchody, dividendy a hotovost z vašeho účtu Trading 212 a spočítá z nich výkonnost, rozložení a dividendy celého portfolia. Bez tabulek v Excelu. Data se dají dostat dovnitř dvěma způsoby: napojením přes API, nebo nahráním exportu ve formátu CSV. Na této stránce je popsáno, jak oba způsoby fungují a kde mají limity.

## Co z Trading 212 v Portfylu uvidíte

- **Pozice.** U každé pozice její váhu a hodnotu. Hned poznáte, jestli vám jedna akcie nebo jeden sektor netvoří příliš velkou část portfolia.
- **Výkonnost.** Vývoj hodnoty portfolia a jeho růst v procentech za zvolené období. Svůj výsledek můžete porovnat s indexy S&P 500, NASDAQ 100 nebo STOXX 50. Podrobnosti jsou v článku [Výkonnost portfolia a srovnání s indexem](/vykonnost-portfolia-vs-benchmark).
- **Rozložení.** Portfolio podle pozic, sektorů a měn. Více v článku [Rozložení portfolia podle sektorů a měn](/rozlozeni-portfolia).
- **Dividendy.** Kolik přišlo, od koho a v kterém měsíci. Podrobnosti najdete v článku [Sledování dividend po měsících](/sledovani-dividend).
- **Hotovost.** Pokud ji Portfyl z vašich dat zná, ukáže se jako samostatná položka v rozložení portfolia.

Hodnoty přepočítáme do měny, kterou si zvolíte, a účty u různých brokerů můžete mít vedle sebe jako samostatná portfolia.

## Dva způsoby, jak data nahrát

### 1. Napojení přes API (jen čtení)

Portfyl se k Trading 212 připojí klíčem API, který si vytvoříte přímo u brokera:

1. V aplikaci Trading 212 otevřete menu (tři vodorovné čárky) a zvolte **Settings**.
2. Vyberte **API (Beta)**.
3. Vygenerujte klíč a zaškrtněte všechna oprávnění kromě **Orders - Execute** a **Pies - Write**.
4. Zkopírujte **API key ID** a **Secret key** a vložte je do Portfylu.

Portfyl s klíčem data jen čte. Obchodovat ani převádět peníze neumí, a proto zápisová oprávnění nezaškrtáváte. Klíč ukládáme šifrovaně.

Po připojení Portfyl klíč nejdřív ověří a načte aktuální pozice a hodnotu účtu, takže přehled uvidíte rychle. Celá historie (obchody, dividendy, vklady a výběry) se dotahuje na pozadí po částech, a proto trvá o něco déle. Jeden klíč patří vždy k jednomu portfoliu, stejný klíč nelze připojit ke dvěma portfoliím. Jakmile připojíte skutečný účet, zmizí ukázková data z úvodního nastavení.

Synchronizaci spustíte ručně. V nastavení také zapnete automatickou, která běží denně v zadaný čas, nebo po zvoleném počtu hodin. Nejkratší možný interval závisí na typu účtu.

Napojení přes API není součástí každého typu účtu, podrobnosti najdete v části Ceník na [úvodní stránce](/). Import souboru CSV je dostupný vždy.

### 2. Import CSV exportu z Trading 212

1. V Trading 212 otevřete **History** a zvolte **Export history**.
2. Vyberte celé období a všechny typy dat.
3. Stažený soubor CSV nahrajte v Portfylu.

Před uložením Portfyl ukáže náhled: kolik řádků se přidá, kolik se odebere a kolik jich už v portfoliu je. Teprve potom import potvrdíte. Do 24 hodin ho můžete vrátit zpět, pokud se portfolio mezitím nezměnilo. Soubor může mít nejvýše 5 MB.

Export z Trading 212 obsahuje celou historii účtu, a proto **nahrazuje obsah portfolia**, nepřidává se k němu. Náhled vám ukáže, co by se odebralo. Poznámky, které jste si k obchodům napsali, se při nahrazení odstraní. Pokud soubor obsahuje akci, kterou Portfyl neumí přečíst, import se zamítne se seznamem problémových řádků a stávající data zůstanou beze změny. Portfyl si také zapamatuje, do kdy export sahá, aby na něj mohla navázat synchronizace přes API.

Pro transakce z jiných míst můžete použít vlastní CSV se sloupci `date`, `ticker`, `type`, `shares` a `price`, volitelně i `currency`. Typy řádků jsou `buy`, `sell` a `dividend`.

## Omezení, o kterých je fér vědět

- **Jen čtení.** Portfyl data od brokera pouze zobrazuje. Nákupy a prodeje děláte dál u Trading 212.
- **Historie z API se může zastavit.** Pokud obsahuje typy korporátních akcí, které Portfyl neumí zpracovat automaticky, historie se neimportuje a synchronizace skončí ve stavu „k posouzení“. Aktuální pozice a hotovost zůstanou. Dnes Portfyl zpracuje rozdělení akcií (split) a odštěpení (spin-off), jiné korporátní akce ne.
- **CSV nahrazuje portfolio.** Nahrávejte proto soubor s kompletní historií a před potvrzením si zkontrolujte náhled.
- **Tržní data jsou z veřejně dostupných zdrojů.** Ceny a údaje o firmách mohou být zpožděné, nebo u méně obchodovaných titulů úplně chybět.
- **Další brokeři.** U jiných brokerů zatím použijete vlastní CSV.

## Časté otázky

**Umí Portfyl za mě obchodovat?** Ne. Portfyl data od brokera pouze čte a zobrazuje.

**Co se stane po odpojení Trading 212?** Portfyl smaže uložený klíč a poslední snímek pozic a hotovosti. Transakce, které už v portfoliu jsou, zůstávají. Účet i data můžete kdykoli smazat.

**Dá se import vrátit?** Import souboru ano, do 24 hodin, pokud se portfolio mezitím nezměnilo.

## Není investiční poradenství

Portfyl ukazuje vaše vlastní data a veřejné údaje o firmách. Není to investiční poradenství a rozhodnutí zůstávají na vás.

## Vyzkoušejte, jak portfolio v Portfylu vypadá

Na [úvodní stránce](/#funkce) si u každé funkce můžete vyzkoušet ukázku na vymyšlených datech, bez registrace.

<!-- OWNER: CTA wording depends on whether public sign-up is open (O6 in the SEO plan). While the beta is closed, keep the examples link only. -->

## Ověření tvrzení

| # | Tvrzení v textu | Důkaz v repu |
|---|---|---|
| 1 | Portfyl načte obchody, dividendy, hotovost a spočítá výkonnost, rozložení, dividendy; bez Excelu | `frontend/src/pages/welcomeCopy.js` (cs.lead, řádek 32) |
| 2 | Dva způsoby: API a CSV; Trading 212 má obojí | `frontend/src/lib/onboardingBrokers.js` (SUPPORTED_BROKERS, `trading212`: `api: true`, `fileKind: "CSV"`); `welcomeCopy.js` cs.brokers (řádek 37) |
| 3 | Váha a hodnota každé pozice | `backend/routers/portfolio.py:1430` `get_holdings` (`weight` na řádku 1489, `market_value`); `welcomeCopy.js` cs.features[0] |
| 4 | Vývoj hodnoty a růst v % za zvolené období | `backend/routers/portfolio.py:2420` `get_performance`; `frontend/src/pages/Dashboard.jsx:46` (PERIODS), režimy Value / Growth % |
| 5 | Porovnání s S&P 500, NASDAQ 100, STOXX 50 | `frontend/src/pages/Dashboard.jsx:49-54` (BENCHMARKS); `backend/routers/portfolio.py:2763` BENCHMARK_TICKERS |
| 6 | Rozložení podle pozic, sektorů, měn | `frontend/src/pages/Allocation.jsx:86-91`; `welcomeCopy.js` cs.features[0] |
| 7 | Hotovost jako samostatná položka v rozložení, pokud ji Portfyl zná | `backend/routers/analytics.py:1341` `_allocation_totals` (Cash bucket z `broker_cash.current_t212_cash` nebo z hotovostní knihy) |
| 8 | Dividendy: kolik, od koho, kdy | `backend/routers/portfolio.py:2127` `get_dividend_forecast` (`entries` s tickerem a názvem po měsících) |
| 9 | Hodnoty se přepočítají do zvolené měny | `frontend/src/lib/displayCurrency.js:5` DISPLAY_CURRENCIES; `welcomeCopy.js` cs.features[4] |
| 10 | Více brokerů jako samostatná portfolia vedle sebe | `welcomeCopy.js` cs.features[4]; `backend/routers/portfolios.py` (portfolia ve workspace) |
| 11 | Postup vytvoření klíče: Settings, API (Beta), všechna oprávnění kromě Orders - Execute a Pies - Write, API key ID + Secret key | `frontend/src/components/settings/T212ApiGuide.jsx` (kroky a T212_PERMISSIONS) |
| 12 | Portfyl s klíčem jen čte (obchodovat ani převádět peníze neumí) | Všechna volání na Trading 212 jsou `httpx.get`: `backend/t212_sync.py:148,531,533`, `backend/routers/broker.py:457,811`; `welcomeCopy.js` cs.dataFacts[0] |
| 13 | Klíč se ukládá šifrovaně | `backend/models.py:689` `BrokerConnection` (`api_key_ciphertext`, `api_secret_ciphertext`); `welcomeCopy.js` cs.dataFacts[1] |
| 14 | Po připojení se klíč ověří a načtou se pozice a hodnota účtu (snímek); historie se dotahuje na pozadí po částech | `backend/routers/broker.py:412` `connect` (volání `/equity/account/info` a summary); `broker.py:686` `sync_transactions` (snapshot first, historie v `BrokerSyncRun`, `backfill_trigger.request_backfill`); `backend/t212_sync.py:180` `fetch_snapshot`, `:321` STREAMS = orders, dividends, cash |
| 15 | Jeden klíč = jedno portfolio, stejný klíč nelze připojit ke dvěma portfoliím | `backend/routers/broker.py:451` (409 "already connected to a different portfolio") |
| 16 | Připojením skutečného účtu zmizí ukázková data | `backend/routers/broker.py:589` `purge_demo_data`; `backend/demo_cleanup.py:41` |
| 17 | Ruční synchronizace a automatická synchronizace denně v zadaný čas nebo po zvoleném počtu hodin | `backend/routers/broker.py:621` `set_auto_sync`; `backend/routers/settings.py:24-60` `SyncSchedule` (`mode` daily/interval, `interval_hours`) |
| 18 | Nejkratší interval závisí na typu účtu | `backend/plans.py:26` `autosync_min_hours`; `backend/jobs.py:1176` |
| 19 | API napojení není součástí každého typu účtu; CSV import je dostupný vždy | `backend/plans.py:69-90` MINIMUM_PLAN (`broker_sync` vyžaduje vyšší plán, `csv_import` je pro všechny); `plans.py:45` Free má 0 napojení brokera |
| 20 | Postup exportu CSV: History, Export history, celé období, všechny typy dat | `frontend/src/components/import/BrokerGuides.jsx:21-27` |
| 21 | Náhled před uložením (přidá, odebere, už existuje); potvrzení až potom | `backend/import_workflow.py:218` `build_preview` (`counts.added/removed/duplicates_existing`); `backend/routers/portfolio.py:942` `preview_import_csv`, `:1081` commit |
| 22 | Vrácení zpět do 24 hodin, jen když se portfolio nezměnilo | `backend/import_undo.py:26` UNDO_WINDOW = 24 h; `backend/routers/portfolio.py:1226` `undo_import_csv` (409 při změně, 410 po vypršení) |
| 23 | Soubor nejvýše 5 MB | `backend/routers/portfolio.py:62` MAX_IMPORT_BYTES = 5 MiB |
| 24 | Export Trading 212 nahrazuje obsah portfolia | `backend/routers/portfolio.py:495-496` `mandatory_replace = True`; `frontend/src/pages/Import.jsx:366` |
| 25 | Poznámky k obchodům se při nahrazení odstraní | `backend/routers/portfolio.py:965-968` (`notes_removed` v replace režimu) |
| 26 | Neznámá akce v souboru = import zamítnut se seznamem řádků, data beze změny | `backend/routers/portfolio.py:481-491` (HTTP 400 "Trading 212 import is not lossless; existing data was preserved"), `:132` `_normalize_t212_detailed` |
| 27 | Portfyl si zapamatuje, do kdy export sahá, aby navázal sync přes API | `backend/routers/portfolio.py:493-496` `t212_covered_through`; `:1049` `_clear_t212_history_coverage`; hub Broker importers and sync (odstavec "Append, except Trading 212 CSV") |
| 28 | Vlastní CSV: sloupce date, ticker, type, shares, price (+ currency), typy buy/sell/dividend | `backend/routers/portfolio.py:499` (required), `:404` `_NATIVE_IMPORT_TYPES`, `:440-443` currency |
| 29 | Historie z API se zastaví ve stavu "k posouzení" u nepodporovaných korporátních akcí; pozice a hotovost zůstanou; split a spin-off podporované | `backend/t212_sync.py:327` SUPPORTED_CORPORATE_ACTION_TYPES, `:356` HISTORY_NEEDS_REVIEW_ERROR, `:753` `history_run_decision`; `broker.py:686-776` (snímek se ukládá nezávisle na historii) |
| 30 | Po odpojení se smaže klíč a snímek pozic a hotovosti; transakce zůstávají | `backend/routers/broker.py:643-675` `disconnect` (maže `BrokerConnection`, `BrokerBalance`, `BrokerPosition`, nesahá na `Transaction`) |
| 31 | Účet i data lze kdykoli smazat | `welcomeCopy.js` cs.dataFacts[2]; `backend/account_deletion.py` `delete_workspace_now` (CLAUDE.md, Account deletion is immediate) |
| 32 | Portfyl neobchoduje, jen čte a zobrazuje | `welcomeCopy.js` cs.questions[1] |
| 33 | Tržní data z veřejně dostupných zdrojů, mohou být zpožděná nebo chybět | hub Market data (yfinance, bounded timeouts, "possibly delisted"); `backend/market_data.py` |
| 34 | U jiných brokerů vlastní CSV | `welcomeCopy.js` cs.questions[2] |
| 35 | Nejde o investiční poradenství; ukázky na vymyšlených datech bez registrace | `welcomeCopy.js` cs.questions[0], cs.questions[3], cs.status |

## Neověřeno

Nic z tohoto není v textu jako tvrzení. Co je zde, buď v textu vůbec není, nebo je podložené jen repem, ne živým Trading 212.

- **Názvy menu a oprávnění u Trading 212** (Settings, API (Beta), History, Export history, názvy oprávnění) jsou převzaté z návodů v repu (`T212ApiGuide.jsx`, `BrokerGuides.jsx`). Dnes se neověřily proti živé aplikaci Trading 212, a ta je může změnit.
- **Limity exportu u Trading 212** (maximální délka období na jeden export, více souborů) se z kódu ověřit nedají. Protože CSV z Trading 212 vždy nahrazuje portfolio, nesmí se text tvářit, že se dá nahrát jeden rok po druhém. Plán S8 má před publikací ověřit skutečný export (Task 0 plánu broker integrací zůstává otevřený).
- **API synchronizace byla ověřená jen na účtu vlastníka** (záznam o odchytu 2026-10-03 v `docs/research/t212-cash-transaction-encoding.md`: 250 transakcí, vše v CZK). Účty vedené v jiné měně a jiné typy účtů ověřené nejsou. Komentář v záhlaví `backend/t212_sync.py` o "published API docs and fixtures" je zastaralý.
- **Že částka dividendy z Trading 212 je čistá po srážkové dani**: kód používá skutečně připsanou částku (`amount` z API, sloupec Total z CSV), ale není ověřený na řádku s konkrétní srážkou. Tato stránka čistotu částek netvrdí; v článku o dividendách je podložená jen tím, co říká úvodní stránka.
- **Přesné intervaly automatické synchronizace** podle typu účtu v textu nejsou (zákaz zmiňovat plány a ceny). Hodnoty jsou v `plans.py`.
- **Snímky obrazovky** z ukázkového portfolia plán S7 chce, ale žádné jsem nevytvářel ani nevymýšlel.

### Rozhodnutí pro vlastníka

1. **Zmínka o typech účtu.** Text jen odkazuje na Ceník, protože Free nemá API napojení (`plans.py:45`). Chcete výslovněji říct, že API je placená funkce? Pravidla zadání plány a ceny zakazují, ale bez toho může mít návštěvník pocit, že ho text o funkci nechává v nejistotě.
2. **CTA.** Registrace jsou zatím jen na pozvánku (cs.status "Uzavřená beta"), `/demo` je od 2026-11-15 zrušené (`frontend/src/lib/routes.js`), takže SEO plán s odkazem na `/demo` je zastaralý. Text proto odkazuje na `/#funkce`. Rozhodnout (O6), kdy přepnout na registrační CTA.
3. **Slug a adresa.** Stránka musí přijít do `frontend/src/seo/publicPages.js` jako jediný zdroj; to tento draft nedělá.
4. **Autor a podpis (O5)**: YMYL text zatím nemá uvedeného autora.

## Related

- [[Frontend structure]]
- [[Broker importers and sync]]
- [[Onboarding and CSV import]]
- [[2026-11-09-portfyl-seo]]
