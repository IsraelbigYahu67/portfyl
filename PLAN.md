# Shibui integrace — rozšíření Portfylu

Plán navazuje na `backend/shibui_client.py` (MCP klient) a `GET /api/market/shibui/financials/{ticker}`,
které už existují a fungují. Zdroj dat: [Shibui Finance](https://shibui.finance) MCP server
(`https://mcp.shibui.finance/mcp`) — DuckDB warehouse, zdarma, bez klíče, NYSE/NASDAQ only.

## Obecné poznámky platné pro celý plán

- **200-row limit per query.** Server tvrdě odmítne cokoliv nad 200 řádků. Víceletá denní
  časová řada (valuace, ceny) se musí agregovat (měsíčně/kvartálně přes `arg_max`/`DATE_TRUNC`),
  ne stahovat po dnech — viz Fáze 5.
- **Validace tickeru.** Každý nový endpoint musí ticker validovat stejným regexem jako
  `_SHIBUI_TICKER_RE` v `routers/market.py` (SQL se stringuje přes f-string, ne parametrizovaně —
  Shibui `stock_data_query` bere jen hotový SQL string).
- **`ticker` vs. `symbol`.** V `WHERE` vždy holý ticker (`ticker = 'AAPL'`), v `JOIN`
  vždy `symbol` (`'AAPL.NASDAQ'`). Insider tabulky mají svoje vlastní `issuer_ticker`/`issuer_symbol`.
- **Cache.** Každý nový endpoint zabalit do `@ttl_cache(...)` stejně jako zbytek `market.py`
  (SEC/insider data se mění nejvýš denně → TTL klidně 1–6 h).
- **Chyby.** `shibui_client.ShibuiError` → `HTTPException(502, ...)`, prázdný výsledek → `404`.
- **⚠ Latence — ověřit před vším ostatním.** `shibui_client.query()` dnes při každém volání
  otevírá novou session a volá `get_database_schema` + `get_query_patterns` + `stock_data_query`
  (3 roundtripy). To je v pořádku pro řídce volané endpointy s TTL cache, ale bylo by pomalé
  pro cokoliv na hot path (např. search-as-you-type). **První krok před Fází 1:** zkusit v čerstvé
  session zavolat `stock_data_query` bez těch dvou úvodních volání a ověřit, jestli výsledek
  zůstane správný. Pokud ano, `shibui_client.py` se zjednoduší a lehce zrychlí (méně roundtripů);
  pokud ne (server výsledky bez nich skutečně degraduje), necháváme jak je.
- **Registrace routes.** Vše pod `/market/shibui/...` v `routers/market.py` — `/market` je už
  v `frontend/src/api.js` (`PORTFOLIO_AGNOSTIC_PREFIXES`) vyjmuté z portfolio-scopingu, není potřeba
  nic měnit na frontendu kvůli routingu.

---

## Fáze 1 — SEC filings & insider aktivita (nejvyšší priorita, dnes chybí úplně)

### 1a. Filings feed pro tiker

`GET /market/shibui/filings/{ticker}?form_types=10-K,10-Q,8-K,DEF 14A&years=2`

```sql
WITH recent AS (
  SELECT sf.filing_date, sf.acceptance_datetime, sf.form_type, sf.raw_form_type,
         sf.is_amendment, sf.report_date, sf.filing_url, sf.items,
         ROW_NUMBER() OVER (PARTITION BY sf.form_type ORDER BY sf.filing_date DESC) AS rn
  FROM shibui.sec_filings sf
  WHERE sf.cik = (SELECT g.cik FROM shibui.general_info g WHERE g.ticker = '{sym}')
    AND sf.filing_date >= CURRENT_DATE - INTERVAL '{years} years'
    AND sf.form_type IN ({form_types})
)
SELECT filing_date, acceptance_datetime, raw_form_type, is_amendment, report_date, items, filing_url
FROM recent WHERE rn <= 20
ORDER BY form_type, filing_date DESC
LIMIT 200
```

- `form_types` whitelist v Pythonu (ne volný string z query param) — jen platné hodnoty ze
  seznamu v `get_database_schema` (10-K, 10-Q, 20-F, 6-K, 8-K, 4, 3, 5, SC 13G, SC 13D, DEF 14A,
  424B2, FWP, S-1, S-3, …).
- **UI:** nová sekce "Filings" na Stock stránce — tabulka `datum · typ · [View na EDGAR]`.
  8-K řádky navíc ukázat `items` (barevný chip pro `2.02`=výsledky, `5.02`=změna vedení atd.).

### 1b. Insider transakce — nahrazuje současnou yfinance verzi

Dnešní `_build_insider_transactions`/`_classify_insider_side` v `routers/market.py` (řádky
~563–630) hádá buy/sell regexem z volného textu, co Yahoo naškrábe. Shibui má strukturované
kódy přímo z Form 4/5.

`GET /market/shibui/insiders/{ticker}?months=12`

```sql
SELECT t.tx_date, t.owner_canonical_name, t.officer_title, t.tx_code,
  CASE WHEN t.acquired_or_disposed = 'A' THEN 'buy' ELSE 'sell' END AS direction,
  t.shares, t.price_per_share, ROUND(t.shares * t.price_per_share, 0) AS value,
  t.shares_after_tx, t.is_10b5_1, t.is_tax_withholding, t.is_gift, t.is_estate,
  t.is_auto_plan, t.is_avg_price, t.security_title,
  t.is_director, t.is_officer, t.is_ten_pct_owner
FROM shibui.insider_transactions t
WHERE NOT t.is_superseded
  AND t.issuer_ticker = '{sym}'
  AND t.tx_date >= CURRENT_DATE - INTERVAL '{months} months'
ORDER BY t.tx_date DESC
LIMIT 100
```

- **Rozhodnutí k udělání:** plně nahradit stávající tabulku, nebo nechat obě vedle sebe
  (`?source=shibui` volitelně)? Doporučuju **rovnou nahradit** — Shibui verze je striktně bohatší
  (tx kódy, 10b5-1, šum-flagy) a stávající regex heuristika nemá jinou výhodu.
- **UI:** stávající insider tabulka na Stock stránce + nové sloupce: `10b5-1` badge,
  šum-flagy jako drobné ikony/tooltip (tax withholding / gift / estate / auto-plan / avg-price).

### 1c. Cluster buy detekce (jeden tiker, ne tržní scan)

Protože jde o jeden tiker (ne market-wide sken jako v Shibui vzoru I1), stačí stáhnout
posledních 6–12 měsíců `P` transakcí a shlukování po 30denních oknech udělat v Pythonu —
jednodušší a čitelnější než SQL self-join na malém datasetu:

```sql
SELECT t.owner_cik, t.owner_canonical_name, t.tx_date, t.shares, t.price_per_share,
  ROUND(t.shares * t.price_per_share, 0) AS value
FROM shibui.insider_transactions t
WHERE NOT t.is_superseded AND NOT t.is_derivative
  AND t.security_title ILIKE '%common%'
  AND t.tx_code = 'P' AND NOT t.is_auto_plan AND NOT t.is_estate
  AND t.price_per_share IS NOT NULL
  AND t.issuer_ticker = '{sym}'
  AND t.tx_date >= CURRENT_DATE - INTERVAL '6 months'
ORDER BY t.tx_date
LIMIT 200
```

Python: seřadit podle data, sliding window 30 dní, flag když `COUNT(DISTINCT owner_cik) >= 3`
v okně → `{"cluster": true, "buyers": [...], "window": [start, end]}`.

### 1d. Aktivistické podíly (SC 13D/G)

`GET /market/shibui/activist-stakes/{ticker}`

```sql
SELECT filer_name, filer_canonical_name, filer_entity_type,
  filer_is_activist, filer_activist_group, schedule_type, filing_date
FROM shibui.beneficial_ownership
WHERE subject_ticker = '{sym}' AND NOT is_superseded
ORDER BY filing_date DESC
LIMIT 50
```

`schedule_type = '13D'` = aktivní/aktivistický záměr, `'13G'` = pasivní podíl >5 %.

### 1e. Firma investuje do firmy (strategic stakes) — ✅ ověřeno živě

Přesně tvůj příklad NVDA→CRWV **funguje** a je ověřený přímým dotazem:

```
NVIDIA CORP → CRWV (CoreWeave), 13G, filed 2026-01-26
NVIDIA CORP → NBIS (Nebius),   13G, filed 2026-07-20
NVIDIA CORP → SERV (Serve Robotics), 13G, filed 2025-02-14
```

`GET /market/shibui/strategic-investors/{ticker}` — filtruje jen filery, kteří jsou sami
veřejně obchodovaný tiker (join `beneficial_ownership.filer_cik = general_info.cik`):

```sql
SELECT bo.filer_name, g2.ticker AS filer_ticker, bo.schedule_type, bo.filing_date
FROM shibui.beneficial_ownership bo
INNER JOIN shibui.general_info g2 ON g2.cik = bo.filer_cik
WHERE bo.subject_ticker = '{sym}' AND NOT bo.is_superseded
ORDER BY bo.filing_date DESC
LIMIT 50
```

**Omezení ověřené na tvém druhém příkladu (GOOGL→FRSH):** podíl Alphabetu ve Freshworks
existuje v datech, ale je podaný pod `CapitalG 2013 LP` (Googlin venture arm), ne pod
Alphabet/GOOGL CIK — takže výše uvedený přímý join ho **nenajde**. Přímí rodiče (jako NVDA→CRWV)
se najdou automaticky; investice přes venture-arm dceřinky ne.

→ **Fáze 2 (později, volitelně):** ručně udržovaný mapping `KNOWN_CORPORATE_VC_ARMS = {"CAPITALG 2013 LP": "GOOGL", "GV": "GOOGL", "M12": "MSFT", "SALESFORCE VENTURES": "CRM", "INTEL CAPITAL": "INTC", "QUALCOMM VENTURES": "QCOM", ...}` — dá se dotahovat průběžně, jak narazíš na další případy. Není blokující pro první verzi.

### 1f. Otevřené otázky, které jsi položil (odpovědi)

- **Transakce politiků (STOCK Act)?** Shibui je nemá — Form 3/4/5 je jiný právní režim (SEC
  insider disclosure) než kongresmanské periodic transaction reports. **Jde to ale přes jiný
  zdroj, viz 1g níže** — ověřeno živě, funguje a je to dokonce jednodušší integrace než Shibui
  (obyčejné REST API, ne MCP).
- **13F filings?** Metadata **ano** — ověřeno, `sec_filings` obsahuje 10 739+ `13F-HR` záznamů
  (plus `13F-NT`, `13F-E`, `13FCONP` varianty) s `filing_date`/`filing_url`, takže "kdo a kdy
  podal 13F" jde zjistit stejným způsobem jako u ostatních filings (1a). **Konkrétní pozice**
  (které tikry a kolik akcií fond drží) ale Shibui **neparsuje** do žádné tabulky — to je jen
  v přiloženém XML na SEC a chtělo by to samostatný parser/zdroj. Mimo scope tohodle plánu,
  dá se řešit jako vlastní projekt později.

### 1g. Politické obchody (Congress trades) — ✅ ověřeno živě, jiný zdroj než Shibui

Otestoval jsem oba dostupné konektory:

- **FMP `senate` tool** — ❌ zablokováno, vyžaduje placený tarif (Starter a výš). Nejde použít
  bez upgradu FMP účtu.
- **Alpha Vantage `CONGRESS_TRADES` / `POLITICIAN_METADATA`** — ✅ funguje, a je to navíc
  **veřejné REST API**, ne jen MCP nástroj svázaný s touhle session — takže integrace do
  Portfylu je jednodušší než u Shibui (žádný MCP klient, jen `httpx` + API klíč).

**Ověřeno na NVDA** (405 obchodů celkem, ukázka):
```
HOUSE, Sam T. Liccardo (D-CA16), SELL, 2026-07-21, $15,001–$50,000, owner=SELF
HOUSE, Dan Newhouse (R-WA04),   SELL, 2026-07-10, $1,001–$15,000,  owner=SPOUSE
```
Pole: `chamber` (HOUSE/SENATE), `politician`, `bioguide_id`, `party`, `state`, `state_district`,
`asset_name`, `transaction_type` (BUY/SELL), `transaction_date`, `notification_date`,
`amount_min`/`amount_max` (STOCK Act zveřejňuje jen **pásmo**, nikdy přesnou částku — UI musí
ukazovat "$15,001–$50,000", ne vymyšlené jedno číslo), `owner_code` (SELF/SPOUSE/CHILD/JOINT),
`filing_status`, `filed_date`. `POLITICIAN_METADATA` dává celý rejstřík (1 144 politiků) s
`bioguide_id`, jmény/alias, komorou, státem, stranou a historií volebních období — užitečné pro
"sleduj tohoto politika" a pro name→bioguide_id resolving.

**REST vzor** (Alpha Vantage má tenhle tvar pro každou funkci bez výjimky):
```
GET https://www.alphavantage.co/query?function=CONGRESS_TRADES&symbol={ticker}&apikey={key}
GET https://www.alphavantage.co/query?function=POLITICIAN_METADATA&apikey={key}
```

**Vazbová podmínka: free tier = 25 requestů/den.** Řešeno tak, že appka je nikdy neutrácí sama
od sebe — viz níže.

#### 1g-i. Načítání jen na tlačítko, ne automaticky

Explicitní požadavek: appka nesmí volat Alpha Vantage sama (žádný background job, žádný
auto-fetch při načtení stránky) — jen když si o to řekneš kliknutím. To zároveň zjednodušuje
dřívější návrh (žádná `jobs.py` pass, žádná `PoliticianTradeCache` tabulka, žádný round-robin —
škrtnuto):

- Nová věc `backend/alphavantage_client.py` — obyčejný `httpx.AsyncClient` wrapper (stejný vzor
  jako `_call_deepseek` v `routers/assistant.py`), **ne** MCP klient jako `shibui_client.py`.
  Nový env var `ALPHA_VANTAGE_API_KEY` (stejný vzor jako `APP_PASSWORD`) — uživatel si zdarma
  založí účet na alphavantage.co. Bez nastaveného klíče endpoint vrací `503` s jasnou hláškou,
  ne pád.
- `GET /market/politician-trades/{ticker}` — backend endpoint zůstává, ale **frontend ho nesmí
  volat automaticky** při otevření Stock stránky (na rozdíl od zbytku appky, kde je zavedený
  yfinance auto-prefetch vzor). Na stránce bude tlačítko (např. "Zobrazit obchody politiků" /
  "Load political trades") — teprve jeho kliknutím se odpálí `useQuery` s `enabled` zapnutým
  přes lokální state (`const [showPolitical, setShowPolitical] = useState(false)`), stejný
  princip jako `enabled: Boolean(ticker)` u `InsiderVolumeChart` (`StockDetail.jsx:1938`), jen
  navíc gated tím tlačítkem.
- Backend `ttl_cache` (24 h) zůstává — jen aby opakované kliknutí na stejný tiker ve stejný den
  nespotřebovalo další request z denní kvóty. Žádné proaktivní obnovování na pozadí.
- Protože je to čistě manuální, 25/den by se v praxi jednoho uživatele nemělo reálně narazit,
  pokud si appka žádá o data jen k tikrům, co si vážně chceš prohlédnout. Kdyby přesto nestačilo
  (hodně kliknutí za den), další krok je placený Alpha Vantage tarif — ne něco, co plán řeší teď.

#### 1g-ii. Tečky na cenovém grafu (zelená nákup, červená prodej)

Stávající cenový graf na Stock stránce je `InsiderVolumeChart` v `StockDetail.jsx:1930` —
`ComposedChart` (recharts) s `Line` pro close cenu (`CATEGORICAL[0]`) a bary pro insider
buy/sell (`GAIN_COLOR`/`LOSS_COLOR`), data z `fetchHistory(ticker, "1y")`. Problém: tenhle graf
agreguje **po měsících** (`aggregateInsiderByMonth`, x-osa = měsíční klíč, ne datum) — přesná
tečka na konkrétní den by se do měsíčního x-axis nevešla čistě.

**Návrh:** nová samostatná komponenta (např. `PoliticalTradesChart`), ne rozšíření
`InsiderVolumeChart`:
- Stejný datový zdroj `fetchHistory(ticker, "1y")`, ale vykreslený jako `LineChart`/`AreaChart`
  s **denní** x-osou (skutečná `date`, ne měsíční bucket) — přímý předek: `hist.data` už má
  `{date, close}` per trading day.
- Politické obchody se napárují na graf přes `recharts` `ReferenceDot` na souřadnici
  `(x=transaction_date, y=close cena k tomu dni)` — cenu vzít z `hist.data` podle přesné shody
  data (STOCK Act transakce jsou obchodní dny, mělo by sedět), s fallbackem na nejbližší
  předchozí obchodní den, kdyby ne.
- Barva přesně jak jsi chtěl: `fill={GAIN_COLOR}` pro `transaction_type === "BUY"`,
  `fill={LOSS_COLOR}` pro `"SELL"` — stejné tokeny, co už `InsiderVolumeChart` používá pro
  insider buy/sell bary, takže to vizuálně ladí s existující stránkou.
- Tvar tečky navíc kóduje typ obchodu (viz 1g-iii): kruh pro akcie, kosočtverec pro
  option-flagged obchody — barva = směr, tvar = typ nástroje.
- Hover/klik na tečku otevře detail popup (viz níže).

#### 1g-iii. "Pelosi style" (deep ITM opce, ~1 rok do expirace) — ověřeno, že to NEJDE spolehlivě automaticky

Otestoval jsem to naživo na Nancy Pelosi (`bioguide_id=P000197`, 134 obchodů) a zjištění je
důležité pro reálná očekávání:

- `asset_type_code` má hodnoty `ST` (akcie), `OP`, `AB`, `OT`, `OL` — **`OP` NENÍ spolehlivě
  "option"**: viděl jsem `OP` i na řádku popsaném jako "Bloom Energy Corporation Class A Common
  Stock (BE) [OP]", tedy obyčejná akcie. Skutečné opční obchody (řádky s "call options" v textu)
  mají `asset_type_code` **buď** `OP`, **nebo** `ST` — kód sám o sobě typ nástroje nerozliší.
- Popis, který by strike a expiraci obsahoval, **je u zdroje uříznutý**: ověřený příklad,
  celý (netruncated) obsah pole `asset_name` u NVDA opčního nákupu:
  `"NVIDIA Corporation (NVDA) [OP] P FIlINg STATuS: New DESCRIPTION: Purchased 50 call options with"`
  — končí přesně tam, kde by měla začít strike cena / datum expirace. **Ani jeden ze 134
  záznamů neobsahoval strike, expiraci, ani odkaz na originální filing** (žádné pole
  `source_url`, `strike`, `expiration` nikde v datech).
- Data navíc mají viditelné OCR-styl chyby (`PYPl`, `AAPl`, `gOOgl`, `FIlINg`, `sTaTus`) —
  vypadá to na sken/OCR PDF disclosure formulářů, takže i to málo textu, co je k dispozici,
  není 100% spolehlivé pro parsování.

**Důsledek pro plán — co jde a co ne:**

- ❌ **Nejde** spočítat "deep ITM, ~1 rok do expirace" programaticky — strike a expirace
  v datech prostě nejsou. Cokoliv, co by tohle tvrdilo, by si to muselo vymyslet.
- ✅ **Jde** spolehlivě poznat "tohle vypadá jako opční sázka" — heuristika
  `asset_type_code == 'OP' AND asset_name ILIKE '%option%'` (kombinace obou podmínek vyřadí
  false-positive typu Bloom Energy výše). Backend endpoint vrátí computed flag
  `is_likely_option: bool` přímo v payloadu, ať to frontend nepočítá znovu.
- **UI pro option-flagged obchod:** jiný tvar tečky (kosočtverec, viz 1g-ii) + v detail popupu
  badge "Options trade" + **surová (useknutá) `asset_name` description tak, jak přišla** — lepší
  ukázat neúplnou informaci s jasným "tohle je vše, co máme" než nic. V popisku k badge
  napsat rovnou: *"Přesný strike/expirace nejsou v datech k dispozici — nejde automaticky
  poznat, jestli jde o 'Pelosi style' deep-ITM sázku."*
- **Pokud bys chtěl skutečné strike/expiraci** (a tím pádem opravdovou "Pelosi style"
  detekci), je to jiný, bohatší (a pravděpodobně placený) zdroj — např. QuiverQuant, Capitol
  Trades, Unusual Whales mají strukturovaná opční data z STOCK Act filings. Mimo scope
  tohodle plánu, dá se prozkoumat zvlášť, kdyby ti na tom fakt záleželo.

**UI shrnutí (1g-ii + 1g-iii dohromady):** samostatná sekce na Stock stránce ("Political
trades"), vizuálně oddělená od SEC insider transakcí (1b) — je to právně jiná kategorie (volení
zástupci, ne firemní insideři). Graf s tečkami (barva = buy/sell, tvar = akcie/option-flagged),
klik na tečku otevře kartu se vším: politik (`politician_canonical`), strana + stát + komora,
typ a datum transakce, datum podání (`filed_date` — u STOCK Act typicky dost pozadu za
`transaction_date`, stojí za zobrazení jako "nahlášeno až po X dnech"), `owner_code`, částkové
pásmo, a u option-flagged navíc badge + surový popis + caveat výše.

---

## Fáze 2 — Earnings analýza — ✅ backend implementován (2a, 2e), frontend zatím ne

### 2a. EPS beat/miss historie — plně podporováno

`GET /market/shibui/earnings/{ticker}`

```sql
SELECT date, report_date, before_after_market, eps_actual, eps_estimate,
  eps_difference, surprise_percent, year, quarter
FROM shibui.earnings_quarterly
WHERE ticker = '{sym}' AND eps_actual IS NOT NULL
ORDER BY date DESC
LIMIT 20
```

### 2b. Revenue beat/miss — částečná podpora, potřeba kombinovat zdroje

Shibui **nemá** revenue konsensus odhad (jen EPS). Portfyl ale yfinance revenue odhad **už
stahuje** — `routers/market.py` řádek ~1192, `stock.revenue_estimate` →
`analyst_estimates_quarterly.revenue`. Návrh: spojit Shibui skutečnou tržbu s existujícím
yfinance odhadem a revenue surprise dopočítat sami v Pythonu:

```sql
SELECT e.date AS earnings_date, e.year, e.quarter, e.eps_actual, e.eps_estimate, e.surprise_percent,
  f.revenue AS revenue_actual
FROM shibui.earnings_quarterly e
LEFT JOIN shibui.fundamentals_quarterly f ON f.symbol = e.symbol AND f.year = e.year AND f.quarter = e.quarter
WHERE e.ticker = '{sym}'
ORDER BY e.date DESC
LIMIT 20
```

### 2c. Guidance změny — nejsou strukturovaná data

Ani Shibui, ani žádný jiný zdroj v tomhle plánu nemá "guidance raised/lowered" jako pole.
Nejbližší signál: 8-K s `items` obsahujícím `'2.02'` (results of operations) často guidance
obsahuje v tiskové zprávě, ale Shibui má jen `filing_url`, ne text filingu.

- **Fáze 1 (levné):** v earnings-recap payloadu (2e) ukázat odkaz na nejbližší 8-K s item 2.02
  kolem data reportu — uživatel si přečte sám.
- **Fáze 2 (stretch, samostatný úkol):** fetch obsahu 8-K exhibitu + LLM sumarizace přes
  Assistant. Nejde o Shibui rozšíření, ale o novou schopnost (fetch + parse SEC dokumentu) —
  mimo scope tohohle plánu.

### 2d. Buyback info — částečná podpora

Realizované odkupy (cash-flow, retrospektivně) **ano**:
`fundamentals_quarterly`/`fundamentals_yearly`.`equity_issuance_repayment` (záporná hodnota =
čistý odkup ten kvartál/rok). Nové **oznámení autorizace** odkupu (forward-looking event)
**není** strukturovaná data — stejná caveat jako guidance (8-K item 8.01, jen odkaz).

### 2e. Kombinovaný "earnings recap" endpoint — ✅ implementováno

`GET /market/shibui/earnings-recap/{ticker}` — spojí 2a (EPS) + 2b (revenue, kombinovaný zdroj)
+ 2c (odkaz na nejbližší 8-K) + 2d (`equity_issuance_repayment` trend) do jednoho payloadu.

**Poznámka k 2b při implementaci:** yfinance `revenue_estimate` v praxi téměř nikdy nemá `-1q`
period (ověřeno živě na AAPL — index byl jen `['0q', '+1q', '0y', '+1y']`), takže "revenue surprise"
je opravdu jen best-effort, jak plán předjímal ("částečná podpora") — `latest_revenue_estimate`/
`latest_revenue_surprise_pct` se často vrátí `null`, ne vymyšlené číslo. `source` v payloadu je
`"shibui+yfinance"` jen když se `-1q` skutečně podařilo najít, jinak `"shibui"`.

**UI (zatím neuděláno):** nová karta/tab "Earnings" na Stock stránce — poslední report nahoře
(beat/miss badge), historie surprise % jako mini-graf, odkaz na filing.

---

## Fáze 3 — Short interest

`GET /market/shibui/ownership/{ticker}`

```sql
SELECT percent_insiders, percent_institutions, short_percent_float, shares_float
FROM shibui.ownership_stats
WHERE ticker = '{sym}'
LIMIT 1
```

**UI:** přidat řádek "Short interest: X % of float" do stávajícího ownership bloku na Stock
stránce (`_build_ownership` v `market.py`) — jednoduché doplnění, ne náhrada (Shibui nemá jmenný
seznam top holderů jako yfinance, takže tabulka top-holderů zůstává z yfinance).

---

## Fáze 4 — Vylepšení existujících funkcí

### 4a. Screener — přidat Shibui jako rychlejší, širší zdroj (ne rovnou nahradit)

Dnešní `/market/screener` skenuje až 500 tikrů přes `ThreadPoolExecutor(12)` živě na yfinance
(`market.py:1439`), cache 1 h. Shibui zvládne **celý univerz** (~10 344 symbolů) jedním SQL
dotazem za sekundy, plus filtry co dnes nejdou vůbec (Piotroski F-score, operating P/E,
earnings-quality flags, forward PEG).

- **Fáze 4a-i (bezpečná, rovnou přidat):** nový volitelný `?source=shibui&universe=all` mód
  vedle stávajícího — screen přes celý trh, ne jen presetové listy (sp500/nasdaq100/...).
  Vzor P4 z query patterns jako základ, rozšířit o `fundamentals_derived_quarterly` (ROE,
  operating_margin) a `fundamentals_quarterly.piotroski_f_score`.
- **Fáze 4a-ii (později, až 4a-i dozraje):** zvážit úplné nahrazení yfinance cesty, pokud
  Shibui pokryje všechna pole, co dnes frontend používá (target_mean, rating, analyst_count —
  šlo by dotáhnout z `analyst_estimates`).

### 4b. Search — Shibui jen jako fallback, ne živě na každý keystroke

**Důležitá korekce oproti dřívějšímu doporučení:** `shibui_client.query()` dnes dělá 3 roundtripy
na server (viz "Latence" výše) — pro search-as-you-type je to moc pomalé oproti Yahoo
autocomplete. Doporučení:
- Použít Shibui `general_info` (`WHERE name ILIKE '%q%' OR ticker ILIKE '%q%' LIMIT 10`) jen
  jako **fallback**, když Yahoo vrátí 0 výsledků (typicky tenčí/nové tikry, kde je yfinance
  nespolehlivé — viz CLAUDE.md poznámka o "yfinance is noisy").
- Případně (větší práce, jen pokud fallback nestačí): jednou denně stáhnout celou `general_info`
  do lokální SQLite tabulky a fulltextově hledat lokálně — žádná latence, ale je to nová
  synchronizační úloha navíc.

### 4c. ✅ Implementováno — jde dál než původní návrh: Shibui jako primární zdroj, ne jen fallback

Původní návrh (Shibui jen když `info` vyjde prázdné) byl nahrazen širším řešením: `get_fundamentals`
teď volá `_shibui_fundamentals(sym)` **vždy** (ne jen při selhání) a pokud Shibui tiker pokrývá
(NYSE/NASDAQ common stock — gate na neprázdný výsledek z `fundamentals_yearly`), jeho data **vyhrávají**
nad yfinance pro:

- **Financials (roční i kvartální)**: revenue, cost_of_revenue, gross_profit, operating_income,
  ebitda, net_income, EPS (diluted s fallbackem na basic), FCF, debt, cash, shares_outstanding —
  z `fundamentals_yearly`/`fundamentals_quarterly`, nahrazuje yfinance statement-row-name-guessing.
- **Ratios**: P/E, P/S, P/B, P/FCF, EV/EBITDA, D/E, ROE, ROA, ROIC, gross/operating/net margin,
  dividend yield, payout ratio, current ratio, quick ratio (dopočítáno z raw balance-sheet polí) —
  z `fundamentals_derived_daily` + `valuation` + `fundamentals_derived_quarterly`. Plus nové pole
  **`piotroski_f_score`** (0-9), co dřív appka vůbec neměla.
- **Ownership %**: `insider_pct`/`institutional_pct` (v `_build_ownership`) teď taky z Shibui
  `ownership_stats`, ne z yfinance `info`.

yfinance zůstává **jediný** zdroj (Shibui to nemá vůbec) pro: analyst buy/hold/sell rozložení
a price targets, revenue consensus estimates, jmenovitý seznam institucionálních holderů,
a živou cenu/market cap (Shibui `valuation` má ~1denní lag, žádné intradenní ceny) — ty zůstávají
beze změny na headline statech stránky. Existující yfinance-statement-based fallbacky (ROIC,
quick ratio, margins) zůstávají jako druhá vrstva pro tikery, co Shibui nepokrývá vůbec (cizí
burzy jako LSE/TSE — appka je multi-market, `_SHIBUI_TICKER_RE` na ně sedí tvarem, ale Shibui
pro ně vrátí prázdný výsledek → čistý fallback na starou yfinance cestu, ověřeno živě na `HSBA.L`).
Payload má nové pole `"fundamentals_source": "shibui" | "yfinance"`.

**Neřešeno v tomhle kroku (vědomě odloženo)**: analyst estimates (EPS/revenue forward křivka,
target price rozsah, rating) zůstávají čistě na yfinance — Shibui má sice `analyst_estimates`
tabulku, ale jen current/next year+quarter EPS + `wall_street_target_price` (jedno číslo, ne
high/low/median), žádné rating counts (strongBuy/buy/hold/sell), žádný revenue estimate. Nahradit
by znamenalo viditelně ochudit stávající forward-estimate graf na Stock stránce — stálo by za
samostatné promyšlení/rozhodnutí, ne tichou náhradu.

---

## Fáze 5 — Historická valuace u více multiplů (podrobný návrh)

Cíl: ukázat ne jen dnešní P/E, ale **jak se násobek vyvíjel v čase vůči sobě samému** — dnes
appka umí jen srovnání proti sektoru "teď", ne proti vlastní historii. To je diferencující
feature, nic takového dnes neexistuje.

### Multiply k zobrazení (5 základních, všechny denně od 1993)

`trailing_pe`, `ev_ebitda`, `price_to_sales`, `price_to_cash_flow` (z `fundamentals_derived_daily`),
`price_to_book` (z `valuation`).

### Granularita — adaptivní žebříček, ne pevný cutoff podle UI presetu

Cíl: co nejjemnější rozlišení, jaké se vejde pod 200-row limit pro daný rozsah — nejdřív denně,
a jen když by to překročilo limit, o stupeň hůř (týdně, pak 2týdně, pak měsíčně, pak kvartálně).
Vychází čistě z počtu (kalendářních) dní v požadovaném rozsahu:

| Rozsah (dny)                          | Bucket          | Max řádků |
|----------------------------------------|-----------------|-----------|
| ≤ ~190 dní (~6 měsíců)                  | denní           | ~190 |
| ≤ ~1300 dní (~3.5 roku)                 | týdenní         | ~186 |
| ≤ ~2600 dní (~7 let)                    | 2týdenní (14d)  | ~186 |
| ≤ ~5400 dní (~15 let)                   | měsíční         | ~180 |
| cokoliv dál, až po floor 1993-06-30     | kvartální       | ~132 (33 let) |

**Ověřeno živě proti Shibui** — `DATE + INTEGER` v DuckDB funguje, `DATE + BIGINT` ne (musí být
`::INTEGER` cast). DuckDB nemá nativní `DATE_TRUNC` pro 2týdenní okna, takže se dělá ručně
integer-division bucketingem; denní/týdenní/měsíční/kvartální jde přes nativní `v.date` /
`DATE_TRUNC('week'|'month'|'quarter', v.date)`:

```sql
-- 2týdenní bucket (jediný, co potřebuje ruční trik):
DATE '1990-01-01' + (((v.date - DATE '1990-01-01') / 14)::INTEGER * 14) AS bucket
-- ověřeno na AAPL, poslední 4 měsíce → 9 čistých 14denních bodů (2026-05-04, 05-18, 06-01, ...)
```

### SQL — šablona, `{bucket_expr}` se dosadí podle zvolené granularity (tabulka výše)

```sql
WITH bucketed AS (
  SELECT {bucket_expr} AS bucket,
    arg_max(v.market_cap, v.date) AS market_cap,
    arg_max(dd.trailing_pe, v.date) AS trailing_pe,
    arg_max(dd.ev_ebitda, v.date) AS ev_ebitda,
    arg_max(dd.price_to_sales, v.date) AS price_to_sales,
    arg_max(dd.price_to_cash_flow, v.date) AS price_to_cash_flow,
    arg_max(v.price_to_book, v.date) AS price_to_book
  FROM shibui.valuation v
  INNER JOIN shibui.fundamentals_derived_daily dd ON dd.symbol = v.symbol AND dd.date = v.date
  WHERE v.ticker = '{sym}' AND v.date >= CURRENT_DATE - INTERVAL '{years} years'
  GROUP BY 1
)
SELECT *,
  PERCENT_RANK() OVER (ORDER BY trailing_pe)         AS pe_pctile,
  PERCENT_RANK() OVER (ORDER BY ev_ebitda)           AS ev_ebitda_pctile,
  PERCENT_RANK() OVER (ORDER BY price_to_sales)      AS ps_pctile,
  PERCENT_RANK() OVER (ORDER BY price_to_cash_flow)  AS pfcf_pctile,
  PERCENT_RANK() OVER (ORDER BY price_to_book)       AS pb_pctile
FROM bucketed
ORDER BY bucket
LIMIT 200
```

Python-side výběr granularity (čistá funkce rozsahu v kalendářních dnech, žádné hardcoded UI
cutoffy — endpoint si to spočítá sám, uživatel/frontend jen pošle `years`):

```python
_GRANULARITY_LADDER = [
    ("day", 190),
    ("week", 1300),
    ("biweekly", 2600),
    ("month", 5400),
    ("quarter", None),  # pokryje zbytek až po floor 1993-06-30
]

def _pick_granularity(range_days: int) -> str:
    for label, max_days in _GRANULARITY_LADDER:
        if max_days is None or range_days <= max_days:
            return label
    return "quarter"
```

`GET /market/shibui/valuation-history/{ticker}?years=10&multiples=pe,ev_ebitda,ps,pfcf,pb`
— granularitu si endpoint zvolí sám podle `years`, nejde o parametr od uživatele. Response
vrací i zvolenou granularitu (`"granularity": "month"`), ať to frontend může napsat k grafu.

### UI návrh

- Nová karta "Valuation history" na Stock stránce, vedle/pod stávajícím ratio blokem.
- Přepínač rozsahu: 1Y / 5Y / 10Y / Max. Databázový floor pro `valuation`/`fundamentals_derived_daily`
  je **1993-06-30** (ověřeno v `get_database_schema`) — konkrétní tiker může mít kratší historii
  podle data IPO. Granularita se odvíjí od adaptivního žebříčku výše (endpoint si ji zvolí sám);
  u grafu zobrazit drobný popisek podle vrácené `granularity` ("denní body" / "týdenní body" /
  "2týdenní body" / "měsíční body" / "kvartální body"), ať je jasné, na jaké rozlišení se
  člověk dívá — u 1Y bude denní/týdenní, u Max kvartální.
- Pět mini-grafů (sparkline) vedle sebe, jeden na multiple, se stínovaným pásem 10.–90. percentilu
  a zvýrazněnou aktuální hodnotou.
- U aktuální hodnoty popisek typu **"P/E 28.4 — 62. percentil svého 10letého rozsahu"** —
  přímo odpovídá na otázku "je to teď draho, nebo levně, vůči tomu, jak to firma normálně
  bývá oceněná".

---

## Doporučené pořadí implementace

1. **Ověřit latenci** (viz "Obecné poznámky") — než začneš cokoliv stavět.
2. **Fáze 1** (filings + insider + politické obchody, 1a–1g) — největší chybějící kus,
   nejvyšší hodnota, žádné otevřené nejasnosti v datech. 1g (politici) potřebuje navíc
   `ALPHA_VANTAGE_API_KEY` — jinak nezávislé na zbytku Fáze 1, jde přeskočit/odložit samostatně.
3. **Fáze 3** (short interest) — triviální, jedno pole navíc do existujícího bloku.
4. **Fáze 2** (earnings recap) — středně velká, závisí na spojení s existujícím yfinance
   revenue-estimate kódem.
5. **Fáze 5** (historické valuace) — samostatná, nezávislá na ostatních fázích.
6. **Fáze 4** (vylepšení screeneru/search/fallbacku) — nejnáročnější na testování (dotýká se
   existujících cest), dělat až budou Fáze 1–3 ověřené v praxi.

## Otevřené otázky pro tebe

- **Insider tabulka:** rovnou nahradit yfinance verzi Shibui verzí, nebo dočasně vedle sebe
  (`?source=`)? (Fáze 1b doporučuje rovnou nahradit.)
- **Politické obchody (1g):** stojí ti za to založit si zdarma Alpha Vantage API klíč
  (25 requestů/den zdarma, jen on-demand na tlačítko), nebo je to nice-to-have, co počká?
- **13F holdings detail:** stojí ti za to jako samostatný build (parsing SEC XML), nebo stačí
  jen metadata (kdo/kdy podal), co dá Shibui rovnou?
