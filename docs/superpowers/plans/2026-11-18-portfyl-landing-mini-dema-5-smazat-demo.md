# Pět mini ukázek na úvodní stránce, potom smazání plného dema: implementační plán

> **Pro agenty, kteří plán provádějí:** povinný doplňkový skill je superpowers:subagent-driven-development (doporučeno) nebo superpowers:executing-plans. Kroky jsou zaškrtávací (`- [ ]`). Každá sekce běží ve vlastním git worktree a na vlastní větvi (viz „Větve a izolace“).

**Cíl:** Na úvodní stránce portfyl.com (`/`, `/en/`, `/de/`) bude u všech pěti funkcí malá interaktivní ukázka, která vypadá jako skutečná aplikace app.portfyl.com (stejné komponenty, stejné tokeny z `DESIGN.md`), na vymyšlených a viditelně označených datech. Až majitel ukázky schválí na náhledu, smaže se veřejné plné demo `/demo` i se vším, co k němu patří (routy, odkazy, analytika, texty, SEO), a staré odkazy se přesměrují 301 na `/`.

**Architektura:** Výpočty a vzhled ukázek žijí jednou, ve sdílených panelech `frontend/src/components/showcase/`. Panely jsou čisté komponenty (jen props, žádné API, žádné `t()` s novými texty) složené ze skutečných komponent aplikace (`AllocationChart`, `AllocationBreakdownList`, `StockHeader`, `ValuationHistoryCharts`, `KpiBox`, `PerformanceChart`, `DividendBarsCard`, `PortfolioHero`, `SegmentedControl`). Dnešní stránky `/demo` je ve vlně 1 začnou používat taky (nic se nepíše dvakrát). Úvodní stránka dostane rámeček `MiniDemoSlot`: na serveru a při prvním renderu vypíše jen statický štítek a zástupný obsah (screenshot nebo text, žádná čísla), živou ukázku načte líně (`React.lazy`) až ve chvíli, kdy se rámeček blíží k obrazovce (`IntersectionObserver`). Uvnitř živé ukázky platí tokeny aplikace (Clay) a slovník aplikace pro jazyk stránky (`I18nProvider`), aby i vnitřní popisky skutečných komponent byly česky/německy.

**Tech stack:** React 18 + Vite 6, Tailwind + `index.css` (Clay), Recharts (jen v líných kouscích), Vitest + Testing Library, Node `--test` pro skripty, FastAPI (`spa_serving.py`) + pytest.

**Zdroje, které je nutné přečíst před prací:** `CLAUDE.md`, `DESIGN.md` (hlavně §3 barvy grafů, §5 písmo, §6 grafy, §10 úvodní stránka), `frontend/src/pages/Welcome.jsx`, `frontend/src/components/landing/BrokerCheck.jsx` (vzor: stejné HTML na serveru i v prohlížeči, vše proměnlivé až v efektech), `frontend/src/demo/**`.

---

## Rozsah a jak čteme zadání

- Majitel chce **všech 5 ukázek** a „stejný vzhled jako v reálné aplikaci“. Schválený rozsah říká „tvoří se jen tam, kde u funkce chybí obrázek, jinak platí screenshot“. Tyto dvě věty sladíme takto: **živá ukázka je u všech pěti funkcí**; existující screenshot funkce slouží jako **zástupný obsah** rámečku (v prerenderovaném HTML, bez JavaScriptu, před načtením a při chybě načtení). Tím screenshot dál „platí“ tam, kde živá ukázka neběží, a nikde nevzniká ukázka bez obrázku i bez textu.
- Dvě různé věci se jmenují „demo“. **Maže se jen veřejné `/demo`** (`frontend/src/demo/DemoApp.jsx` a spol.). **Nesahá se** na onboardingové ukázkové portfolio v aplikaci: `createDemoPortfolio` v `api.js`, `POST /portfolios/demo` v `backend/routers/portfolios.py`, `DemoDataBanner`, `ConnectStep`, `OnboardingView`, `activationState.js` (`sourceType: "demo"`), `eventContract.js` hodnoty `"demo"` v `sourceTypes` a `creationPaths`, `lib/gettingStarted.js`, `lib/brokerPortfolio.js`.
- `frontend/src/demo/demoPortfolio.js` a `validateDemoPortfolio.js` se ve vlnách 1 a 2 nemění; ve vlně 3 smí `demoPortfolio.js` dostat jen opravu komentáře (odkaz na zrušené `/demo/*`). Zůstávají jako zdroj dat pro ukázky (b), (c), (d).

## Pevná rozhodnutí

1. **Vzhled = Clay.** Úvodní stránka už Clay paletu používá (`CLAY_STYLE`, třída `theme-clay` na kořeni `.welcome`) a screenshoty na ní jsou v Clay vzhledu (plán 2026-11-15, rozhodnutí 7). Výchozí vzhled aplikace pro nového uživatele je Premium (`neu`, mesh gradient a průsvitné plochy na `body`), který nejde čistě uzavřít do rámečku uvnitř `.theme-clay`. Proto ukázky kreslí Clay, tedy jeden ze dvou oficiálních vzhledů aplikace. Majitel to potvrdí na náhledu (otázka O1).
2. **Skutečné komponenty, žádné kopie.** Ukázky skládají jen existující komponenty aplikace. Nové vizuální prvky v panelech jsou jen Tailwind třídy/aliasy z `DESIGN.md` §2 (`card`, `bg-surface-card`, `text-muted`...). Žádný hex, žádná nová barva grafu (barvy grafů z `CATEGORICAL` / `--chart-N`).
3. **Data jsou vymyšlená a označená.** Každý rámeček má trvale viditelný štítek „Ukázkové portfolio“ + „Vymyšlená čísla, ne skutečné výnosy.“ (cs/en/de ve `welcomeCopy.js`). Ukázka (e) a (a) používají nový soubor `showcaseData.js` (tři ukázková portfolia v EUR, USD a CZK, **pevný ukázkový kurz** 1 EUR = 25 Kč, 1 USD = 23 Kč, jasně popsaný v ukázce).
4. **Data pro jednotlivé ukázky:** (a) rozložení: držby z `showcaseData` (mají různé měny, takže „podle měn“ dává smysl); (b) detail akcie: držba z `demoPortfolio` + historie P/E z `showcaseData` (5 let po čtvrtletích), pětiletý průměr P/E se počítá z té historie (metodika Portfylu: ocenění podle 5letého průměru P/E, ne aktuálního); (c) výkonnost: `demoPortfolio.performance` + `benchmarks`; (d) dividendy: `demoPortfolio.dividends`, měsíční sloupce `DividendBarsCard`; (e) více portfolií: `showcaseData`.
5. **Statický render:** server a první render klienta vypíšou v rámečku jen štítek, popis funkce (už existující text) a zástupný obsah. Uvnitř rámečku **žádná číslice v textu**. Nic nečte `window`, `localStorage` ani čas při renderu. Recharts, panely a data nejsou ve statickém grafu chunku `src/pages/Welcome.jsx` (hlídá skript `landing-bundle-guard.mjs`).
6. **Rozpočet velikosti:** počáteční balíček (`index.html` entry) a statický graf chunku `Welcome` smí každý narůst nejvýš o **5 KiB gzip** proti základu změřenému na `main` před změnou (`frontend/scripts/landing-bundle-baseline.json`).
7. **Analytika:** jedna nová událost `landing_minidemo_used` s vlastnostmi `minidemo` (`allocation|stock|performance|dividends|portfolios`) a `language` (`cs|en|de`). Odešle se při první interakci uživatele s ovládáním ukázky, nejvýš jednou na ukázku za načtení stránky, a jen když je souhlas s analytikou `accepted` (bez souhlasu se nic neodešle ani neoznačí).
8. **Přístupnost:** ovládání je `SegmentedControl` aplikace (nativní `<button type="button">` s `aria-pressed`, `role="group"` s `aria-label`). Každý panel má textovou tabulku pro čtečky (`sr-only` `<table>` s `<caption>`). Funguje na šířce 360 px a s dlouhými německými popisky (řada tlačítek se posouvá do strany, nepřetéká stránku).
9. **Vlna 3 (smazání) začne až po schválení vln 1+2 majitelem na náhledu.** Do té doby `/demo` běží a pod každou ukázkou je odkaz na odpovídající stránku plného dema.

## Otázky pro majitele (rozhodne na náhledu, před vlnou 3)

- **O1 – vzhled:** Clay (doporučeno, viz rozhodnutí 1), nebo Premium? Při Premium by se musel řešit mesh gradient a průsvitné karty uvnitř rámečku; je to samostatná práce.
- **O2 – hlavní tlačítko při zavřených registracích:** doporučeno „Vyzkoušet ukázky“ → `#funkce` (posun na sekci s ukázkami). Alternativa: jen text „Uzavřená beta“ bez tlačítka. Plán vlny 3 počítá s doporučenou variantou.
- **O3 – po spuštění sledovat** v PostHog `landing_minidemo_used` a `signup_cta_clicked`/`signup_started` proti období před smazáním `/demo` (vědomá cena: z pěti stránek se proklikáváním akcií zbude pět malých ukázek).

## Rizika a kde se řeší

| Riziko | Ošetření |
|---|---|
| Smazání `/demo` zruší jediné hlavní tlačítko | Maže se až ve vlně 3, po rozhodnutí O2; S4 přepíše Hero, Header, Footer, closing, BrokerCheck, BrokerList, FAQ, stavový řádek |
| Recharts a komponenty aplikace jsou těžké | Jen v líných kouscích `minidemo/Mini*.jsx`; S2 přidá `landing-bundle-guard.mjs` (žádné Recharts/data ve statickém grafu `Welcome`, +5 KiB limit) |
| Hydratace a prerender | `MiniDemoSlot` na serveru nikdy nerenderuje líný kousek (stav `active=false`), test hydratace bez varování |
| Styly aplikace vs. plochá úvodní stránka (DESIGN.md §10) | Pravidla `Welcome.css` pro `h1–h4`, `p`, `a` se uvnitř `.welcome-minidemo-app` nepoužijí (`:where(:not(.welcome-minidemo-app *))`), tokeny aplikace jsou jen na `.welcome-minidemo-app` (`APP_CLAY_SCOPE`); rámeček je jediný „vyvýšený objekt“ místo screenshotu |
| (e) nemá data | Nový `showcaseData.js` s pevným ukázkovým kurzem, test invariantů |
| Rozbité staré odkazy a osiřelá analytika | S5: 301 `/demo` a `/demo/*` → `/` v `spa_serving.py`; S4: klientská pojistka v `Root.jsx`, úklid `eventContract.js` + testů, dokumentace |
| Záměna dvou „dem“ | Seznam nedotknutelných souborů výše; S4 má test, že onboardingové `"demo"` hodnoty v kontraktu zůstaly |
| Sdílené soubory | Každý hotspot má v jedné vlně jednoho vlastníka (tabulka „Vlny“) |

## Větve a izolace

- Plán leží na větvi `feature/landing-mini-dema-5-smazat-demo`. Každá sekce si z ní udělá vlastní worktree a větev `feature/landing-mini-dema-5-smazat-demo-s1` … `-s5`; nikdo necommituje na `main` a nepushuje.
- V každém worktree nejdřív `cd frontend && npm ci` (žádná sekce nemění `package.json` ani `package-lock.json`). Pokud `npm run build:cloud` v novém worktree chybí `frontend/.env.local`, zkopírovat ho (jen čtení) z hlavní složky; soubor je v `.gitignore` a necommituje se.
- Vývojový server pro vizuální kontrolu úvodní stránky: cloud edice na vlastním portu, např. S2 `npx vite --mode edition-cloud --port 5182`, S3 `--port 5183`. Úvodní stránka nepotřebuje backend ani databázi. Žádná sekce nespouští `alembic`, migrace ani sdílené porty 8000/5173.
- Hotspoty z `CLAUDE.md`: žádná sekce nemění migrace, `backend/database.py`, `requirements*`, `package*.json`, `frontend/src/i18n/messages/*`, `frontend/src/App.jsx`, `frontend/src/api.js` ani `backend/main.py` (ten už posílá redirect se stavem 301, viz `main.py` `RedirectResponse(..., status_code=301)`).

## Vlny

| Vlna | Sekce | Podmínka startu |
|---|---|---|
| 1 | S1 (sdílené panely + data + refaktor `/demo`), S2 (rámeček na úvodní stránce, texty, analytika, hlídač balíčku) | hned, paralelně |
| 2 | S3 (pět živých ukázek, vizuální a velikostní ověření) | sloučené S1 + S2 |
| 3 | S4 (frontend: smazání `/demo`, nové CTA, úklid analytiky), S5 (backend 301 + dokumentace) | sloučená vlna 2 **a** schválení majitelem na náhledu + rozhodnutí O1/O2 |

Vlastníci sdílených souborů: `welcomeCopy.js` (vlna 1 S2, vlna 3 S4), `eventContract.js` (vlna 1 S2, vlna 3 S4), `Welcome.css` (vlna 1 S2, vlna 2 S3), `FeatureList.jsx` a `MiniDemoSlot.jsx` (vlna 1 S2, vlna 3 S4), `DESIGN.md` (vlna 1 S2, vlna 3 S4), `Root.jsx` (vlna 3 S4).

---

## Smlouva mezi sekcemi (S3 na ni spoléhá, S1 a S2 ji musí dodržet přesně)

### S1 exportuje (`frontend/src/components/showcase/`)

`showcaseMath.js` (čisté funkce, žádný `Date.now()`, žádné `window`):
- `groupHoldings(holdings, key)` → `[{ name, value, weight }]`; `key` ∈ `holdings|sectors|countries|currencies|assetTypes`; holding má `symbol, sector, country, currency, assetType, marketValue, weight` (přesunuto z `DemoAllocation.jsx`).
- `buildSummary(data)` (z `DemoOverview.jsx`), `calculateMetrics(performance)` (z `DemoAnalytics.jsx`), `quarterKey(date)`, `sumBy(rows, keyFor)` (z `DemoDividends.jsx`), `stockHeaderData(holding)` (z `DemoStock.jsx`) – chování beze změny.
- `fiveYearAveragePe(points)` → průměr `trailing_pe` z bodů za posledních 5 let před posledním bodem, `null` bez dat.
- `buildDividendForecast(dividends, asOf)` → objekt ve tvaru, který čte `splitDividendForecast` z `lib/dashboardSummaries.js`: `{ year, months: [{ month: "Jan"…"Dec", paid, estimated, entries: [] }], outlook: { months: [{ month, year, confirmed, forecasted, entries: [] }] }, total_paid_all_time }`. Měsíc „teď“ se bere z `asOf`, nikdy z aktuálního data. Výhled = stejné měsíce minulého roku (označeno jako odhad z ukázkových dat).

`showcaseData.js` (zmrazená data, `Object.freeze` do hloubky; každá položka má `id` začínající `portfyl-showcase-v1`):
- `SHOWCASE_AS_OF = "2026-09-18"`.
- `SHOWCASE_RATES_TO_CZK = { CZK: 1, EUR: 25, USD: 23 }` (pevný ukázkový kurz).
- `SHOWCASE_PORTFOLIOS`: tři portfolia `{ id: "portfyl-showcase-v1-long" | "-dividend" | "-growth", key: "long" | "dividend" | "growth", baseCurrency: "EUR" | "USD" | "CZK", cash, holdings: [{ symbol, name, sector, country, currency, assetType, marketValue }] }` – `marketValue` v měně držby. Názvy portfolií nejsou v datech, dodává je copy podle `key`.
- `showcaseHoldings(displayCurrency)` → všechny držby převedené do `displayCurrency`, s `weight` (součet 100 ± 0,01).
- `portfolioTotals(displayCurrency)` → `[{ key, value, cash, weight }]`.
- `convertAmount(amount, from, to)`.
- `SHOWCASE_PE_HISTORY`: `{ MSFT, JNJ, PG }` → 20 čtvrtletních bodů `{ bucket: "YYYY-MM-DD", trailing_pe }` končících nejpozději `SHOWCASE_AS_OF`.

Panely (výchozí export, jen props; `labels` jsou hotové řetězce, panel nic nepřekládá):
- `AllocationPanel({ holdings, currency, grouping, groupings, onGroupingChange, labels })`; `groupings` = `[{ value, label }]`; `labels = { title, groupingAria, tableCaption, columns: { name, value, weight } }`. Kreslí kartu se `SegmentedControl`, `AllocationChart` pro řádky vybraného seskupení, `AllocationBreakdownList` a `sr-only` tabulku.
- `StockValuationPanel({ holding, peHistory, currency, labels })`; `labels = { pe, fivePe, forwardPe, vsAverage, historyTitle, tableCaption, disclaimer }`. Kreslí `StockHeader` (přes `stockHeaderData`), řadu `KpiBox` (P/E, 5letý průměr P/E, Forward P/E, P/E proti průměru v %), `ValuationHistoryCharts points={peHistory}` a `sr-only` tabulku bodů.
- `PerformancePanel({ performance, benchmarks, benchmarkMeta, currency, mode, onModeChange, modes, labels })`; `mode` ∈ `value|growth`; `labels = { title, modeAria, totalReturn, benchmarkReturn, tableCaption, columns: { date, value, benchmark } }`. Kreslí `KpiBox` řadu + `PerformanceChart` (v `growth` předává `calculateMetrics(...).growth`) + `sr-only` tabulku (jen měsíční body, ne všechny týdny).
- `DividendsPanel({ dividends, asOf, currency, view, onViewChange, views, labels })`; `view` ∈ `received|upcoming`; `labels = { received, upcoming, receivedTotal, upcomingTotal, viewAria, tableCaption, columns: { month, amount } }`. Kreslí `DividendBarsCard` pro vybranou polovinu ze `splitDividendForecast(buildDividendForecast(...), { monthIndex z asOf })` + `sr-only` tabulku.
- `PortfoliosPanel({ portfolios, displayCurrency, onCurrencyChange, currencies, labels })`; `labels = { currencyAria, portfolioNames: { long, dividend, growth }, ratesNote, tableCaption, columns: { name, value, weight } }`. Kreslí `PortfolioHero` (souhrn všech portfolií v `displayCurrency`, `series=[]`, `loading=false`), `AllocationBreakdownList` s řádkem na portfolio, větu s pevným kurzem a `sr-only` tabulku.

### S2 exportuje (`frontend/src/components/landing/`)

- `MiniDemoSlot({ kind, language, copy, pictures, demoHref })` – `kind` ∈ `MINI_DEMO_KINDS`; `copy = COPY[language].miniDemo`; `pictures` = pole `{ key, image, alt }` (desktopové screenshoty funkce, smí být prázdné); `demoHref` = odkaz pod ukázkou (vlna 1: stránka plného dema, vlna 3: odstraní se).
- `miniDemoRegistry.js`: `MINI_DEMO_KINDS = ["allocation", "stock", "performance", "dividends", "portfolios"]`, `MINI_DEMOS` = mapa `kind → React.lazy(() => import("./minidemo/Mini<Kind>.jsx"))` vytvořená jednou na úrovni modulu, `DEMO_HREFS` (vlna 1: `allocation → /demo/allocation`, `stock → /demo/stock/MSFT`, `performance → /demo/analytics`, `dividends → /demo/dividends`, `portfolios → /demo`).
- Každý soubor `minidemo/Mini<Kind>.jsx` má výchozí export s props `({ language, copy, onUse })`; `onUse()` zavolá při každé změně ovládání (hlídání „jednou“ je v `useMiniDemoAnalytics`). Obal `minidemo/AppScope.jsx` (`<AppScope language>`): `<div className="welcome-minidemo-app …" style={APP_CLAY_SCOPE}><I18nProvider initial={language}>…</I18nProvider></div>`.
- Copy (všechny tři jazyky, stejné klíče): každá položka `features[]` dostane `demo: "<kind>"`; nový blok `miniDemo`:
  `{ badge, disclaimer, loading, unavailable, openDemo, allocation: { title, groupingAria, groupings: { holdings, sectors, currencies }, tableCaption, columns: { name, value, weight } }, stock: { pickAria, pe, fivePe, forwardPe, vsAverage, historyTitle, tableCaption, disclaimer }, performance: { title, modeAria, modes: { value, growth }, totalReturn, benchmarkReturn, tableCaption, columns: { date, value, benchmark } }, dividends: { viewAria, received, upcoming, receivedTotal, upcomingTotal, tableCaption, columns: { month, amount } }, portfolios: { currencyAria, portfolioNames: { long, dividend, growth }, ratesNote, tableCaption, columns: { name, value, weight } } }`.
  `badge` = „Ukázkové portfolio“ / „Sample portfolio“ / „Beispielportfolio“; `disclaimer` = „Vymyšlená čísla, ne skutečné výnosy.“ / „Made-up numbers, not real returns.“ / „Erfundene Zahlen, keine echten Renditen.“. `badge`, `disclaimer`, `loading`, `unavailable`, `openDemo` **nesmí obsahovat číslici** (jsou ve statickém HTML). `ratesNote` číslice mít smí (jen v živé ukázce).

---

## S1: Sdílené panely ukázek, ukázková data a refaktor stránek /demo (vlna 1)

**Soubory (jiné neměnit):**
- Vytvořit: `frontend/src/components/showcase/showcaseMath.js`, `frontend/src/components/showcase/showcaseMath.test.js`, `frontend/src/components/showcase/showcaseData.js`, `frontend/src/components/showcase/showcaseData.test.js`, `frontend/src/components/showcase/AllocationPanel.jsx`, `frontend/src/components/showcase/StockValuationPanel.jsx`, `frontend/src/components/showcase/PerformancePanel.jsx`, `frontend/src/components/showcase/DividendsPanel.jsx`, `frontend/src/components/showcase/PortfoliosPanel.jsx`, `frontend/src/components/showcase/panels.test.jsx`
- Změnit: `frontend/src/demo/pages/DemoAllocation.jsx`, `frontend/src/demo/pages/DemoAnalytics.jsx`, `frontend/src/demo/pages/DemoDividends.jsx`, `frontend/src/demo/pages/DemoOverview.jsx`, `frontend/src/demo/pages/DemoStock.jsx`, `frontend/src/demo/pages/DemoAllocation.test.jsx`, `frontend/src/demo/pages/DemoAnalytics.test.jsx`, `frontend/src/demo/pages/DemoDividends.test.jsx`, `frontend/src/demo/pages/DemoOverview.test.jsx`, `frontend/src/demo/pages/DemoStock.test.jsx`
- **Nemění se:** `demoPortfolio.js`, `validateDemoPortfolio.js`, jakákoli komponenta v `frontend/src/components/` mimo `showcase/`.

### Kroky

- [ ] **1. Testy výpočtů (červeně).** `showcaseMath.test.js`:
  - `groupHoldings` nad `demoPortfolio.holdings` pro `holdings` dá 10 řádků, pro `sectors` 10, součet vah 100 ± 0,01; pro `currencies` nad `showcaseHoldings("CZK")` dá právě 3 řádky `CZK`, `EUR`, `USD`.
  - `calculateMetrics`, `buildSummary`, `quarterKey`, `sumBy`, `stockHeaderData` vrací pro `demoPortfolio` stejné hodnoty jako dnešní kód v `src/demo/pages` (zkopírovat dnešní výsledky jako očekávané hodnoty před přesunem).
  - `fiveYearAveragePe(SHOWCASE_PE_HISTORY.MSFT)` = aritmetický průměr bodů v okně 5 let (ručně spočítané číslo v testu), `fiveYearAveragePe([])` = `null`, body s `trailing_pe: null` se ignorují.
  - `buildDividendForecast(demoPortfolio.dividends, demoPortfolio.asOf)`: 12 měsíců, `paid` měsíců po `asOf` je 0, součet `paid` v roce `asOf` sedí se součtem dividend toho roku do `asOf`, výsledek prošlý `splitDividendForecast(..., { monthIndex: 8 })` má `received.total > 0` a `upcoming.total > 0`; volání dvakrát s `vi.setSystemTime` na jiné datum dává totéž (nezávislost na čase).
- [ ] **2. Testy dat (červeně).** `showcaseData.test.js`: tři portfolia s klíči `long|dividend|growth` a měnami `EUR|USD|CZK`; každé `id` začíná `portfyl-showcase-v1`; kurzy přesně `{ CZK: 1, EUR: 25, USD: 23 }`; `showcaseHoldings(c)` pro `CZK|EUR|USD` má součet vah 100 ± 0,01 a stejné pořadí; `portfolioTotals("CZK")` součet hodnot = součet `showcaseHoldings("CZK")` + hotovost převedená do CZK (± 0,01); `SHOWCASE_PE_HISTORY` má pro `MSFT|JNJ|PG` 20 bodů, data rostou, poslední ≤ `SHOWCASE_AS_OF`, všechna P/E konečná a > 0; data jsou zmrazená (`Object.isFrozen` do hloubky); žádné pole se jménem `account`, `iban`, `email`, `user`.
- [ ] **3. Implementace** `showcaseMath.js` (přesun funkcí ze stránek `src/demo/pages`, beze změny výsledků) a `showcaseData.js` (vymyšlené, ale věrohodné hodnoty; ≥ 3 sektory a ≥ 3 země napříč portfolii; hodnoty zaokrouhlené na 2 desetinná místa). `npm test -- src/components/showcase` zeleně.
- [ ] **4. Testy panelů (červeně).** `panels.test.jsx` (v `beforeAll` stub `ResizeObserver` a šířky pro `ResponsiveContainer` podle vzoru dnešních testů `src/demo/pages/*.test.jsx`; `vi.mock("../../api", …)` proxy, která hodí chybu při jakémkoli přístupu – panel nesmí importovat API klienta; `fetch` je `vi.fn()` a nesmí být zavolán). Pro každý panel:
  - vykreslí `labels.title`/hlavní popisek a `sr-only` tabulku s `caption` = `labels.tableCaption` a správným počtem řádků;
  - ovládání je `role="group"` s `aria-label` z `labels.*Aria`, tlačítka jsou `type="button"` a právě jedno má `aria-pressed="true"`; klik zavolá `on…Change` s hodnotou;
  - `AllocationPanel`: přepnutí `grouping` na `currencies` změní řádky tabulky na `CZK/EUR/USD`;
  - `StockValuationPanel`: zobrazí P/E, 5letý průměr (hodnota z `fiveYearAveragePe` naformátovaná na 1 desetinné místo) a rozdíl v %;
  - `PerformancePanel`: `mode="growth"` předá `PerformanceChart` data s `pnl_pct` (ověřit přes vykreslený text tabulky nebo `vi.mock` `PerformanceChart` s kontrolou props);
  - `DividendsPanel`: `view="upcoming"` ukáže `labels.upcoming`; tabulka má 12 řádků;
  - `PortfoliosPanel`: tři řádky s názvy z `labels.portfolioNames`, `labels.ratesNote` je vidět, přepnutí měny změní měnu v tabulce (např. `Kč` → `€`);
  - žádný panel nevolá `useT` s novým textem: test projde `rg -n "t\(\"" frontend/src/components/showcase` v kontrolním kroku 7 (výsledek musí být prázdný).
- [ ] **5. Implementace panelů** podle smlouvy výše. Ovládání = `SegmentedControl` (`components/ui/SegmentedControl.jsx`, už dává `aria-pressed` a `role="group"`). Karty `className="card p-5"` jako na stránkách aplikace, nadpisy přes `SectionHeader`. Na 360 px nic nepřetéká: tabulky a řady tlačítek v kontejneru s `overflow-x-auto`/`min-w-0`, grafy v `ResponsiveContainer` dané komponenty. Žádné nové barvy, žádné `style={{ color: … }}` s hexem.
- [ ] **6. Refaktor `/demo`.** Stránky `DemoAllocation`, `DemoAnalytics`, `DemoDividends`, `DemoOverview`, `DemoStock` importují funkce ze `showcaseMath.js` a vykreslují panely tam, kde dnes kreslí stejnou věc: `DemoAllocation` → `AllocationPanel` (seskupení všech pěti klíčů, stav na stránce), `DemoAnalytics` → `PerformancePanel` (výchozí `growth`), `DemoDividends` → navíc `DividendsPanel` nad dnešními kartami, `DemoStock` → `StockValuationPanel` (pro symboly bez historie P/E předá `peHistory=[]` a panel ukáže „—“), `DemoOverview` → `PerformancePanel` v režimu `value` místo samotného `PerformanceChart`. Popisky na `/demo` zůstávají anglické řetězce, které tam jsou dnes (předají se jako `labels`). Testy `src/demo/**` upravit jen tam, kde se změnil text nebo struktura; přidat do `DemoAllocation.test.jsx` ověření, že přepnutí na „Currencies“ funguje přes `aria-pressed`.
- [ ] **7. Kontrola a commit.**
  - `cd frontend && npm test -- src/components/showcase src/demo` zeleně.
  - `cd frontend && npm test` a `cd frontend && npm run test:cloud` zeleně.
  - `cd frontend && npm run audit:readability` bez nových nálezů.
  - `rg -n "#[0-9a-fA-F]{3,8}\b" frontend/src/components/showcase` a `rg -n "t\(\"" frontend/src/components/showcase` prázdné.
  - Commit: `feat(showcase): shared demo panels and showcase data, /demo uses them`.

**Hotovo, když:** všechny exporty ze smlouvy existují s danými props; `/demo` vypadá a funguje stejně (plus nové panely), testy obou edic zelené, žádný hex ani nový text přes `t()` v `showcase/`.

---

## S2: Rámeček mini ukázek na úvodní stránce, texty cs/en/de, analytika a hlídač balíčku (vlna 1)

**Soubory (jiné neměnit):**
- Vytvořit: `frontend/src/components/landing/MiniDemoSlot.jsx`, `frontend/src/components/landing/MiniDemoSlot.test.jsx`, `frontend/src/components/landing/miniDemoRegistry.js`, `frontend/src/components/landing/useMiniDemoAnalytics.js`, `frontend/src/components/landing/useMiniDemoAnalytics.test.jsx`, `frontend/src/components/landing/FeatureList.test.jsx`, `frontend/src/components/landing/minidemo/AppScope.jsx`, `frontend/src/components/landing/minidemo/appClayScope.js`, `frontend/src/components/landing/minidemo/appClayScope.test.js`, `frontend/src/components/landing/minidemo/MiniAllocation.jsx`, `frontend/src/components/landing/minidemo/MiniStock.jsx`, `frontend/src/components/landing/minidemo/MiniPerformance.jsx`, `frontend/src/components/landing/minidemo/MiniDividends.jsx`, `frontend/src/components/landing/minidemo/MiniPortfolios.jsx`, `frontend/scripts/landing-bundle-guard.mjs`, `frontend/scripts/landing-bundle-guard.test.mjs`, `frontend/scripts/landing-bundle-baseline.json`
- Změnit: `frontend/src/components/landing/FeatureList.jsx`, `frontend/src/pages/Welcome.jsx`, `frontend/src/pages/Welcome.css`, `frontend/src/pages/Welcome.test.jsx`, `frontend/src/pages/welcomeCopy.js`, `frontend/src/analytics/eventContract.js`, `frontend/src/analytics/eventContract.test.js`, `DESIGN.md`

### Kroky

- [ ] **0. Základ velikosti (před jakoukoli změnou).** Napsat nejdřív jen `landing-bundle-guard.mjs` + test (krok 1), pak na nezměněném kódu: `cd frontend && npm run build:cloud && node scripts/landing-bundle-guard.mjs dist --write-baseline scripts/landing-bundle-baseline.json`. Soubor obsahuje `{ "measured_on": "<git rev-parse --short HEAD>", "entry_gzip_bytes": …, "welcome_closure_gzip_bytes": …, "limit_increase_bytes": 5120 }`. Commitnout zvlášť: `chore(landing): bundle guard and size baseline`.
- [ ] **1. Hlídač balíčku (test napřed).** `landing-bundle-guard.test.mjs` (`node --test`, falešný `dist` v dočasné složce s ručně psaným `.vite/manifest.json`, chunky a `prerendered/{,en/,de/}index.html`):
  - selže, když soubor ze statického grafu `src/pages/Welcome.jsx` (`collectInitialAssets(manifest, "src/pages/Welcome.jsx")` importované z `measure-initial-bundle.mjs`, ten se nemění) obsahuje `recharts-surface`, `Vanguard S&P 500 UCITS ETF` nebo `portfyl-showcase-v1`; projde, když jsou jen v dynamických importech;
  - selže, když `entry` nebo `welcome closure` gzip přesáhne základ + `limit_increase_bytes`;
  - selže, když v některé prerenderované stránce není právě 5 bloků `<figure class="welcome-minidemo…">…</figure>` nebo když text bloku (po odstranění tagů a atributů) obsahuje číslici; atributy (`width="1047"`, `alt`) se nepočítají;
  - režim `--write-baseline` kontrolu figur přeskočí (na `main` ještě nejsou).
  Implementace `landing-bundle-guard.mjs`: CLI `node scripts/landing-bundle-guard.mjs <dist> [--baseline <json>] [--write-baseline <json>]`, výstup JSON s naměřenými čísly, `process.exitCode = 1` při porušení s jasnou zprávou.
- [ ] **2. Kontrakt analytiky (test napřed).** `eventContract.test.js`: `sanitizeEvent("landing_minidemo_used", { minidemo: "stock", language: "de" })` projde; neznámá hodnota `minidemo`, chybějící `language` nebo vlastnost navíc v přísném režimu hodí chybu; ostatní testy beze změny. Implementace: `ANALYTICS_EVENTS.LANDING_MINIDEMO_USED = "landing_minidemo_used"`, množina `miniDemoKinds` (5 hodnot), pole `minidemo`, schéma `["minidemo", "language"]`. Nic dalšího v kontraktu neměnit.
- [ ] **3. Tokeny aplikace pro rámeček (test napřed).** `appClayScope.test.js`: přečte zdroj `src/App.jsx` (`sourcePath` z `src/test/sourcePath`), vytáhne všechny `s.setProperty("--…"` z teplé větve `applyAppearance` (od `if (warm)` po první `return;`) a ověří, že `APP_CLAY_SCOPE` má každou z nich (`--chart-1…8` včetně); hodnoty se rovnají `CLAY_TOKENS` (`--sidebar-active` = `brandLight`); `APP_CLAY_SCOPE` neobsahuje `--landing-paper`. Implementace `appClayScope.js` jen z `CLAY_TOKENS` (žádný hex v souboru). `AppScope.jsx`: `<div className="welcome-minidemo-app font-sans text-ink bg-surface" style={APP_CLAY_SCOPE}>` + `<I18nProvider initial={language}>` (bez ukládání jazyka; slovník aplikace se načte jako vlastní chunk).
- [ ] **4. Analytický hook (test napřed).** `useMiniDemoAnalytics.test.jsx` s `AnalyticsProvider` + `createMemoryAdapter`: při souhlasu `accepted` první `reportUse()` pošle `["landing_minidemo_used", { minidemo: "dividends", language: "cs" }]`, druhé nic; jiná ukázka pošle vlastní událost; při `pending` a `rejected` se nic nepošle a po pozdějším přijetí souhlasu první interakce událost pošle; bez provideru (`useOptionalAnalytics` vrací `null`) nic nespadne. Implementace: `useMiniDemoAnalytics(kind, language)` → `reportUse`, ref „už odesláno“ se nastaví jen při `consent === "accepted"`; neposílá se na `localStorage` (`captureOnce` se nepoužije, „jednou“ platí na načtení stránky).
- [ ] **5. Copy (test napřed).** Do `Welcome.test.jsx` přidat: všechny tři jazyky mají stejnou strukturu klíčů `miniDemo` (rekurzivní porovnání klíčů), všech 5 `features` má `demo` s hodnotami v pořadí `allocation, stock, performance, dividends, portfolios`, `badge/disclaimer/loading/unavailable/openDemo` neobsahují číslici. Doplnit texty do `welcomeCopy.js` (cs, en, de) podle smlouvy; německé popisky tlačítek psát plně (žádné zkratky), aby se otestovala dlouhá slova.
- [ ] **6. `MiniDemoSlot` (test napřed).** `MiniDemoSlot.test.jsx` (`vi.mock("./miniDemoRegistry", …)` s testovací lehkou komponentou místo líných kousků):
  - `renderToString(<MiniDemoSlot …/>)` obsahuje `copy.badge` a `copy.disclaimer`, screenshot z `pictures` (pokud je) a **žádnou číslici v textu** a žádné `recharts`; nevolá `IntersectionObserver` ani `window` (spy na globální `IntersectionObserver` = 0 volání při renderu na serveru);
  - hydratace: `container.innerHTML = renderToString(…)`, `hydrateRoot(container, …)`, `console.error` spy = 0 volání (žádné varování o nesouladu);
  - se stubem `IntersectionObserver`: dokud nenastane průsečík, je vidět zástupný obsah; po `isIntersecting` se vykreslí ukázka a observer se odpojí (`disconnect` zavolán); bez `IntersectionObserver` v prostředí se ukázka aktivuje po mountu;
  - komponenta ukázky, která hodí chybu, nebo odmítnutý `import()` → zůstane zástupný obsah + text `copy.unavailable`, stránka nespadne (error boundary);
  - `onUse` předaný ukázce volá `useMiniDemoAnalytics` (ověřit událostí v memory adapteru);
  - pod ukázkou je odkaz s textem `copy.openDemo` na `demoHref`.
  Implementace: `<figure className="welcome-minidemo" data-minidemo={kind}>` → horní řádek štítku (`<p className="welcome-minidemo-label"><strong>{badge}</strong> <span>{disclaimer}</span></p>`), tělo (`active ? <ErrorBoundary><Suspense fallback={placeholder}><Demo language copy onUse/></Suspense></ErrorBoundary> : placeholder`), odkaz. Stav `active` začíná `false` na serveru i v prohlížeči; `IntersectionObserver` s `rootMargin: "200px 0px"` se zakládá jen v `useEffect`.
- [ ] **7. Stuby pěti ukázek.** `minidemo/Mini<Kind>.jsx`: výchozí export `({ language, copy, onUse })`, vrací `<AppScope language={language}><div className="card p-5"><p className="text-muted">{copy.loading}</p></div></AppScope>` (bez čísel, bez Recharts). Skutečný obsah doplní S3. `miniDemoRegistry.js` podle smlouvy.
- [ ] **8. `FeatureList` a `Welcome` (test napřed).** `FeatureList.test.jsx`: všech 5 funkcí je řádek `article.welcome-feature` s jedním `figure.welcome-minidemo` ve správném pořadí `data-minidemo`; zástupný obsah obsahuje desktopové screenshoty funkce z `LANDING_IMAGES` (ne `phone…`), funkce bez obrázku má v zástupném obsahu jen text; textový pás `welcome-more` se nevykreslí, když mají všechny funkce `demo`. `Welcome.test.jsx`: povolené odkazy rozšířit o `^/demo/(allocation|analytics|dividends|stock/[A-Z]+)$`, test „prerenderované HTML obsahuje 5 štítků ukázek“. Implementace: `FeatureList({ copy, language })` předá `kind`, `language`, `copy.miniDemo`, obrázky a `DEMO_HREFS[kind]` do `MiniDemoSlot`; `Welcome.jsx` jen předá `language` do `FeatureList`.
- [ ] **9. Styly (test napřed).** Stávající testy `Welcome.test.jsx` (žádný hex, písmo ≥ 12 px) platí dál. Přidat test, který ve zdroji `Welcome.css` ověří, že pravidla pro `h1–h4`, `p` a `a` uvnitř `.welcome` obsahují `:where(:not(.welcome-minidemo-app *))` (tj. nezasáhnou ukázku). Implementace v `Welcome.css`:
  - `.welcome :is(h1,h2,h3,h4):where(:not(.welcome-minidemo-app *))`, `.welcome p:where(:not(.welcome-minidemo-app *))`, `:where(.welcome) a:where(:not(.welcome-minidemo-app *))` místo dnešních selektorů (specifičnost se nemění);
  - `.welcome-minidemo`: stejný rámeček jako `.welcome-shot` (16 px radius, 12 px na telefonu, hairline `--w-line`, jeden stín `--w-shadow`), pozadí `var(--bg)`, vnitřní odsazení; `min-height` podle druhu přes `[data-minidemo="…"]` (proti skákání stránky); `.welcome-minidemo-label` v `--muted`, písmo ≥ 0.75rem;
  - nic z `.welcome-minidemo-app` nesmí ovlivnit zbytek stránky (pravidla jen pod tímto selektorem).
- [ ] **10. `DESIGN.md` §10.** Doplnit: „Jediný vyvýšený objekt je screenshot **nebo rámeček mini ukázky** (`MiniDemoSlot`): stejný rámeček, uvnitř Clay tokeny aplikace (`APP_CLAY_SCOPE` na `.welcome-minidemo-app`) a skutečné komponenty aplikace; landingová pravidla pro nadpisy, odstavce a odkazy uvnitř neplatí; v HTML jen štítek „Ukázkové portfolio / Vymyšlená čísla“ a zástupný obsah, živá ukázka se načte líně.“ Upravit větu o pořadí sekcí (funkce = řádky s ukázkami).
- [ ] **11. Ověření a commit.**
  - `cd frontend && npm test -- src/components/landing src/pages/Welcome.test.jsx src/analytics/eventContract.test.js` zeleně.
  - `cd frontend && node --test scripts/landing-bundle-guard.test.mjs scripts/measure-initial-bundle.test.mjs scripts/prerender.test.mjs` zeleně.
  - `cd frontend && npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud` zeleně (prerender nesmí hlásit chybu ani inline skript).
  - `cd frontend && node scripts/landing-bundle-guard.mjs dist --baseline scripts/landing-bundle-baseline.json` projde.
  - Ruční kontrola `npx vite --mode edition-cloud --port 5182`: `/`, `/en/`, `/de/` na 1280 px a 360 px; pět rámečků se štítkem, žádné vodorovné posouvání stránky, nadpisy a odstavce úvodní stránky vypadají jako dřív.
  - Commit: `feat(landing): mini demo frame, copy and analytics event`.

**Hotovo, když:** úvodní stránka má 5 rámečků se štítkem (zatím se stuby), prerender je bez čísel v rámečcích a bez Recharts v chunku `Welcome`, hlídač prochází proti základu, nová událost je v kontraktu, `DESIGN.md` popisuje rámeček.

---

## S3: Pět živých mini ukázek, ověření vzhledu, přístupnosti a velikosti (vlna 2)

**Předpoklad:** S1 a S2 sloučené do integrační větve; S3 z ní vychází.

**Soubory (jiné neměnit):**
- Změnit: `frontend/src/components/landing/minidemo/MiniAllocation.jsx`, `frontend/src/components/landing/minidemo/MiniStock.jsx`, `frontend/src/components/landing/minidemo/MiniPerformance.jsx`, `frontend/src/components/landing/minidemo/MiniDividends.jsx`, `frontend/src/components/landing/minidemo/MiniPortfolios.jsx`, `frontend/src/pages/Welcome.css` (jen `min-height` a odsazení rámečků podle skutečné výšky), `frontend/src/components/showcase/AllocationPanel.jsx`, `frontend/src/components/showcase/StockValuationPanel.jsx`, `frontend/src/components/showcase/PerformancePanel.jsx`, `frontend/src/components/showcase/DividendsPanel.jsx`, `frontend/src/components/showcase/PortfoliosPanel.jsx` (panely jen pro opravy rozložení zjištěné při vizuální kontrole; props se nemění)
- Vytvořit: `frontend/src/components/landing/minidemo/miniDemoLabels.js`, `frontend/src/components/landing/minidemo/miniDemoLabels.test.js`, `frontend/src/components/landing/minidemo/miniDemos.test.jsx`, `docs/operations/landing-minidemo-check.md`

### Kroky

- [ ] **1. Mapování textů (test napřed).** `miniDemoLabels.test.js`: pro `cs|en|de` vrací `allocationLabels(copy)`, `stockLabels(copy)`, `performanceLabels(copy)`, `dividendsLabels(copy)`, `portfoliosLabels(copy)` objekty přesně ve tvaru `labels` ze smlouvy S1, žádná hodnota není prázdná ani `undefined`. Implementace `miniDemoLabels.js` (čisté funkce nad `COPY[language].miniDemo`).
- [ ] **2. Testy ukázek (červeně).** `miniDemos.test.jsx` (stub `ResizeObserver`; `vi.mock("../../../api", …)` proxy hází chybu; `fetch` spy nevolán; render přes `MiniDemoSlot` se stubem `IntersectionObserver`, který hned hlásí průsečík, pro `cs`, `en` a `de`):
  - (a) `MiniAllocation`: výchozí seskupení „pozice“; klik na „měny“ nastaví `aria-pressed="true"` jen na něm a tabulka má 3 řádky `CZK/EUR/USD`; `onUse` → jedna událost `landing_minidemo_used` s `minidemo: "allocation"` (souhlas `accepted`), druhý klik žádnou;
  - (b) `MiniStock`: výběr `MSFT/JNJ/PG` (`copy.stock.pickAria`), zobrazí P/E, 5letý průměr P/E a rozdíl; přepnutí na `PG` změní nadpis `StockHeader`;
  - (c) `MiniPerformance`: přepínač `value/growth`, v `growth` je vidět výnos portfolia i S&P 500 (`KpiBox`);
  - (d) `MiniDividends`: přepínač `received/upcoming`, karta `DividendBarsCard` s měsíci v jazyce stránky (cs: „led“/„Led“ podle slovníku aplikace – ověřit proti `frontend/src/i18n/messages/cs.js`, ne natvrdo);
  - (e) `MiniPortfolios`: tři portfolia s názvy z copy, přepínač `CZK/EUR/USD`, věta `ratesNote` viditelná;
  - u každé ukázky je trvale vidět štítek `badge` + `disclaimer` a `sr-only` tabulka s `caption`;
  - žádné varování v `console.error` během testu.
- [ ] **3. Implementace pěti ukázek.** Každá: `<AppScope language={language}>` + vlastní `useState` pro ovládání + příslušný panel z `components/showcase/` + data (`demoPortfolio` pro b/c/d, `showcaseData` pro a/e) + `onUse()` v každém `on…Change`. Výchozí stavy: (a) `holdings`, zobrazovací měna `CZK` pro cs, `EUR` pro de, `USD` pro en; (b) `MSFT`; (c) `growth`; (d) `received`; (e) měna podle jazyka jako u (a). Žádné texty natvrdo; všechno z `miniDemoLabels.js`.
- [ ] **4. Velikost a prerender.**
  - `cd frontend && npm run build:cloud && node scripts/landing-bundle-guard.mjs dist --baseline scripts/landing-bundle-baseline.json` projde (Recharts a data jen v dynamických chuncích, +5 KiB limity dodrženy).
  - `cd frontend && npm run measure:bundle` → čísla zapsat do `docs/operations/landing-minidemo-check.md`.
  - V `dist/prerendered/index.html`, `en/index.html`, `de/index.html` ověřit 5 rámečků se štítkem a žádné číslo v jejich textu (hlídač to dělá; zapsat výsledek).
- [ ] **5. Vizuální kontrola proti aplikaci.** `npx vite --mode edition-cloud --port 5183` a Playwright MCP:
  - snímky všech pěti ukázek na `/`, `/en/`, `/de/` při 1280 px a 360 px (Playwright `browser_resize` 360×800), plus při 768 px;
  - porovnat s tímtéž v aplikaci ve vzhledu Clay (stejné komponenty: Allocation, Stock → Ocenění, Analytics, Dividends, Dashboard). Pokud lokální aplikace neběží (potřebuje `DATABASE_URL` a přihlášení), porovnat se stránkami `/demo/*` nastavenými na Clay přes třídu `theme-clay` v devtools a s `DESIGN.md` §3–§6: barvy grafů v pořadí `--chart-1…`, karty 24 px radius s Clay stínem, `SegmentedControl` s klouzavým pozadím, písmo ≥ 12 px;
  - zkontrolovat, že nadpisy, odstavce a odkazy úvodní stránky mimo rámečky vypadají stejně jako na snímku z `main` (plochý vzhled, DESIGN.md §10);
  - `prefers-reduced-motion: reduce` (Playwright `browser_emulate_media`): ukázky fungují, animace aplikace se chovají jako v aplikaci;
  - klávesnice: Tab projde tlačítky ukázky, Enter/mezerník přepíná, viditelný fokus;
  - Lighthouse/čtečka: tabulky `sr-only` mají `caption`; žádné vodorovné posouvání stránky na 360 px (`document.documentElement.scrollWidth <= 360`).
  - Snímky poslat majiteli (SendUserFile) jako podklad pro schválení; seznam a výsledky zapsat do `docs/operations/landing-minidemo-check.md` (krátká kontrolní stránka: co se kontrolovalo, čísla velikosti, otázky O1–O3).
- [ ] **6. Ověření a commit.** `cd frontend && npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`, `npm run audit:readability`, `node --test scripts/landing-bundle-guard.test.mjs` zeleně. Commit: `feat(landing): five live mini demos built from the app's own components`.

**Hotovo, když:** pět živých ukázek funguje v cs/en/de na telefonu i počítači, vypadají jako aplikace (Clay), velikostní limity platí, prerender je bez čísel v rámečcích, analytika posílá nejvýš jednu událost na ukázku po souhlasu, majitel má snímky k odsouhlasení. **Zde je stopka: vlna 3 jen po výslovném schválení majitelem a rozhodnutí O1/O2.**

---

## S4: Smazání veřejného /demo ve frontendu, nové hlavní tlačítko a úklid analytiky (vlna 3)

**Předpoklad:** sloučená vlna 2, schválení majitelem, O2 rozhodnuto (níže je doporučená varianta `#funkce`; při jiném rozhodnutí upravit jen texty a cíle odkazů, ne rozsah souborů).

**Soubory (jiné neměnit):**
- Smazat: `frontend/src/demo/DemoApp.jsx`, `frontend/src/demo/DemoApp.test.jsx`, `frontend/src/demo/DemoBootstrap.jsx`, `frontend/src/demo/DemoDataContext.jsx`, `frontend/src/demo/DemoShell.jsx`, `frontend/src/demo/demoCopy.js`, `frontend/src/demo/demoIsolation.test.jsx`, `frontend/src/demo/demoRouteWalk.test.jsx`, `frontend/src/demo/pages/DemoAllocation.jsx`, `frontend/src/demo/pages/DemoAllocation.test.jsx`, `frontend/src/demo/pages/DemoAnalytics.jsx`, `frontend/src/demo/pages/DemoAnalytics.test.jsx`, `frontend/src/demo/pages/DemoDividends.jsx`, `frontend/src/demo/pages/DemoDividends.test.jsx`, `frontend/src/demo/pages/DemoOverview.jsx`, `frontend/src/demo/pages/DemoOverview.test.jsx`, `frontend/src/demo/pages/DemoStock.jsx`, `frontend/src/demo/pages/DemoStock.test.jsx`, `frontend/src/analytics/useDemoAnalytics.js`, `frontend/src/analytics/useDemoAnalytics.test.jsx`
- Změnit: `frontend/src/demo/demoPortfolio.js` (jen komentář), `frontend/src/Root.jsx`, `frontend/src/Root.test.jsx`, `frontend/src/lib/routes.js`, `frontend/src/lib/routes.test.js`, `frontend/src/pages/Welcome.jsx`, `frontend/src/pages/Welcome.test.jsx`, `frontend/src/pages/welcomeCopy.js`, `frontend/src/components/landing/LandingHero.jsx`, `frontend/src/components/landing/LandingHeader.jsx`, `frontend/src/components/landing/LandingFooter.jsx`, `frontend/src/components/landing/BrokerCheck.jsx`, `frontend/src/components/landing/BrokerCheck.test.jsx`, `frontend/src/components/landing/BrokerList.jsx`, `frontend/src/components/landing/FeatureList.jsx`, `frontend/src/components/landing/FeatureList.test.jsx`, `frontend/src/components/landing/MiniDemoSlot.jsx`, `frontend/src/components/landing/MiniDemoSlot.test.jsx`, `frontend/src/components/landing/miniDemoRegistry.js`, `frontend/src/analytics/eventContract.js`, `frontend/src/analytics/eventContract.test.js`, `frontend/src/analytics/AnalyticsProvider.test.jsx`, `frontend/src/analytics/analyticsClient.test.js`, `frontend/src/analytics/analyticsCopy.js` (jen komentář), `frontend/src/pages/Register.jsx`, `frontend/src/pages/Register.intent.test.jsx`, `frontend/src/pages/AuthPages.test.jsx`, `frontend/src/lib/signupIntent.js` (jen komentář), `frontend/src/seo/publicPages.js`, `frontend/src/seo/publicPages.test.js`, `frontend/src/components/stock/StockHeader.jsx` (jen komentář), `frontend/src/components/layout/NavGroupsContext.js` (jen komentář), `DESIGN.md`
- **Nesahat:** `validateDemoPortfolio.js` (+ test), `components/showcase/**`, `components/landing/minidemo/**`, onboardingové demo (seznam v „Rozsah“), `frontend/src/i18n/messages/*`.

### Kroky

- [ ] **1. Testy cílového stavu (červeně).**
  - `Welcome.test.jsx`: při zavřených registracích je hlavní tlačítko v hero, hlavičce i závěru odkaz na `#funkce` s textem `copy.examplesCta`; na stránce (cs/en/de, otevřené i zavřené registrace) **neexistuje žádný `href` začínající `/demo`**; stavový řádek nezmiňuje demo; povolené odkazy už neobsahují `/demo`; testy `demo_started` nahradit testem, že klik na hlavní tlačítko neposílá žádnou analytickou událost a nemění `pathname`.
  - `BrokerCheck.test.jsx`: místo odkazu na demo odkaz `#funkce` (`copy.examples`); při otevřených registracích beze změny.
  - `FeatureList.test.jsx`, `MiniDemoSlot.test.jsx`: pod ukázkou už není odkaz (prop `demoHref` zrušena).
  - `Root.test.jsx`: `/demo` a `/demo/allocation` na `portfyl.com` vyvolají `window.location.replace("/")` (spy) a nevykreslí tracker ani demo; `/demolition` jde dál do trackeru; na `app.portfyl.com` se `/demo` chová jako jakákoli neznámá cesta trackeru (beze změny).
  - `routes.test.js`: `isDemoPath` zmizí, `isRetiredDemoPath` platí pro `/demo`, `/demo/`, `/demo/x` jen v cloud edici, ne pro `/demolition`.
  - `eventContract.test.js`: `demo_started`, `demo_page_viewed`, `demo_stock_viewed`, `demo_activation_reached` jsou neznámé události; `signup_cta_clicked`/`signup_started` s `source_surface: "demo"` neprojdou; `landing_minidemo_used` projde; **`portfolio_created` s `creation_path: "demo"` a `source_type: "demo"` dál projdou** (onboardingové demo).
  - `Register.intent.test.jsx`, `AuthPages.test.jsx`: `?source=demo` vede na `source_surface: "direct"`.
  - `publicPages.test.js`: `DISALLOWED_PATHS` neobsahuje `/demo` (301 musí robot vidět), popisy stránek nezmiňují demo, `robots.txt` a `sitemap.xml` neobsahují `/demo`.
  - `AnalyticsProvider.test.jsx`, `analyticsClient.test.js`: místo `demo_started` použít `landing_viewed` s platnými vlastnostmi (testují mechaniku, ne konkrétní událost).
- [ ] **2. Smazání.** `git rm` souborů ze seznamu „Smazat“. `Root.jsx`: odstranit líný import `./demo/DemoBootstrap` a větev `showDemo`; pro `isRetiredDemoPath(pathname) && !trackerHost` vykreslit malou komponentu, která v `useEffect` zavolá `window.location.replace("/")` a do té doby ukáže stejný `role="status"` text jako Suspense (pojistka pro klientskou navigaci a hostitele bez backendu; hlavní přesměrování dělá server, S5). `routes.js`: `isDemoPath` → `isRetiredDemoPath` + komentář.
- [ ] **3. Nové CTA a texty (cs/en/de).** `welcomeCopy.js`: odstranit `demoCta`, `demoCtaShort`, `demoLink`, `demoNote`, `brokerCheck.demo`, `footer.demo`, `miniDemo.openDemo`; přidat `examplesCta` („Vyzkoušet ukázky“ / „Try the live examples“ / „Beispiele ausprobieren“), `examplesCtaShort` („Ukázky“ / „Examples“ / „Beispiele“), `examplesNote` („Bez registrace. Vymyšlená čísla.“ / „No sign-up. Made-up numbers.“ / „Ohne Registrierung. Erfundene Zahlen.“), `brokerCheck.examples`, `footer.examples`; přepsat `status` („Uzavřená beta.“, „Ukázky funkcí jsou otevřené všem.“ a ekvivalenty), `brokerCheck.betaNote`, FAQ odpovědi `a`/`aOpen` o vyzkoušení bez účtu (ukázky u funkcí, vymyšlená data). `LandingHero`, `LandingHeader`, `LandingFooter` (`${anchorBase}#funkce`), závěr ve `Welcome.jsx`, `BrokerCheck`, `BrokerList`: odkazy na `#funkce`, odstranit `onDemo` props a `handleDemoCtaClick`, import `DEMO_SESSION_SCOPE`. Při otevřených registracích: hlavní tlačítko registrace beze změny, sekundární textový odkaz „Vyzkoušet ukázky“ → `#funkce`. `FeatureList`/`MiniDemoSlot`/`miniDemoRegistry`: odstranit `demoHref`, `DEMO_HREFS` a odkaz pod ukázkou.
- [ ] **4. Analytika.** `eventContract.js`: odstranit čtyři `DEMO_*` události, jejich schémata, pole `entry_point`, `demo_page`, `demo_symbol`, `activation_path`, `distinct_demo_pages` a množiny `entryPoints`, `demoPages`, `demoSymbols`, `activationPaths`; z `sourceSurfaces` odstranit `"demo"`. Ponechat `sourceTypes` a `creationPaths` s `"demo"`. `Register.jsx`: `SOURCE_SURFACES` bez `demo`. Komentáře v `analyticsCopy.js`, `signupIntent.js`, `StockHeader.jsx`, `NavGroupsContext.js`, `demoPortfolio.js` upravit tak, aby nemluvily o veřejném `/demo` (žádná změna kódu).
- [ ] **5. SEO.** `publicPages.js`: z `DISALLOWED_PATHS` odstranit `"/demo"` (a komentář nad ním), popisy cs/en/de: „Vyzkoušejte živé demo.“ → „Vyzkoušejte interaktivní ukázky.“ / „Try the interactive examples.“ / „Probiere die interaktiven Beispiele aus.“. Sitemap obsahuje jen `/`, `/en/`, `/de/` (beze změny).
- [ ] **6. `DESIGN.md` §10.** Věta o CTA: zavřené registrace → primární tlačítko „Vyzkoušet ukázky“ na `#funkce`; žádná zmínka o `/demo`; odkaz pod ukázkami zrušen.
- [ ] **7. Ověření a commit.**
  - `rg -n "\"/demo|'/demo|href=\"/demo|isDemoPath|useDemoAnalytics|DEMO_SESSION_SCOPE|demo_started|demo_page_viewed|demo_stock_viewed|demo_activation_reached|DemoBootstrap|demoCopy" frontend/src` → jen `isRetiredDemoPath` v `routes.js`, `Root.jsx` a jejich testech.
  - `rg -n "createDemoPortfolio|DemoDataBanner" frontend/src` → stejné výsledky jako na `main` (onboardingové demo nedotčeno).
  - `cd frontend && npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`, `npm run audit:readability` zeleně; `node scripts/landing-bundle-guard.mjs dist --baseline scripts/landing-bundle-baseline.json` projde (smazáním se entry spíš zmenší).
  - `dist/sitemap.xml` a `dist/robots.txt` neobsahují `/demo`; `dist/prerendered/**/index.html` neobsahuje `href="/demo`.
  - Ruční kontrola cs/en/de na 360 px a 1280 px (`npx vite --mode edition-cloud --port 5184`): hlavní tlačítko posune na ukázky, nic nevede na prázdnou stránku.
  - Commit: `feat(landing)!: retire the public /demo, examples become the call to action`.

**Hotovo, když:** v kódu frontendu nezůstal veřejný demo strom ani odkaz na `/demo`, CTA vede na ukázky, kontrakt analytiky nemá demo události (onboardingové `"demo"` hodnoty zůstaly), testy a buildy obou edic zelené.

---

## S5: Přesměrování /demo na serveru (301) a úklid provozní dokumentace (vlna 3)

**Soubory (jiné neměnit):**
- Změnit: `backend/spa_serving.py`, `backend/tests/test_spa_seo.py`, `docs/operations/posthog-activation-analytics.md`, `docs/operations/activation-analytics-browser-check.md`, `docs/operations/readability-browser-check.md`
- Smazat: `docs/operations/public-demo-release-check.md`
- **Nesahat:** `backend/main.py` (redirect už posílá 301), `backend/routers/portfolios.py` (`/portfolios/demo` je onboardingové demo).

### Kroky

- [ ] **1. Testy (červeně)** v `backend/tests/test_spa_seo.py`:
  - parametrizovaně `demo`, `demo/`, `demo/allocation`, `demo/stock/MSFT` na hostu `portfyl.com`, na náhledovém hostu (`*.run.app`) a na `localhost` → `SpaTarget.redirect == "/"`; s `query="utm_source=x"` → `"/?utm_source=x"`; hlavičky na neveřejném hostu obsahují `X-Robots-Tag: noindex, nofollow`;
  - `demolition`, `demo.png`, `demos` → beze změny (app shell, resp. soubor);
  - na `app.portfyl.com` se `demo` chová jako dnes (app shell `noindex`, tracker si cestu vyřeší sám);
  - end-to-end přes existující `TestClient` vzor (`test_the_spa_fallback_route_applies_the_rules_end_to_end`): `GET /demo/allocation` s `Host: portfyl.com` a `follow_redirects=False` vrátí **301** a `Location: /`;
  - z parametrizace `test_every_other_route_gets_the_noindex_app_shell` odstranit `demo` a `demo/allocation`.
- [ ] **2. Implementace** v `spa_serving.py`: konstanta `RETIRED_DEMO_PREFIX = "demo"`, funkce `_is_retired_demo(full_path)` (`full_path == "demo"` nebo začíná `"demo/"`); v `resolve` hned po větvi `robots.txt` a jen pro `host != TRACKER_HOST`: `return SpaTarget(redirect="/" + (f"?{query}" if query else ""), headers=host_headers)`. Docstring modulu doplnit o „staré `/demo` a `/demo/*` → 301 na `/`“ a odebrat zmínku o demu v app shellu. Čisté funkce, žádné I/O ani DB (`def`, žádné `async`).
- [ ] **3. Dokumentace.**
  - `posthog-activation-analytics.md`: odstranit `demo_started`, `demo_page_viewed`, `demo_stock_viewed`, `demo_activation_reached`, `entry_point`, `source_surface=demo` a trychtýř přes demo; přidat `landing_minidemo_used` (`minidemo`, `language`; nejvýš jednou na ukázku za načtení stránky; jen po souhlasu) a doporučený přehled O3 (ukázky → `signup_cta_clicked` → `signup_started`). Uvést datum vyřazení dema 2026-11-18+ a že staré události v PostHog zůstávají jen historicky.
  - `activation-analytics-browser-check.md`: přepsat kroky z procházení `/demo` na kontrolu ukázek na `/`, `/en/`, `/de/` (souhlas přijmout → interakce s každou ukázkou → v PostHog 5 událostí `landing_minidemo_used`, druhá interakce nic; bez souhlasu nic).
  - `readability-browser-check.md`: odkaz na zrušené `/demo` nahradit ukázkami na úvodní stránce.
  - `public-demo-release-check.md` smazat (`git rm`); jeho roli přebírá `docs/operations/landing-minidemo-check.md` z S3.
- [ ] **4. Ověření a commit.** `cd backend && python -m pytest tests/test_spa_seo.py tests/test_spa_fallback.py -v` zeleně; `cd backend && python -m pytest tests/ --ignore=tests/postgres -q` zeleně (rychlá sada). `rg -n "/demo" docs/operations` → jen zmínky o přesměrování a historii. Commit: `feat(seo): 301 the retired /demo to the home page`.

**Hotovo, když:** `/demo` i `/demo/*` dostanou na veřejném i náhledovém hostu 301 na `/` (s query), nikdo nedostane 404 ani prázdnou stránku, dokumentace analytiky odpovídá kontraktu po S4.

---

## Integrační testy

Spustí se na integrační větvi po sloučení každé vlny (po vlně 1: S1+S2, po vlně 2: S3, po vlně 3: S4+S5), vždy po rebase na aktuální `main` a s vyřešením konfliktů lokálně:

1. Frontend, obě edice: `cd frontend && npm ci && npm test && npm run test:cloud`.
2. Buildy: `cd frontend && npm run build && npm run build:cloud` (prerender `/`, `/en/`, `/de/` bez chyby a bez inline skriptů).
3. Skripty: `cd frontend && node --test scripts/landing-bundle-guard.test.mjs scripts/measure-initial-bundle.test.mjs scripts/prerender.test.mjs scripts/audit-readability.test.mjs`.
4. Velikost a prerender: `cd frontend && node scripts/landing-bundle-guard.mjs dist --baseline scripts/landing-bundle-baseline.json` a `npm run measure:bundle` (porovnat se základem, limit +5 KiB gzip pro entry i chunk `Welcome`).
5. Čitelnost: `cd frontend && npm run audit:readability`.
6. Backend (po vlně 3): `cd backend && python -m pytest tests/ --ignore=tests/postgres -q`; PostgreSQL sada se nemění (žádná DB práce), spouštět ji není nutné.
7. Po vlně 3 navíc: `rg -n "href=\"/demo|'/demo'|\"/demo\"" frontend/src frontend/dist/prerendered` prázdné kromě `isRetiredDemoPath`; `frontend/dist/sitemap.xml` a `robots.txt` bez `/demo`; ruční prohlídka cs/en/de na 360 px a 1280 px; `curl -sI -H "Host: portfyl.com" http://127.0.0.1:<port>/demo/allocation` (lokální backend na vlastním portu, např. 8015, bez `alembic`) vrátí `301` a `Location: /`.

## Sekce (strojově)

```json
[
  {
    "id": "S1",
    "title": "Sdílené panely ukázek, ukázková data a refaktor stránek /demo",
    "wave": 1,
    "files": [
      "frontend/src/components/showcase/showcaseMath.js",
      "frontend/src/components/showcase/showcaseMath.test.js",
      "frontend/src/components/showcase/showcaseData.js",
      "frontend/src/components/showcase/showcaseData.test.js",
      "frontend/src/components/showcase/AllocationPanel.jsx",
      "frontend/src/components/showcase/StockValuationPanel.jsx",
      "frontend/src/components/showcase/PerformancePanel.jsx",
      "frontend/src/components/showcase/DividendsPanel.jsx",
      "frontend/src/components/showcase/PortfoliosPanel.jsx",
      "frontend/src/components/showcase/panels.test.jsx",
      "frontend/src/demo/pages/DemoAllocation.jsx",
      "frontend/src/demo/pages/DemoAnalytics.jsx",
      "frontend/src/demo/pages/DemoDividends.jsx",
      "frontend/src/demo/pages/DemoOverview.jsx",
      "frontend/src/demo/pages/DemoStock.jsx",
      "frontend/src/demo/pages/DemoAllocation.test.jsx",
      "frontend/src/demo/pages/DemoAnalytics.test.jsx",
      "frontend/src/demo/pages/DemoDividends.test.jsx",
      "frontend/src/demo/pages/DemoOverview.test.jsx",
      "frontend/src/demo/pages/DemoStock.test.jsx"
    ],
    "test_commands": [
      "cd frontend && npm test -- src/components/showcase src/demo",
      "cd frontend && npm test",
      "cd frontend && npm run test:cloud",
      "cd frontend && npm run audit:readability"
    ]
  },
  {
    "id": "S2",
    "title": "Rámeček mini ukázek na úvodní stránce, texty cs/en/de, analytika a hlídač balíčku",
    "wave": 1,
    "files": [
      "frontend/src/components/landing/MiniDemoSlot.jsx",
      "frontend/src/components/landing/MiniDemoSlot.test.jsx",
      "frontend/src/components/landing/miniDemoRegistry.js",
      "frontend/src/components/landing/useMiniDemoAnalytics.js",
      "frontend/src/components/landing/useMiniDemoAnalytics.test.jsx",
      "frontend/src/components/landing/FeatureList.test.jsx",
      "frontend/src/components/landing/minidemo/AppScope.jsx",
      "frontend/src/components/landing/minidemo/appClayScope.js",
      "frontend/src/components/landing/minidemo/appClayScope.test.js",
      "frontend/src/components/landing/minidemo/MiniAllocation.jsx",
      "frontend/src/components/landing/minidemo/MiniStock.jsx",
      "frontend/src/components/landing/minidemo/MiniPerformance.jsx",
      "frontend/src/components/landing/minidemo/MiniDividends.jsx",
      "frontend/src/components/landing/minidemo/MiniPortfolios.jsx",
      "frontend/scripts/landing-bundle-guard.mjs",
      "frontend/scripts/landing-bundle-guard.test.mjs",
      "frontend/scripts/landing-bundle-baseline.json",
      "frontend/src/components/landing/FeatureList.jsx",
      "frontend/src/pages/Welcome.jsx",
      "frontend/src/pages/Welcome.css",
      "frontend/src/pages/Welcome.test.jsx",
      "frontend/src/pages/welcomeCopy.js",
      "frontend/src/analytics/eventContract.js",
      "frontend/src/analytics/eventContract.test.js",
      "DESIGN.md"
    ],
    "test_commands": [
      "cd frontend && npm test -- src/components/landing src/pages/Welcome.test.jsx src/analytics/eventContract.test.js",
      "cd frontend && node --test scripts/landing-bundle-guard.test.mjs scripts/measure-initial-bundle.test.mjs scripts/prerender.test.mjs",
      "cd frontend && npm test",
      "cd frontend && npm run test:cloud",
      "cd frontend && npm run build",
      "cd frontend && npm run build:cloud",
      "cd frontend && node scripts/landing-bundle-guard.mjs dist --baseline scripts/landing-bundle-baseline.json"
    ]
  },
  {
    "id": "S3",
    "title": "Pět živých mini ukázek, ověření vzhledu, přístupnosti a velikosti",
    "wave": 2,
    "files": [
      "frontend/src/components/landing/minidemo/MiniAllocation.jsx",
      "frontend/src/components/landing/minidemo/MiniStock.jsx",
      "frontend/src/components/landing/minidemo/MiniPerformance.jsx",
      "frontend/src/components/landing/minidemo/MiniDividends.jsx",
      "frontend/src/components/landing/minidemo/MiniPortfolios.jsx",
      "frontend/src/pages/Welcome.css",
      "frontend/src/components/showcase/AllocationPanel.jsx",
      "frontend/src/components/showcase/StockValuationPanel.jsx",
      "frontend/src/components/showcase/PerformancePanel.jsx",
      "frontend/src/components/showcase/DividendsPanel.jsx",
      "frontend/src/components/showcase/PortfoliosPanel.jsx",
      "frontend/src/components/landing/minidemo/miniDemoLabels.js",
      "frontend/src/components/landing/minidemo/miniDemoLabels.test.js",
      "frontend/src/components/landing/minidemo/miniDemos.test.jsx",
      "docs/operations/landing-minidemo-check.md"
    ],
    "test_commands": [
      "cd frontend && npm test -- src/components/landing/minidemo src/components/showcase",
      "cd frontend && npm test",
      "cd frontend && npm run test:cloud",
      "cd frontend && npm run build",
      "cd frontend && npm run build:cloud",
      "cd frontend && node scripts/landing-bundle-guard.mjs dist --baseline scripts/landing-bundle-baseline.json",
      "cd frontend && npm run measure:bundle",
      "cd frontend && npm run audit:readability"
    ]
  },
  {
    "id": "S4",
    "title": "Smazání veřejného /demo ve frontendu, nové hlavní tlačítko a úklid analytiky",
    "wave": 3,
    "files": [
      "frontend/src/demo/DemoApp.jsx",
      "frontend/src/demo/DemoApp.test.jsx",
      "frontend/src/demo/DemoBootstrap.jsx",
      "frontend/src/demo/DemoDataContext.jsx",
      "frontend/src/demo/DemoShell.jsx",
      "frontend/src/demo/demoCopy.js",
      "frontend/src/demo/demoIsolation.test.jsx",
      "frontend/src/demo/demoRouteWalk.test.jsx",
      "frontend/src/demo/pages/DemoAllocation.jsx",
      "frontend/src/demo/pages/DemoAllocation.test.jsx",
      "frontend/src/demo/pages/DemoAnalytics.jsx",
      "frontend/src/demo/pages/DemoAnalytics.test.jsx",
      "frontend/src/demo/pages/DemoDividends.jsx",
      "frontend/src/demo/pages/DemoDividends.test.jsx",
      "frontend/src/demo/pages/DemoOverview.jsx",
      "frontend/src/demo/pages/DemoOverview.test.jsx",
      "frontend/src/demo/pages/DemoStock.jsx",
      "frontend/src/demo/pages/DemoStock.test.jsx",
      "frontend/src/analytics/useDemoAnalytics.js",
      "frontend/src/analytics/useDemoAnalytics.test.jsx",
      "frontend/src/demo/demoPortfolio.js",
      "frontend/src/Root.jsx",
      "frontend/src/Root.test.jsx",
      "frontend/src/lib/routes.js",
      "frontend/src/lib/routes.test.js",
      "frontend/src/pages/Welcome.jsx",
      "frontend/src/pages/Welcome.test.jsx",
      "frontend/src/pages/welcomeCopy.js",
      "frontend/src/components/landing/LandingHero.jsx",
      "frontend/src/components/landing/LandingHeader.jsx",
      "frontend/src/components/landing/LandingFooter.jsx",
      "frontend/src/components/landing/BrokerCheck.jsx",
      "frontend/src/components/landing/BrokerCheck.test.jsx",
      "frontend/src/components/landing/BrokerList.jsx",
      "frontend/src/components/landing/FeatureList.jsx",
      "frontend/src/components/landing/FeatureList.test.jsx",
      "frontend/src/components/landing/MiniDemoSlot.jsx",
      "frontend/src/components/landing/MiniDemoSlot.test.jsx",
      "frontend/src/components/landing/miniDemoRegistry.js",
      "frontend/src/analytics/eventContract.js",
      "frontend/src/analytics/eventContract.test.js",
      "frontend/src/analytics/AnalyticsProvider.test.jsx",
      "frontend/src/analytics/analyticsClient.test.js",
      "frontend/src/analytics/analyticsCopy.js",
      "frontend/src/pages/Register.jsx",
      "frontend/src/pages/Register.intent.test.jsx",
      "frontend/src/pages/AuthPages.test.jsx",
      "frontend/src/lib/signupIntent.js",
      "frontend/src/seo/publicPages.js",
      "frontend/src/seo/publicPages.test.js",
      "frontend/src/components/stock/StockHeader.jsx",
      "frontend/src/components/layout/NavGroupsContext.js",
      "DESIGN.md"
    ],
    "test_commands": [
      "cd frontend && npm test -- src/pages src/components/landing src/analytics src/lib src/seo src/Root.test.jsx",
      "cd frontend && npm test",
      "cd frontend && npm run test:cloud",
      "cd frontend && npm run build",
      "cd frontend && npm run build:cloud",
      "cd frontend && node scripts/landing-bundle-guard.mjs dist --baseline scripts/landing-bundle-baseline.json",
      "cd frontend && npm run audit:readability"
    ]
  },
  {
    "id": "S5",
    "title": "Přesměrování /demo na serveru (301) a úklid provozní dokumentace",
    "wave": 3,
    "files": [
      "backend/spa_serving.py",
      "backend/tests/test_spa_seo.py",
      "docs/operations/posthog-activation-analytics.md",
      "docs/operations/activation-analytics-browser-check.md",
      "docs/operations/readability-browser-check.md",
      "docs/operations/public-demo-release-check.md"
    ],
    "test_commands": [
      "cd backend && python -m pytest tests/test_spa_seo.py tests/test_spa_fallback.py -v",
      "cd backend && python -m pytest tests/ --ignore=tests/postgres -q"
    ]
  }
]
```
