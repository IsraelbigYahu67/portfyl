# Broker integrace před public launchem: research

> **Stav (2026-10-17):** Fáze 1 implementována podle plánu
> `docs/superpowers/plans/2026-10-16-portfyl-broker-integrations.md` (IBKR Flex
> sync + XML, Degiro, XTB, Schwab, Fidelity, eToro Public API). Otevřené: Task 0
> (reálné vzorky exportů, eToro app key a mapování hotovosti/dividend).

Datum: 2026-10-16. Stav kódu, ze kterého jsem vycházel: Trading 212 má vlastní API
sync (`backend/t212_sync.py`, `backend/routers/broker.py`) a import T212 CSV. IBKR
Flex Web Service je napojený (`backend/routers/ibkr.py`), ale parsuje jen opční
obchody (`_parse_options_trades`) a zůstatek NAV/Cash.

Hodnocení spolehlivosti: **[ověřeno]** = oficiální dokumentace brokera nebo
agregátora; **[sekundární]** = fóra, blogy nebo konkurenční trackery. U těch
je potřeba před implementací ještě ověření.

## Rozhodnutí: strategie ve dvou fázích

**Fáze 1 (před public launchem): přímé broker API, kde existuje, jinak CSV/XLSX.**
Bez fixních nákladů, nic nového se nepřipojuje přes agregátor.
- API: IBKR (Flex Web Service, rozšířit stávající), eToro (Public API),
  Trading 212 (už hotové).
- CSV/XLSX: Degiro, XTB, Schwab, Fidelity.
- Robinhood ve fázi 1 **nebude** (nemá API ani použitelné CSV).

**Fáze 2 (později): SnapTrade** pro US brokery (Robinhood, Fidelity, Schwab,
Vanguard, E\*TRADE, Webull…) a jako automatická alternativa k CSV u Degira.
Důvod odkladu je cena: plán Launch Daily stojí $100/měs fixně + $1 za
připojeného uživatele měsíčně. Při malém počtu uživatelů je to dražší než
samotné předplatné (10 uživatelů ≈ $11/uživatel). Návratnost začíná zhruba od
30–40 platících uživatelů, kteří SnapTrade opravdu využijí.

**Spouštěč fáze 2** (stačí kterýkoli z nich):
- aspoň 30–40 platících uživatelů žádá US brokera nebo automatický Degiro sync;
- CSV import u US brokerů generuje výrazný support/churn.

Až se fáze 2 spustí: jen pro placené plány (Investor/Pro); o production access
a broker approval (Fidelity, Schwab) zažádat s předstihem, protože schválení
trvá dny až týdny.

## TL;DR: doporučené pořadí

| # | Broker | Nejefektivnější cesta | Typ | Náročnost | Poznámka |
|---|---|---|---|---|---|
| **Fáze 1** | | | | | |
| 1 | **IBKR (vše)** | **Flex Web Service**, který už máme, rozšířit o Trades (STK/ETF/FUND), CashTransactions, CorporateActions, Transfers a OpenPositions. Plus upload Flex XML pro historii starší než 365 dní | Oficiální API (token + query ID) | **S** | Největší poměr hodnota/práce. Infrastruktura (token, polling, auto-sync, šifrované secrets) už existuje |
| 2 | **eToro** | **eToro Public API**: start na osobních klíčích (`x-api-key` + `x-user-key`, read scope), později OAuth 2.0 (auth code + PKCE) | Oficiální REST API | **M** | Pozice, uzavřené obchody, cash transakce, historie zůstatků. Dividendy explicitně nejsou, budou nejspíš v cash-account transakcích (ověřit) |
| 3 | **Degiro** | **CSV import**: `Transactions.csv` (obchody) + `Account.csv` (dividendy, srážková daň, poplatky, vklady) | CSV | **M** | Oficiální API neexistuje. Klíčové: vícejazyčné hlavičky, ISIN místo tickeru (mapování přes OpenFIGI) |
| 4 | **XTB** | **XLSX import** z xStation → Account History (closed positions + open positions + cash operations) | XLSX/CSV | **M** | API **zrušeno 14. 3. 2025**. Nově je potřeba XLSX parser (`openpyxl`) |
| 5 | **Schwab, Fidelity** | **CSV import**: Schwab Transactions CSV, Fidelity Activity & Orders CSV | CSV | S každý | Ve fázi 2 zůstává jako fallback pro free plán, nebo když SnapTrade spojení selže |
| **Fáze 2** | | | | | |
| 6 | **US brokeři** (Robinhood, Fidelity, Schwab, Vanguard, E\*TRADE, Webull, Public, tastytrade) + volitelně Degiro | **SnapTrade** (agregátor, OAuth/connect portal) | Placený agregátor | **M–L** (jednou pro všechny) | $100/měs + $1 za připojeného uživatele měsíčně (Launch Daily). Jen pro placené plány; spustit až podle spouštěče výše |

**Co bych nedělal:** neoficiální/reverse-engineered API (Degiro `degiroapi`,
Robinhood `robin_stocks`, Trade Republic `pytr`). V SaaS to znamená ukládat
heslo + 2FA uživatele, porušení ToS brokera, riziko zablokování účtu a křehkost.
Pro produkt, který prodává důvěru (KMS, RLS, audit), je to špatný trade-off.
Přímé Schwab Trader API v commercial režimu taky ne: schvalování pro third-party
platformy je podle zpráv z konce 2025 zablokované [sekundární], a SnapTrade to
řeší za nás.

---

## 1. Interactive Brokers: Flex Web Service (rozšířit stávající)

**Proč:** Flex je oficiální, read-only, nepotřebuje gateway ani session
(na rozdíl od Client Portal API / TWS API, které vyžadují běžící gateway a
denní re-login, tedy nevhodné pro server-side SaaS). Token + query ID už máme
zašifrované v `BrokerConnection`.

**Co přidat do parseru** (stejné XML, jen další sekce; uživatel je zaškrtne v
Activity Flex Query):

| Flex sekce | Účel v Portfylu |
|---|---|
| `Trades` (assetCategory `STK`, `ETF`/`FUND`, `OPT` už je) | buy/sell, `tradePrice`, `quantity`, `ibCommission`, `fxRateToBase`, `isin`, `conid`, `tradeID` pro dedup |
| `CashTransactions` | dividendy, `Withholding Tax`, úroky, poplatky, vklady/výběry |
| `CorporateActions` | splity, spin-offy, merger (navázat na existující corporate-action logiku) |
| `Transfers` | ACATS/FOP přesuny pozic (jinak nesedí cost basis) |
| `OpenPositions` | rekonciliace: kontrola, že dopočtené pozice = broker |
| `ConversionRates` | FX k CZK přímo od brokera (fallback na `fx.bulk_fetch_fx`) |

**Omezení a řešení:**
- Flex Query má max. období **365 dní** [sekundární, ale konzistentní napříč
  zdroji]. Pro plnou historii nabídnout **upload Flex XML souborů** (uživatel
  si vygeneruje roky zvlášť) se stejným parserem, plus duplicate-aware preview,
  které už import má.
- Flex requesty jsou rate-limited. Auto-sync 1× denně stačí, protože data jsou
  stejně EOD.
- Onboarding UX: krok-za-krokem návod, které sekce zaškrtnout. IBKR nově umí
  konfigurovat Flex Query přes AI z přirozeného jazyka, takže stačí dát
  uživateli prompt ke zkopírování.
- **Lynx** (CZ/EU introducing broker nad IBKR) používá stejné Flex Queries,
  takže Lynx klienti dostanou integraci zdarma [sekundární, ověřit na Lynx účtu].

## 2. eToro: oficiální Public API

**Stav [ověřeno, api-portal.etoro.com]:**
- Auth: buď pár klíčů (`x-api-key` app key + `x-user-key` user key, který si
  uživatel vygeneruje v *Settings → Trading → API Key Management*, permission
  **Read**, environment Real), nebo **OAuth 2.0 authorization code + PKCE (S256)**
  s confidential clientem. Access token cca 1 h, refresh token long-lived. OAuth
  aplikaci jde registrovat přes Builders portál nebo `POST /api/v1/sso/applications`.
  Dokumentace přímo zmiňuje „portfolio dashboard" jako use case.
- Endpointy: portfolio snapshot/breakdown, PnL, pozice,
  `GET /api/v1/trading/info/trade/history` (uzavřené obchody, `minDate`,
  stránkování, **okno < 1 rok na request**, iterovat po letech),
  cash-account transactions, historie zůstatků.
- Rate limit: default **60 req / 60 s**, sdílený mezi endpointy; 429 vrací `Retry-After`.
- Scope např. `etoro-public:real:read`.
- Existuje i eToro MCP server (`mcp.public-api.etoro.com`). Hodí se pro AI
  asistenta, ale pro serverový sync je správně REST.

**Doporučení:** MVP = uživatel vloží svůj read-only user key (stejný UX vzor
jako T212 API key). Před public launchem zažádat o OAuth app (lepší UX,
revokovatelné, nemusíme držet dlouhodobý klíč).

**Rizika k ověření:**
- eToro má mix reálných akcií a **CFD**, plus copy-trading (mirror pozice).
  Nutné mapování `isBuy`/`leverage` a vyfiltrovat/označit CFD (leverage > 1 nebo short).
- Dividendy nejsou v trade history. Ověřit, jestli chodí v cash-account transactions.
- Instrumenty jsou `instrumentId` → potřeba lookup na ticker/ISIN přes jejich instruments endpoint.
- Explicitní ToS pro third-party agregaci jsem v docs nenašel, takže se zeptat eToro partner týmu.

## 3. Degiro: CSV

**Stav:** Žádné oficiální API. Neoficiální knihovny (`degiroapi`) vyžadují
heslo + 2FA a jejich údržba je nejistá, takže **ne**. SnapTrade Degiro podporuje
(read-only, „available immediately") [ověřeno, SnapTrade Broker Access Guide],
takže je to volitelná placená cesta.

**CSV import (hlavní cesta):**
- `Transactions.csv` (Inbox → Transactions, zvolit rozsah, export CSV): obchody.
  Neobsahuje dividendy, srážkovou daň ani TOB [sekundární].
- `Account.csv` (Account statement): dividendy, srážková daň, poplatky
  (vč. connectivity fee), vklady, FX konverze.
- **Úskalí:** hlavičky se mění podle jazyka UI (NL/DE/EN/CZ…), takže detekce
  podle pozice/sady sloupců, ne podle názvu. Instrumenty jsou ISIN + burza →
  mapování na Yahoo ticker (OpenFIGI, limit 30 req/min bez klíče, s klíčem
  víc; cachovat). FX konverze jsou v Account.csv rozložené do více řádků
  (AutoFX) a je potřeba je párovat k obchodu.

## 4. XTB: XLSX

**Stav [ověřeno, XTB help center]:** „We no longer offer API access." xAPI
(`xapi.xtb.com`, `ws.xtb.com`) vypnuto **14. 3. 2025**. Wrappery archivované.
XTB nepodporuje ani MT4/MT5.

**Import:** xStation 5 (web) → Account History → export **Excel**
(closed positions, open positions, cash operations, v některých buildech i
CSV/HTML) [ověřeno + sekundární]. Je potřeba:
- XLSX parser (přidat `openpyxl` do `requirements.txt`, což je shared hotspot,
  takže sekvencovat).
- Tickery ve formátu `AAPL.US`, `CEZ.CZ`, `VWCE.DE` → mapovat suffix na Yahoo
  (`.CZ`→`.PR`, `.DE`→`.DE`, `.UK`→`.L` …).
- XTB má akcie/ETF i CFD. CFD vyfiltrovat (nebo importovat jen sekci akcií/ETF).
- Cash operations obsahují dividendy a srážkovou daň jako samostatné řádky.

**Alternativa:** Flanks (EU B2B agregátor, napájí getquin) tvrdí pokrytí XTB,
Degiro, IBKR, Trade Republic [sekundární, marketing]. Pokud by se ukázalo, že
XTB umí přes Flanks automaticky, stojí za to zjistit jejich ceník. Jinak CSV.

## 5. US brokeři: SnapTrade (fáze 2)

> Ve fázi 1 se US brokeři řeší CSV importem (sekce 6). SnapTrade přijde až
> podle spouštěče v sekci „Rozhodnutí".

**Proč agregátor:** Robinhood nemá veřejné API pro akcie (jen Crypto Trading
API). Fidelity sdílí data jen přes **Fidelity Access / Akoya** (OAuth, pro
schválené agregátory). Schwab Trader API je pro third-party commercial
prakticky nedostupné. Napojit každého zvlášť nedává smysl, jeden agregátor to
pokryje.

**SnapTrade [ověřeno, docs.snaptrade.com Broker Access Guide]:**

| Broker | Režim | Dostupnost |
|---|---|---|
| Robinhood | Read only | ihned po production approval |
| Vanguard US | Read only | ihned |
| Interactive Brokers | Read only | ihned |
| E\*TRADE, Webull US, Public, tastytrade, Moomoo | Read + trade | ihned |
| **Fidelity** | Read | broker approval (cca 2 dny až 2 týdny) |
| **Charles Schwab** | Read | broker approval (cca 1 týden) |
| Chase, Wells Fargo, Empower | Read | broker approval |
| EU bonus: **Degiro, eToro, Trading 212**, BUX, AJ Bell | Read (T212 i trade) | ihned |
| XTB, Saxo, Revolut, Scalable, Trade Republic | **nejsou** | – |

- **Cena [ověřeno, snaptrade.com/pricing, 2026-10-16]:**
  - *Build* $0: max 5 brokerage připojení, real-time. Jen pro vývoj a test.
  - *Launch Daily* **$100/měs platform fee + $1 / connected user / měs**: data
    1× denně, jen čtení, manuální sync $0.05 za kus.
  - *Launch Real-time* **$100/měs + $2 / connected user / měs**: real-time,
    manuální sync zdarma, trading.
  - *Custom*: objemové slevy, dohodou.
  - Connected user = uživatel s aspoň 1 úspěšně připojeným brokerem (nebo se
    sync aktivitou v daném období). Víc brokerů na jednoho uživatele = 1 user.
    Za konkrétní brokery se neplatí příplatek. Účtuje se měsíčně v USD.
    Produkční klíče vyžadují KYC a platební metodu.
  - *Personal/OAuth* uživatelé (investor si SnapTrade připojí sám) jsou zatím
    zdarma, ale jen dočasně. SaaS s vlastními uživateli spadá pod Commercial model.
  - Pro Portfyl stačí **Launch Daily**, protože data jsou stejně EOD. Při odpojení
    brokera nebo downgradu je nutné smazat SnapTrade usera, jinak se dál účtuje.
- **Data:** holdings, balances, activities (transakce vč. dividend), orders.
  Read-only nám stačí, trading nechceme.
- **Byznys fit:** při Investor EUR 4.99 / Pro EUR 7.99 je $1–2 únosné, ale
  **SnapTrade gatovat jen na placené plány** (přes `edition.py` capability +
  entitlement). Free plán dostane CSV.
- **Compliance:** SnapTrade je processor osobních/finančních dat → DPA,
  update privacy policy, záznam v audit logu, a v cloudu nutně per-workspace
  `user_secret` šifrovaný přes KMS (stejně jako T212 klíče).

**Plaid Investments** jako alternativa: dražší (kontrakty, medián cca $9k/rok
[sekundární]), billing za Item měsíčně bez pro-rata, US-centric, EU brokery
nepokrývá. Pro nás ne.

**Přímé API mimo agregátor (jen pokud by SnapTrade nevyšel):**
- E\*TRADE: OAuth 1.0a API existuje, nevyžaduje broker approval pro
  individual keys; pro distribuci třetím stranám nutné commercial approval [neověřeno].
- tastytrade, Webull (OpenAPI s OAuth 2.0 pro third-party [ověřeno, developer.webull.com]),
  Public: oficiální API existují. Ale SnapTrade je má taky.
- Schwab Trader API: refresh token expiruje po 7 dnech [sekundární], takže
  unattended sync bez re-loginu nefunguje. Pro SaaS nevhodné.

## 6. US CSV fallbacky

- **Schwab:** Accounts → History → Transactions → filtr „All Transactions" →
  Export CSV. Limit **1500 řádků/export** (přes limit vrátí prázdný soubor,
  takže exportovat po kvartálech). Soubor má banner řádek a „Total" řádek
  [sekundární].
- **Fidelity:** Activity & Orders → download CSV; positions CSV
  [sekundární, ověřit formát na reálném účtu].
- **Robinhood:** oficiální CSV historie transakcí v podstatě neexistuje
  (dřív přes support, dnes jen měsíční PDF statementy / tax dokumenty)
  [sekundární, starší zdroje]. **Pro Robinhood je SnapTrade jediná rozumná cesta.**

---

## Navrhovaná architektura

1. **Společná vrstva `broker_import/`**: každý zdroj (Flex XML, eToro API,
   Degiro CSV, XTB XLSX, SnapTrade activities) produkuje stejný normalizovaný
   `ImportRow` (date, isin/ticker, type, qty, price, fee, currency, fx_to_czk,
   external_id). Pak už jede stávající duplicate-aware preview → commit → 24h undo.
2. **Mapování instrumentů** (ISIN/conid/instrumentId/XTB suffix → Yahoo ticker)
   jako sdílený cachovaný resolver. Degiro, XTB i eToro ho potřebují.
3. **API zdroje** (IBKR, eToro, SnapTrade) přes existující vzor `BrokerConnection`
   + KMS secrets + Cloud Scheduler job + dead-letter + `release_connection` před
   outbound calls (sync `def`, `run_on_private_loop`).
4. **Capabilities:** nové `broker_*` capability v `backend/edition.py`; SnapTrade
   jen pro entitlement Investor/Pro.

## Návrh vln (paralelní sessions, disjunktní soubory)

### Fáze 1: přímé API + CSV (před public launchem)

- **Vlna 1 (paralelně):** (a) IBKR Flex rozšíření (`routers/ibkr.py` + nový parser
  modul + testy); (b) Degiro CSV parser (nový modul + fixtures); (c) eToro API
  klient (nový modul, zatím bez migrace).
- **Vlna 2 (sekvenčně, shared hotspots):** migrace pro nový `broker` typ eToro +
  `EXPECTED_ALEMBIC_HEAD`; `openpyxl` do `requirements.txt` a XTB parser.
- **Vlna 3:** Schwab + Fidelity CSV parsery, onboarding UI (návody k exportu)
  pro všechny brokery fáze 1.

### Fáze 2: SnapTrade (později, podle spouštěče v sekci „Rozhodnutí")

- Production access u SnapTrade (KYC) a broker approval pro Fidelity/Schwab.
  Zažádat s předstihem před plánovaným spuštěním.
- Migrace pro šifrovaný per-workspace SnapTrade `userSecret`, nová capability
  gatovaná na Investor/Pro, connection portal v UI, mazání SnapTrade usera při
  odpojení nebo downgradu.
- Mapování SnapTrade activities do společného `ImportRow`.
- DPA se SnapTrade + update privacy policy.

## Otevřené otázky před implementací

1. eToro: kde jsou dividendy (cash-account transactions?) a jestli partner tým
   povolí OAuth app pro portfolio tracker.
2. SnapTrade (až pro fázi 2): DPA, a zda activities u Degiro/eToro mají
   dostatečnou historii (jinak tam nechat přímé cesty).
3. XTB: aktuální struktura XLSX z reálného účtu (sloupce se mezi buildy měnily).
4. Lynx: potvrdit, že Flex Web Service token jde vygenerovat i z Lynx portálu.

## Zdroje

- XTB, ukončení API: https://www.xtb.com/int/help-center/our-platforms-1/do-you-offer-api-1
- XTB, historie a export: https://www.xtb.com/en/help-center/our-platforms/history-of-positions-and-cash-operations-web-platform-and-mobile-app
- xapi-python archivováno: https://github.com/pawelkn/xapi-python
- eToro API, autentizace: https://api-portal.etoro.com/core/getting-started/authentication
- eToro API, OAuth: https://api-portal.etoro.com/core/getting-started/sso-oauth.md
- eToro API, trade history: https://api-portal.etoro.com/api-reference/trading--real/list-trading-history.md
- eToro API, index: https://api-portal.etoro.com/llms.txt
- eToro MCP: https://mcp.public-api.etoro.com/skill
- SnapTrade Broker Access Guide: https://docs.snaptrade.com/docs/broker-access-guide
- SnapTrade Brokerage API / pricing: https://snaptrade.com/brokerage-api
- SnapTrade Fidelity: https://snaptrade.com/brokerage-integrations/fidelity-api
- Plaid billing: https://plaid.com/docs/account/billing
- Degiro export (Portfolio Dividend Tracker): https://help-en.portfoliodividendtracker.com/article/139-import-your-degiro-account
- Degiro CSV (PP forum): https://forum.portfolio-performance.info/t/degiro-import-transactions/38539
- IBKR Flex (PP forum): https://forum.portfolio-performance.info/t/how-to-import-from-interactive-brokers/2229/9
- IBKR Flex sekce (ibflex): https://pypi.org/project/ibflex/0.13
- IBKR Flex s AI: https://interactivebrokers.ie/en/trading/configure-flex-queries-ai.php
- Lynx Flex: https://help-en.portfoliodividendtracker.com/article/269-download-your-lynx-actions
- Schwab Trader API commercial: https://blog.traderspost.io/article/will-traderspost-reconnect-with-charles-schwab
- Schwab CSV export: https://traderfyles.helpscoutdocs.com/article/14-how-to-export-trade-history-from-schwab
- Webull OpenAPI: https://developer.webull.com/apis/docs/connect-api
- Robinhood CSV: https://www.tradervue.com/site/2022/09/16/robinhood-csv
- Flanks / getquin: https://by.linkedin.com/in/unsav
