# Malá interaktivní dema na úvodní stránce – implementační plán

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na veřejné úvodní stránce (portfyl.com, `/`, `/en/`, `/de/`) přidat dvě malé interaktivní ukázky nad vymyšleným demo portfoliem: (1) rozložení portfolia s přepínačem Pozice / Sektory / Měny, (2) dividendy po měsících. Ukázky se objeví v `FeatureList` místo chybějícího screenshotu.

**Architecture:** Statická „schránka“ `MiniDemoSlot` je v chunku `Welcome` a vykreslí na serveru i při hydrataci stejný statický text (štítek „Ukázkové portfolio“, věta, upozornění, odkaz na `/demo`). Až po připojení v prohlížeči a po doskrolování (IntersectionObserver) načte přes `React.lazy` samostatný chunk `MiniAllocation` / `MiniDividends`. Ten bere data z `src/demo/demoPortfolio.js` přes čistý modul `miniDemoData.js` a kreslí je CSS pruhy (bez Recharts). Texty jsou ve `welcomeCopy.js` (cs/en/de), čísla se formátují ručně (bez `Intl`), stejně jako v `lib/planPrices.js`.

**Tech Stack:** React 18 (`lazy`, `Suspense`, `hydrateRoot`), Vite 6 (dynamický import → vlastní chunk), Vitest + Testing Library (jsdom), node:test pro skripty, čisté CSS s tokeny Clay.

**Spec:** schválený rozsah od hodnotitele (workflow `portfyl-idea`, 2026-11-18). Je přepsaný v sekci „Global Constraints“. Související dokumenty: `DESIGN.md` §10 (veřejná úvodní stránka), `docs/superpowers/plans/2026-11-15-portfyl-landing-redesign-free-trial.md`, `docs/superpowers/plans/2026-09-19-portfyl-public-demo.md` (pevná data dema).

## Global Constraints

- Jen **2** ukázky: `allocation` (Pozice / Sektory / Měny, vodorovné CSS pruhy) a `dividends` (sloupce po měsících, po najetí nebo klepnutí se ukáže částka). Nic pro detail akcie, P/E, analytiku ani import.
- Data jen z `frontend/src/demo/demoPortfolio.js` (`demoPortfolio`). Ten soubor ani `validateDemoPortfolio.js` se **nemění**.
- Ukázka nahrazuje **chybějící** obrázek dané funkce (`LANDING_IMAGES[key] === null`). Existující obrázek má vždy přednost. Mapa: `sectors → allocation`, `dividends → dividends`.
- Línné načtení: `React.lazy` + IntersectionObserver (`rootMargin: "200px 0px"`). Do statického grafu chunku `src/pages/Welcome.jsx` se **nesmí** dostat `MiniAllocation`, `MiniDividends`, `miniDemoData`, `demoPortfolio` ani `recharts`.
- Prerender a hydratace: server i první render v klientu vykreslí jen statický obsah. Nic se při renderu nedotýká `window`, `navigator` ani úložiště (vzor `BrokerCheck.jsx`). Do statického HTML nejdou žádné hodnoty z dat (procenta, částky).
- Texty jen ve `welcomeCopy.js`, blok `miniDemos`, pro `cs`, `en`, `de` (přesné znění je v Tasku S1). Nevkládat `DemoAllocation` / `DemoDividends` (jsou napevno anglicky a používají třídy aplikace).
- Pod každou ukázkou je odkaz „Prohlédnout celé demo“ na `/demo`. Zachytí se stejně jako dnešní `onDemo`, `entry_point = "landing_minidemo"`.
- Vzhled podle `DESIGN.md` §10: plochý panel (hairline `--w-line`, **bez stínu**). Jediný zvýšený prvek v řádku zůstává screenshot. Barvy jsou jen z tokenů (`--chart-1`, `--chart-2`, `--ink`, `--muted`, `--w-line`), žádné hex barvy a písmo nejméně 12px.
- Přístupnost: nativní `<button type="button">`, přepínač s `aria-pressed`, skrytá textová tabulka pro čtečky (jako v `DemoAllocation`), pruhy mají `aria-hidden="true"` a odečet `aria-live="polite"`.
- Na ukázce je vždy vidět štítek „Ukázkové portfolio“ a věta „Vymyšlená čísla, ne skutečné výnosy.“
- Analytika: nová událost `landing_minidemo_used` `{ demo: "allocation"|"dividends", language }`, nejvýš jednou na ukázku a načtení stránky, jen po skutečném kliknutí (ne po pouhém najetí myší).
- Bez backendu, bez DB, bez migrací, bez změn `package.json`/lockfilů, `App.jsx` ani `api.js`. Tax Report / Screener se nikde nezmiňují.
- Rozpočet velikosti (gzip, `node scripts/measure-initial-bundle.mjs dist <entry>` po `npm run build:cloud`): obě entry, `src/pages/Welcome.jsx` i `index.html`, mají **stejný rozpočet**. `initial_combined_gzip_bytes` smí u každé z nich narůst celkem (S1 + S3) nejvýš o **5 KiB**: S1 nejvýš o 2,5 KiB a S3 nejvýš o 2,5 KiB, u každé entry zvlášť.
  - Proč i `index.html`: `welcomeCopy.js` importuje také `analytics/analyticsCopy.js` (texty souhlasu s analytikou), který je v hlavním balíčku. Celý text úvodní stránky proto leží v `index-*.js`, ne v chunku Welcome. Nový blok `miniDemos` (cs, en, de) tak zvětší `index.html` zhruba o 1,5 až 2 KiB gzip, a to je v pořádku. Texty zůstávají ve `welcomeCopy.js`, jak říká schválený rozsah. Samostatný modul s texty se **nezavádí**.
  - `index.html` je ve statickém grafu Welcome, takže nárůst textů se objeví v obou číslech, ale do rozpočtu každé entry se počítá jen jednou (5 KiB platí pro každou entry samostatně, nesčítají se).

## Review Focus

1. **Chunk ukázky se nenačte** (offline, nový deploy vyměnil hashe): stránka nesmí spadnout a zůstane statický text. Test S3 `keeps the static text when the demo chunk fails to load`.
2. **Hydratace prerenderovaného HTML**: žádné varování o neshodě a ukázka se připojí až po viditelnosti. Test S3 `hydrates the prerendered markup without a mismatch`.
3. **Telefon 360px a dlouhé německé názvy** („Informationstechnologie“, 12 měsíčních sloupců): stránka se nesmí posouvat do strany a sloupce musí mít aspoň 24px. Řeší to CSS v S2 (`minmax(24px, 1fr)`, vnitřní `overflow-x: auto`, `overflow-wrap: anywhere`) a ruční kontrola v S3, krok 9.
4. **Návštěvník bez souhlasu s analytikou**: nic se neodešle. Test S3 `sends nothing before analytics consent`.
5. **Rychlé opakované přepínání**: odejde jen jedna událost na ukázku. Test S3 `captures landing_minidemo_used once per demo`.

Známé omezení dat (vědomě se neřeší): demo portfolio je celé v USD, takže pohled **Měny** ukazuje jeden pruh `USD 100 %`. Pohled Sektory má stejné váhy jako Pozice (každá pozice je v jiném sektoru). Je to pravdivé a data se měnit nesmí.

---

## Paralelní práce (izolace)

- Každá sekce pracuje ve **vlastním git worktree na vlastní větvi** odvozené od `feature/landing-mini-demos` (např. `feature/landing-mini-demos-s1`). Do `feature/landing-mini-demos` se slučuje až po zelených testech sekce. Nikdy se necommituje na `main` a nic se nepushuje.
- Žádná sekce nespouští `alembic`, backend ani sdílenou databázi. Dev server spouští jen S3 (krok 9), a to na vlastním portu **5181**, nikdy na 5173.
- `npm run build:cloud` zapisuje do `frontend/dist` a `frontend/.prerender` **vlastního** worktree, takže se sekce neperou.
- Hotspot „překlady“ (`welcomeCopy.js`) vlastní jen S1. Vlna 1 = S1 a S2 (disjunktní soubory), vlna 2 = S3 (potřebuje obě sloučené).

---

### Task S1: Texty, analytický kontrakt a měření balíčku (vlna 1)

**Files:**
- Modify: `frontend/src/pages/welcomeCopy.js` (blok `miniDemos` v `cs`, `en`, `de` + komentář o tvaru nahoře)
- Create: `frontend/src/pages/welcomeCopy.test.js`
- Modify: `frontend/src/analytics/eventContract.js`
- Modify: `frontend/src/analytics/eventContract.test.js`
- Modify: `frontend/scripts/measure-initial-bundle.mjs`
- Modify: `frontend/scripts/measure-initial-bundle.test.mjs`
- Modify: `docs/operations/posthog-activation-analytics.md` (seznam povolených událostí a jejich počet)

**Interfaces:**
- Produces: `COPY[lang].miniDemos` přesně v tomto tvaru:
  ```
  miniDemos: {
    badge, disclaimer, fullDemo,
    allocation: { label, staticText, toggleLabel, views: { positions, sectors, currencies },
                  tableCaption, columns: [name, weight], sectors: { <anglický název sektoru>: <překlad> } },
    dividends:  { label, staticText, hint, total /* obsahuje "{amount}" */, tableCaption,
                  columns: [month, amount], months: [12 zkratek], monthsLong: [12 názvů] },
  }
  ```
- Produces: `ANALYTICS_EVENTS.LANDING_MINIDEMO_USED === "landing_minidemo_used"` (poslední položka objektu) se schématem `["demo", "language"]`. Pole `demo` přijímá jen `allocation` a `dividends`. `entry_point` nově přijímá i `"landing_minidemo"`.
- Produces: `measureInitialBundle(directory, entry = "index.html")` a CLI `node scripts/measure-initial-bundle.mjs <dist> [entry]`. Pole `entry` ve výstupu odpovídá argumentu.

Přesné texty:

| klíč | cs | en | de |
|---|---|---|---|
| badge | Ukázkové portfolio | Sample portfolio | Beispielportfolio |
| disclaimer | Vymyšlená čísla, ne skutečné výnosy. | Made-up numbers, not real returns. | Erfundene Zahlen, keine echten Renditen. |
| fullDemo | Prohlédnout celé demo | Explore the full demo | Ganze Demo ansehen |
| allocation.label | Ukázka: rozložení portfolia | Preview: portfolio allocation | Vorschau: Portfolio-Aufteilung |
| allocation.staticText | Ukázkové portfolio s deseti pozicemi. V prohlížeči si ho přepnete podle pozic, sektorů a měn. | A sample portfolio with ten positions. In your browser you can switch it between positions, sectors and currencies. | Ein Beispielportfolio mit zehn Positionen. Im Browser schaltest du zwischen Positionen, Branchen und Währungen um. |
| allocation.toggleLabel | Rozložení podle | Allocation by | Aufteilung nach |
| allocation.views | Pozice / Sektory / Měny | Positions / Sectors / Currencies | Positionen / Branchen / Währungen |
| allocation.tableCaption | Váhy v ukázkovém portfoliu | Weights in the sample portfolio | Gewichte im Beispielportfolio |
| allocation.columns | Název, Váha | Name, Weight | Name, Gewicht |
| dividends.label | Ukázka: dividendy po měsících | Preview: dividends by month | Vorschau: Dividenden nach Monaten |
| dividends.staticText | Dividendy ukázkového portfolia za posledních 12 měsíců. V prohlížeči uvidíte částku za každý měsíc. | Dividends of the sample portfolio over the last 12 months. In your browser you see the amount for each month. | Dividenden des Beispielportfolios der letzten 12 Monate. Im Browser siehst du den Betrag für jeden Monat. |
| dividends.hint | Najeďte na měsíc nebo na něj klepněte. | Hover over a month or tap it. | Fahre über einen Monat oder tippe darauf. |
| dividends.total | Za posledních 12 měsíců: {amount} | Last 12 months: {amount} | Letzte 12 Monate: {amount} |
| dividends.tableCaption | Dividendy ukázkového portfolia po měsících | Sample portfolio dividends by month | Dividenden des Beispielportfolios nach Monaten |
| dividends.columns | Měsíc, Částka | Month, Amount | Monat, Betrag |

`allocation.sectors` (klíče jsou přesně hodnoty `sector` z `HOLDING_SEEDS`):

| klíč | cs | en | de |
|---|---|---|---|
| Diversified ETF | Široký ETF | Diversified ETF | Breiter ETF |
| Information Technology | Informační technologie | Information technology | Informationstechnologie |
| Financials | Finance | Financials | Finanzen |
| Health Care | Zdravotnictví | Health care | Gesundheitswesen |
| Energy | Energetika | Energy | Energie |
| Consumer Staples | Základní spotřeba | Consumer staples | Basiskonsumgüter |
| Consumer Discretionary | Zbytná spotřeba | Consumer discretionary | Zyklischer Konsum |
| Industrials | Průmysl | Industrials | Industrie |
| Utilities | Veřejné služby | Utilities | Versorger |
| Real Estate | Nemovitosti | Real estate | Immobilien |

`dividends.months` / `monthsLong`:
- cs: `led úno bře dub kvě čvn čvc srp zář říj lis pro` / `leden únor březen duben květen červen červenec srpen září říjen listopad prosinec`
- en: `Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec` / `January … December`
- de: `Jan Feb Mär Apr Mai Jun Jul Aug Sep Okt Nov Dez` / `Januar Februar März April Mai Juni Juli August September Oktober November Dezember`

- [ ] **Step 1: Napsat padající test skriptu.** V `measure-initial-bundle.test.mjs` přidat `test('measures a lazily loaded page from its own manifest entry', …)`. Ten s dočasným adresářem (`mkdtempSync`) zapíše `.vite/manifest.json` s položkami `index.html` a `src/pages/Welcome.jsx` (s jedním `imports` a jedním `dynamicImports`) a malé soubory. Pak ověří, že `measureInitialBundle(dir, 'src/pages/Welcome.jsx')` vrátí `entry === 'src/pages/Welcome.jsx'`, v `assets` jsou jen soubory statického grafu Welcome a `excluded_dynamic_imports` obsahuje dynamickou položku.
- [ ] **Step 2: Spustit test a ověřit, že padá.** Spustit `cd frontend && node --test scripts/measure-initial-bundle.test.mjs`. Očekávaný výsledek: FAIL (`entry` je `index.html`).
- [ ] **Step 3: Upravit skript.** `measureInitialBundle(directory, entry = 'index.html')` předá `entry` do `collectInitialAssets` i do výstupu. CLI čte `process.argv[3]` jako entry. `package.json` se **nemění**.
- [ ] **Step 4: Ověřit, že test projde.** Stejný příkaz. Očekávaný výsledek: PASS.
- [ ] **Step 5: Změřit základ před změnou textů.** Spustit `cd frontend && npm run build:cloud && node scripts/measure-initial-bundle.mjs dist src/pages/Welcome.jsx && node scripts/measure-initial-bundle.mjs dist`. Obě čísla `initial_combined_gzip_bytes` si zapsat (půjdou do těla commitu).
- [ ] **Step 6: Napsat padající testy kontraktu** v `eventContract.test.js`:
  - na konec `validEvents` přidat `["landing_minidemo_used", { demo: "allocation", language: "cs" }]` (test pořadí jmen to pak vynutí),
  - `it("accepts the mini demo entry point and both demos, and rejects anything else", …)`: `sanitizeEvent("demo_started", { language: "de", entry_point: "landing_minidemo" }, { strict: true })` projde. `sanitizeEvent("landing_minidemo_used", { demo: "dividends", language: "en" }, { strict: true }).properties` je `{ demo: "dividends", language: "en" }`. `{ demo: "stock", language: "cs" }`, `{ demo: "allocation", language: "pl" }` a `{ demo: "allocation", language: "cs", view: "sectors" }` vyhodí `TypeError`.
- [ ] **Step 7: Spustit test a ověřit, že padá.** Spustit `cd frontend && npx vitest run --mode edition-local src/analytics/eventContract.test.js`. Očekávaný výsledek: FAIL.
- [ ] **Step 8: Upravit `eventContract.js`.** `LANDING_MINIDEMO_USED` jde na konec `ANALYTICS_EVENTS`. Přidat `const miniDemos = new Set(["allocation", "dividends"])`, pole `demo` a schéma `["demo", "language"]`. Do `entryPoints` přidat `"landing_minidemo"`. Zakázaná slova testu (`holdings`, `amount`…) se ve zdroji nesmí objevit.
- [ ] **Step 9: Ověřit, že test projde.** Stejný příkaz. Očekávaný výsledek: PASS.
- [ ] **Step 10: Napsat padající `welcomeCopy.test.js`** (importuje `COPY`, `LANGUAGES` a `HOLDING_SEEDS` z `../demo/demoPortfolio`):
  - `it("gives every language the same miniDemos keys", …)`: rekurzivní seznam klíčů `COPY[code].miniDemos` (pole se porovnávají délkou) je pro `cs`, `en` a `de` stejný,
  - `it.each(["cs","en","de"])("translates every demo sector in %s", …)`: pro každou `seed.sector` platí, že `COPY[code].miniDemos.allocation.sectors[seed.sector]` je neprázdný řetězec,
  - `it("has twelve short and long month names and an {amount} slot", …)`,
  - `it("keeps the full-demo link text distinct from the other demo links", …)`: `fullDemo` se v každém jazyce liší od `demoCta`, `demoCtaShort`, `demoLink` i `brokerCheck.demo`,
  - `it("shows the sample-portfolio badge and disclaimer in every language", …)`: `cs.miniDemos.badge === "Ukázkové portfolio"`, `en…badge === "Sample portfolio"`, `de…badge === "Beispielportfolio"`.
- [ ] **Step 11: Spustit test a ověřit, že padá.** Spustit `cd frontend && npx vitest run --mode edition-local src/pages/welcomeCopy.test.js`. Očekávaný výsledek: FAIL.
- [ ] **Step 12: Doplnit `miniDemos` do `cs`, `en`, `de`** přesně podle tabulek výš. Do komentáře „Shape of one language“ přidat řádek o `miniDemos`.
- [ ] **Step 13: Ověřit testy a celou sadu.** Spustit `cd frontend && npx vitest run --mode edition-local src/pages/welcomeCopy.test.js src/pages/Welcome.test.jsx src/analytics && npm test && npm run test:cloud`. Očekávaný výsledek: vše PASS (test zakázaných slov ve `Welcome.test.jsx` hlídá i nový blok).
- [ ] **Step 14: Změřit znovu.** Stejné příkazy jako v kroku 5. Nárůst smí být nejvýš 2,5 KiB pro entry `src/pages/Welcome.jsx` a nejvýš 2,5 KiB pro entry `index.html` (každá zvlášť). Očekává se, že obě čísla narostou zhruba stejně (asi 1,5 až 2 KiB), protože texty jsou v hlavním chunku `index-*.js` (viz Global Constraints).
- [ ] **Step 15: Upravit dokumentaci.** V `docs/operations/posthog-activation-analytics.md` doplnit do seznamu povolených událostí `landing_minidemo_used` (vlastnosti `demo`, `language`) a hodnotu `entry_point` `landing_minidemo`. Počet v nadpisu opravit podle skutečného počtu v `ANALYTICS_EVENTS`.
- [ ] **Step 16: Commitnout** soubory z výčtu se zprávou `feat(landing): texty a analytika pro malá dema na úvodní stránce`. Do těla commitu dát naměřená čísla `před → po` pro obě entry.

**Hotovo, když:** všechny čtyři testované soubory jsou zelené, `npm test` i `npm run test:cloud` projdou, nárůst velikosti je u obou entry nejvýš 2,5 KiB a čísla `před → po` pro obě entry jsou v těle commitu.

---

### Task S2: Data, interaktivní komponenty a styly ukázek (vlna 1)

**Files:**
- Create: `frontend/src/components/landing/miniDemoData.js`
- Create: `frontend/src/components/landing/miniDemoData.test.js`
- Create: `frontend/src/components/landing/MiniAllocation.jsx`
- Create: `frontend/src/components/landing/MiniAllocation.test.jsx`
- Create: `frontend/src/components/landing/MiniDividends.jsx`
- Create: `frontend/src/components/landing/MiniDividends.test.jsx`
- Create: `frontend/src/components/landing/miniDemos.css`
- Create: `frontend/src/components/landing/miniDemos.css.test.js`

**Interfaces:**
- Consumes: `demoPortfolio` (`holdings[].{symbol, sector, currency, weight}`, `dividends[].{date, amount}`, `asOf`) z `src/demo/demoPortfolio.js`. Tvar `COPY[lang].miniDemos` je popsaný v S1. S1 ještě není sloučený, proto testy S2 používají **vlastní fixturu** se stejným tvarem a s českými texty z tabulky S1.
- Produces (`miniDemoData.js`):
  - `allocationRows(view: "positions"|"sectors"|"currencies", portfolio = demoPortfolio) → Array<{ key: string, weight: number }>`. Řazení: váha sestupně, při shodě `key` vzestupně. `key` je ticker, anglický sektor nebo kód měny.
  - `monthlyDividends(portfolio = demoPortfolio) → Array<{ year: number, month: number /*0–11*/, amount: number }>`. Vrací přesně 12 měsíců končících měsícem `asOf`, chybějící měsíce mají `amount: 0`.
  - `formatDemoAmount(n: number, language: "cs"|"en"|"de") → string` (USD, celé dolary) a `formatDemoPercent(n: number, language) → string` (nejvýš 1 desetinné místo). Formát se staví ručně, bez `Intl`, mezery jsou nezlomitelné (` `).
- Produces (komponenty, `export default`):
  - `MiniAllocation({ copy, language, onUse })`, kde `copy` je celý blok `miniDemos`,
  - `MiniDividends({ copy, language, onUse })`.
  - Kořen obou má třídu `welcome-minidemo-live`. `onUse()` (bez argumentů) se volá při každém skutečném použití: u rozložení při změně pohledu, u dividend při kliknutí nebo klepnutí na měsíc. Najetí myší ani fokus `onUse` **nevolají**. Komponenty samy nic neodesílají a neimportují analytiku.
- Produces (`miniDemos.css`): třídy `welcome-minidemo`, `welcome-minidemo-badge`, `welcome-minidemo-static`, `welcome-minidemo-note`, `welcome-minidemo-live`, `welcome-minidemo-toggle`, `welcome-minidemo-bars`, `welcome-minidemo-bar`, `welcome-minidemo-months`, `welcome-minidemo-month`, `welcome-minidemo-readout`, `welcome-minidemo-sr` (vizuálně skryté) a výšky `.welcome-minidemo[data-demo="allocation"]` / `[data-demo="dividends"]`. Soubor importuje až `MiniDemoSlot` v S3, komponenty S2 ho **neimportují**.

- [ ] **Step 1: Napsat padající `miniDemoData.test.js`:**
  - `allocationRows("positions")` má délku 10, první je `{ key: "VUAA", weight: 18 }`, poslední `{ key: "PLD", weight: 7 }`, součet vah je 100 a `JNJ` je před `JPM` (obě 10),
  - `allocationRows("sectors")[0]` je `{ key: "Diversified ETF", weight: 18 }` a délka je 10,
  - `allocationRows("currencies")` je `[{ key: "USD", weight: 100 }]`,
  - `monthlyDividends()` má délku 12. První je `{ year: 2025, month: 9, amount: 0 }`, poslední `{ year: 2026, month: 8, amount: 355 }`. Nenulové jsou indexy `[2, 5, 8, 11]` (12/2025, 3, 6, 9/2026) a součet je 1420,
  - `formatDemoAmount(1420, "en") === "$1,420"`, `formatDemoAmount(1420, "cs") === "1 420 $"`, `formatDemoAmount(1420, "de") === "1.420 $"`, `formatDemoAmount(355, "cs") === "355 $"`,
  - `formatDemoPercent(18, "en") === "18%"`, `formatDemoPercent(18, "cs") === "18 %"`, `formatDemoPercent(12.5, "de") === "12,5 %"`, `formatDemoPercent(12.5, "en") === "12.5%"`, `formatDemoPercent(100, "cs") === "100 %"`.
- [ ] **Step 2: Spustit test a ověřit, že padá.** Spustit `cd frontend && npx vitest run --mode edition-local src/components/landing/miniDemoData.test.js`. Očekávaný výsledek: FAIL (modul neexistuje).
- [ ] **Step 3: Implementovat `miniDemoData.js`.** Měsíce se počítají z řetězců `YYYY-MM` (`asOf.slice(0, 7)`), ne přes lokální `Date`, aby výsledek nezávisel na časovém pásmu.
- [ ] **Step 4: Ověřit, že test projde.** Stejný příkaz. Očekávaný výsledek: PASS.
- [ ] **Step 5: Napsat padající `MiniAllocation.test.jsx`** (fixtura `copy` = český blok `miniDemos` z S1):
  - `it("starts on positions with ten weighted rows and a pressed toggle", …)`: tři tlačítka ve skupině `role="group"` s `aria-label = copy.allocation.toggleLabel`, „Pozice“ má `aria-pressed="true"` a ostatní `"false"`. Skrytá tabulka (`getByRole("table", { name: copy.allocation.tableCaption })`) má 10 řádků těla a první řádek je `VUAA` / `18 %`,
  - `it("switches to translated sectors and calls onUse", …)`: klik na „Sektory“ přepne `aria-pressed`, zobrazí se „Informační technologie“ a `onUse` je volán jednou,
  - `it("shows one USD row under currencies", …)`: tabulka má jeden řádek `USD` / `100 %`,
  - `it("does not call onUse on first render or when the pressed view is clicked again", …)`,
  - `it("hides the bars from screen readers and keeps native buttons", …)`: kontejner `.welcome-minidemo-bars` má `aria-hidden="true"` a tlačítka mají `type="button"`.
- [ ] **Step 6: Spustit test a ověřit, že padá.** Spustit `cd frontend && npx vitest run --mode edition-local src/components/landing/MiniAllocation.test.jsx`. Očekávaný výsledek: FAIL.
- [ ] **Step 7: Implementovat `MiniAllocation.jsx`.** Řádek pruhu tvoří popisek, pruh se `style={{ width: \`${weight / maxWeight * 100}%\` }}` a hodnota `formatDemoPercent`. Sektor se překládá přes `copy.allocation.sectors[key] ?? key`.
- [ ] **Step 8: Ověřit, že test projde.** Stejný příkaz. Očekávaný výsledek: PASS.
- [ ] **Step 9: Napsat padající `MiniDividends.test.jsx`** (stejná fixtura):
  - `it("renders twelve month buttons labelled with month, year and amount", …)`: `getByRole("button", { name: "prosinec 2025: 355 $" })` existuje, `říjen 2025: 0 $` také a tlačítek je celkem 12,
  - `it("shows the twelve-month total until a month is chosen", …)`: odečet (`.welcome-minidemo-readout`, `aria-live="polite"`) zobrazuje `Za posledních 12 měsíců: 1 420 $`,
  - `it("shows the month amount on hover and focus without calling onUse", …)`: po `fireEvent.mouseEnter` na prosinec ukazuje odečet `prosinec 2025: 355 $` a tlačítko má `aria-pressed="true"`. Totéž platí po `fireEvent.focus` na březen. `onUse` volán není,
  - `it("calls onUse when a month is clicked or tapped", …)`,
  - `it("offers a screen-reader table with twelve rows", …)`: tabulka `copy.dividends.tableCaption`, sloupce `copy.dividends.columns` a 12 řádků těla,
  - `it("shows the hint text", …)`.
- [ ] **Step 10: Spustit test a ověřit, že padá.** Spustit `cd frontend && npx vitest run --mode edition-local src/components/landing/MiniDividends.test.jsx`. Očekávaný výsledek: FAIL.
- [ ] **Step 11: Implementovat `MiniDividends.jsx`.** Sloupec je `<button type="button" aria-pressed aria-label="{monthsLong[m]} {year}: {částka}">` s vnitřní výplní, jejíž výška je `amount / max * 100 %`. Nulový měsíc má viditelný 2px pahýl. Pod sloupcem je zkratka `months[m]`. `mouseLeave` výběr neruší (kvůli dotyku).
- [ ] **Step 12: Ověřit, že test projde.** Stejný příkaz. Očekávaný výsledek: PASS.
- [ ] **Step 13: Napsat padající `miniDemos.css.test.js`** (čtení souboru přes `sourcePath` jako ve `Welcome.test.jsx`):
  - `it("holds no hex color", …)`: `css.match(/#[0-9a-fA-F]{3,8}\b/g)` je `null`,
  - `it("keeps every font-size at or above 12px", …)` (stejný regex jako ve `Welcome.test.jsx`),
  - `it("draws no shadow: the screenshot stays the only raised object", …)`: CSS neobsahuje `box-shadow`,
  - `it("keeps month columns at least 24px wide", …)`: CSS obsahuje `minmax(24px, 1fr)`.
- [ ] **Step 14: Spustit test a ověřit, že padá.** Spustit `cd frontend && npx vitest run --mode edition-local src/components/landing/miniDemos.css.test.js`. Očekávaný výsledek: FAIL.
- [ ] **Step 15: Napsat `miniDemos.css`.** Pravidla:
  - panel: `border: 1px solid var(--w-line)`, radius 16px (12px pod 860px), padding 20px, bez stínu,
  - pruhy: `var(--chart-1)`, vybraný měsíc `var(--chart-2)`,
  - stisknuté tlačítko přepínače: `border-color: var(--ink)` a tučnější písmo (nepoužívat `--brand`, ten patří tlačítku, fokusu a odkazům),
  - tlačítka mají nejméně 44px výšky, `.welcome-minidemo-months` je `grid-template-columns: repeat(12, minmax(24px, 1fr)); overflow-x: auto`, popisky mají `overflow-wrap: anywhere`,
  - `min-height` panelu podle `data-demo`, aby výměna statického textu za ukázku neposunula stránku,
  - `.welcome-minidemo-sr` je standardní visually-hidden.
- [ ] **Step 16: Ověřit testy S2 a celou sadu.** Spustit `cd frontend && npx vitest run --mode edition-local src/components/landing && npm test && npm run test:cloud`. Očekávaný výsledek: PASS.
- [ ] **Step 17: Commitnout** soubory z výčtu se zprávou `feat(landing): data a interaktivní komponenty malých dem`.

**Hotovo, když:** čtyři nové testovací soubory jsou zelené, `npm test` i `npm run test:cloud` projdou a žádná komponenta S2 neimportuje analytiku, CSS, `welcomeCopy` ani `recharts`.

---

### Task S3: Schránka s líným načtením, zapojení do úvodní stránky a DESIGN.md (vlna 2)

**Files:**
- Create: `frontend/src/components/landing/MiniDemoSlot.jsx`
- Create: `frontend/src/components/landing/MiniDemoSlot.test.jsx`
- Modify: `frontend/src/components/landing/FeatureList.jsx`
- Create: `frontend/src/components/landing/FeatureList.test.jsx`
- Modify: `frontend/src/pages/Welcome.jsx` (jen řádek s `<FeatureList …/>`)
- Modify: `frontend/src/pages/Welcome.test.jsx`
- Modify: `DESIGN.md` (§10)

**Interfaces:**
- Consumes: z S1 `COPY[lang].miniDemos`, `ANALYTICS_EVENTS.LANDING_MINIDEMO_USED` a `entry_point` `"landing_minidemo"`. Z S2 default exporty `MiniAllocation` / `MiniDividends` (`{ copy, language, onUse }`) a `./miniDemos.css`. Dále `useOptionalAnalytics()` (`capture`) z `analytics/AnalyticsProvider` a `LANDING_IMAGES`.
- Produces:
  - `export const MINI_DEMO_FOR_IMAGE = Object.freeze({ sectors: "allocation", dividends: "dividends" })`,
  - `export default function MiniDemoSlot({ demo, copy, language, onDemo, loader })`. `copy` je blok `miniDemos`. `loader` je volitelný testovací vstup (`() => Promise<{ default: Component }>`), jinak se použije `LOADERS[demo]` = `() => import("./MiniAllocation")` nebo `() => import("./MiniDividends")`,
  - `FeatureList({ copy, language, onDemo })`.

Markup schránky (statický stav, stejný na serveru i v klientu):
`<div className="welcome-minidemo" data-demo={demo} role="group" aria-label={copy[demo].label}>`, uvnitř `<p className="welcome-minidemo-badge">{copy.badge}</p>`, tělo `<p className="welcome-minidemo-static">{copy[demo].staticText}</p>`, `<p className="welcome-minidemo-note">{copy.disclaimer}</p>` a `<a className="welcome-textlink" href="/demo" onClick={onDemo}>{copy.fullDemo}</a>`. V živém stavu se nahradí jen tělo, a to `<Suspense fallback={statické tělo}>` uvnitř chybové hranice (třída s `getDerivedStateFromError`), jejíž náhradou je opět statické tělo. **Žádný `h3`** (test ve `Welcome.test.jsx` počítá `#funkce h3` podle počtu funkcí) a **žádný `<img>`**.

- [ ] **Step 1: Změřit základ.** Spustit `cd frontend && npm run build:cloud && node scripts/measure-initial-bundle.mjs dist src/pages/Welcome.jsx && node scripts/measure-initial-bundle.mjs dist` a čísla si zapsat. Základ S1 je v těle jeho commitu (`git log --grep "texty a analytika pro malá dema"`).
- [ ] **Step 2: Napsat padající `MiniDemoSlot.test.jsx`:**
  - `it.each` přes `["cs","en","de"] × ["allocation","dividends"]` `("renders only static text on the server for %s %s", …)`: `renderToString(<MiniDemoSlot …/>)` obsahuje `copy.badge`, `copy[demo].staticText`, `copy.disclaimer` a `href="/demo"`, neobsahuje `welcome-minidemo-live`, `%` ani `$` (statický text nenese hodnoty z dat) a druhé volání vrátí stejný řetězec,
  - `it("hydrates the prerendered markup without a mismatch", …)`: `container.innerHTML = renderToString(…)`, `vi.spyOn(console, "error")`, `act(() => hydrateRoot(container, …))` se stubem IntersectionObserveru, který nikdy nespustí callback. `console.error` volán nebyl a v DOM je pořád statický text,
  - `it("loads the demo only once it scrolls into view", …)`: stub `globalThis.IntersectionObserver` si uloží callback, `loader = vi.fn(() => Promise.resolve({ default: () => <div className="welcome-minidemo-live">live</div> }))`. Před callbackem `loader` volán není. Po `callback([{ isIntersecting: true }])` je `findByText("live")` a `loader` byl volán jednou. Observer dostal `rootMargin: "200px 0px"` a po zobrazení se odpojil,
  - `it("mounts at once where IntersectionObserver is missing", …)` (výchozí jsdom),
  - `it("keeps the static text when the demo chunk fails to load", …)`: `loader = () => Promise.reject(new Error("chunk"))`, `console.error` umlčený. Po `waitFor` je statický text pořád vidět a odkaz na demo funguje,
  - `it("captures landing_minidemo_used once per demo", …)`: `AnalyticsProvider initialConsent="accepted"` s `createMemoryAdapter()` a falešnou komponentou s tlačítkem, které volá `onUse`. Po 3 kliknutích je v `adapter.events` přesně jedna položka `["landing_minidemo_used", { demo: "dividends", language: "de" }]`,
  - `it("sends nothing before analytics consent", …)`: `initialConsent="pending"`, po kliknutích není žádná událost `landing_minidemo_used`,
  - `it("calls onDemo from the full-demo link", …)`,
  - `it("never statically imports the demo, its data or recharts", …)`: zdroj `./MiniDemoSlot.jsx?raw` neodpovídá `/^import[^;]*(MiniAllocation|MiniDividends|miniDemoData|demoPortfolio|recharts)/m`, ale obsahuje `import("./MiniAllocation")` a `import("./MiniDividends")`. Totéž (bez dynamických importů) platí pro `./FeatureList.jsx?raw` a `../../pages/Welcome.jsx?raw`.
- [ ] **Step 3: Spustit test a ověřit, že padá.** Spustit `cd frontend && npx vitest run --mode edition-local src/components/landing/MiniDemoSlot.test.jsx`. Očekávaný výsledek: FAIL.
- [ ] **Step 4: Implementovat `MiniDemoSlot.jsx`.**
  - `live` začíná na `false`. V `useEffect` se zapne buď hned (když chybí `IntersectionObserver`), nebo po prvním `isIntersecting` a observer se pak odpojí.
  - Líná komponenta se vytváří přes `useMemo(() => lazy(loader ?? LOADERS[demo]), [loader, demo])`.
  - `onUse` hlídá `useRef` a pošle `capture(ANALYTICS_EVENTS.LANDING_MINIDEMO_USED, { demo, language })` jen jednou a jen pro `language` z `["cs","en","de"]`. `capture` je z `useOptionalAnalytics()`, takže bez provideru (prerender) se nic neděje.
  - Soubor importuje `./miniDemos.css`.
- [ ] **Step 5: Ověřit, že test projde.** Stejný příkaz. Očekávaný výsledek: PASS.
- [ ] **Step 6: Napsat padající `FeatureList.test.jsx`** (`copy = COPY.cs`, bez IntersectionObserveru, takže se ukázky načtou hned):
  - `it("puts the allocation demo after the allocation screenshot in the same row", …)`: první `article.welcome-feature` obsahuje `img[src=LANDING_IMAGES.allocation.src]` a za ním `[data-demo="allocation"]`,
  - `it("turns the dividends feature into a row with its demo instead of a picture", …)`: existuje `article` s nadpisem `copy.features[3].title` a `[data-demo="dividends"]` a bez `img`. Funkce „Výkonnost proti indexům“ a „Více portfolií, jedna měna“ zůstávají v `.welcome-more`,
  - `it("wires the real Czech copy end to end", …)`: `await findByRole("button", { name: "Sektory" })`, klik, pak `findByText("Informační technologie")`,
  - `it("lets an existing picture win over its mini demo", …)`: `vi.resetModules()`, `vi.doMock("./landingImages", …)` se `dividends: { src: "/landing/d.png", width: 10, height: 10 }`, dynamický import `FeatureList` a render. Řádek dividend má `img` a nemá `[data-demo="dividends"]`.
- [ ] **Step 7: Upravit `FeatureList.jsx`.** Řádek funkce se staví průchodem `feature.images` v jejich pořadí:
  - existující obrázek → `Shot`,
  - `null` s položkou v `MINI_DEMO_FOR_IMAGE` → `MiniDemoSlot` (`copy={copy.miniDemos}`),
  - jinak nic.

  Funkce je řádek, když má desktopový obrázek nebo ukázku. Pak upravit `Welcome.jsx` na `<FeatureList copy={copy} language={language} onDemo={handleDemoCtaClick("landing_minidemo")} />`.
- [ ] **Step 8: Upravit `Welcome.test.jsx`.**
  - do `describe.each(LANGUAGES)` přidat `it("labels both mini demos as a sample portfolio and links each to the full demo", …)`: `getAllByText(copy.miniDemos.badge)` má délku 2, `getAllByText(copy.miniDemos.disclaimer)` také 2 a oba odkazy `copy.miniDemos.fullDemo` mají `href="/demo"`,
  - přidat `it("captures demo_started with entry_point=landing_minidemo from a mini demo link", …)` po vzoru testu `landing_closing`,
  - stávající test „two feature screenshots“ musí projít beze změny očekávaných `src`.
- [ ] **Step 9: Spustit testy, sestavení, prerender a ruční kontrolu.**
  - Spustit `cd frontend && npx vitest run --mode edition-local src/components/landing src/pages/Welcome.test.jsx && npm test && npm run test:cloud && npm run build && npm run build:cloud`. Očekávaný výsledek: PASS a prerender bez chyby.
  - Ověřit prerender: `grep -c "Ukázkové portfolio" dist/prerendered/index.html` vrátí `2`, `grep -c "Sample portfolio" dist/prerendered/en/index.html` vrátí `2`, `grep -c "Beispielportfolio" dist/prerendered/de/index.html` vrátí `2` a `grep -c "welcome-minidemo-live" dist/prerendered/index.html` vrátí `0`.
  - Volitelně ověřit vzhled: `npx vite --mode edition-cloud --port 5181` (vlastní port) a Playwright na `http://localhost:5181/`. Šířky 1280 a 360px, kontroluje se, že stránka nemá vodorovný posuv, že je jen jeden stín v řádku, že klávesnice (Tab, Enter) ovládá ukázky a že `prefers-reduced-motion` funguje.
- [ ] **Step 10: Změřit znovu a porovnat.**
  - Spustit `node scripts/measure-initial-bundle.mjs dist src/pages/Welcome.jsx` a `node scripts/measure-initial-bundle.mjs dist`.
  - Nárůst S3 je nejvýš 2,5 KiB pro Welcome a nejvýš 2,5 KiB pro `index.html`. Celkem s S1 je to u každé entry nejvýš 5 KiB proti základu z commitu S1.
  - S3 by `index.html` měl zvětšit jen nepatrně (`MiniDemoSlot`, `FeatureList` a `miniDemos.css` patří do chunku Welcome). Větší nárůst je signál, že se ukázka nebo její data dostala do hlavního balíčku. Pak se musí najít příčina pomocí kontroly manifestu níže, i když je číslo v rozpočtu.
  - `excluded_dynamic_imports` pro Welcome obsahuje `src/components/landing/MiniAllocation.jsx` a `src/components/landing/MiniDividends.jsx`.
  - V `dist/.vite/manifest.json` se `src/demo/demoPortfolio.js` nesmí objevit v rekurzivním `imports` grafu Welcome. Kontrola: `node -e` s `collectInitialAssets` z `scripts/measure-initial-bundle.mjs` a výpisem klíčů navštívených položek, nebo ručně procházením `imports`.
- [ ] **Step 11: Upravit `DESIGN.md` §10.** Přidat odstavec o malých ukázkách:
  - jsou ploché panely s hairline a bez stínu a nahrazují jen chybějící obrázek,
  - pruhy používají `--chart-1`, vybraný měsíc `--chart-2` a stisknutý přepínač má okraj `--ink`,
  - nesou štítek „Ukázkové portfolio“ a upozornění,
  - načítají se líně až po doskrolování a v prerenderu je jen statický text,
  - texty jsou v `welcomeCopy.js` → `miniDemos`.

  Současně upravit větu „the only brand color…“ tak, aby zůstala pravdivá (ukázky brand nepoužívají).
- [ ] **Step 12: Commitnout** soubory z výčtu se zprávou `feat(landing): malá interaktivní dema u rozložení a dividend`. Do těla commitu dát velikosti `před → po`.

**Hotovo, když:**
- všechny testy z kroku 9 jsou zelené a oba buildy prošly,
- prerenderované HTML ve třech jazycích obsahuje dvakrát štítek a žádný živý obsah,
- velikosti jsou v rozpočtu,
- `DESIGN.md` odpovídá novému vzhledu.

---

## Integrační testy

Spouští se na sloučené větvi `feature/landing-mini-demos` po vlně 2 (po případném rebase na `main` znovu):

1. `cd frontend && npm test`: celá Vitest sada v local edici.
2. `cd frontend && npm run test:cloud`: celá Vitest sada v cloud edici.
3. `cd frontend && node --test scripts/measure-initial-bundle.test.mjs scripts/prerender.test.mjs`
4. `cd frontend && npm run build`: local build.
5. `cd frontend && npm run build:cloud`: cloud build + prerender (`validateMarkup` musí projít pro `/`, `/en/` i `/de/`).
6. `cd frontend && node scripts/measure-initial-bundle.mjs dist src/pages/Welcome.jsx && node scripts/measure-initial-bundle.mjs dist`: porovnání se základem z commitu S1. Každá z obou entry smí proti základu narůst nejvýš o 5 KiB (rozpočet z Global Constraints).
7. `grep -c "welcome-minidemo-live" frontend/dist/prerendered/index.html` vrátí `0` a `grep -c "Ukázkové portfolio" frontend/dist/prerendered/index.html` vrátí `2`.

Backendové sady (`pytest`) se nespouští: změna nesahá na backend, DB, migrace ani `EXPECTED_ALEMBIC_HEAD`.

## Sekce (strojově)

```json
[
  {
    "id": "S1",
    "title": "Texty, analytický kontrakt a měření balíčku",
    "wave": 1,
    "files": [
      "frontend/src/pages/welcomeCopy.js",
      "frontend/src/pages/welcomeCopy.test.js",
      "frontend/src/analytics/eventContract.js",
      "frontend/src/analytics/eventContract.test.js",
      "frontend/scripts/measure-initial-bundle.mjs",
      "frontend/scripts/measure-initial-bundle.test.mjs",
      "docs/operations/posthog-activation-analytics.md"
    ],
    "test_commands": [
      "cd frontend && node --test scripts/measure-initial-bundle.test.mjs",
      "cd frontend && npx vitest run --mode edition-local src/pages/welcomeCopy.test.js src/pages/Welcome.test.jsx src/analytics",
      "cd frontend && npm test",
      "cd frontend && npm run test:cloud",
      "cd frontend && npm run build:cloud && node scripts/measure-initial-bundle.mjs dist src/pages/Welcome.jsx && node scripts/measure-initial-bundle.mjs dist"
    ]
  },
  {
    "id": "S2",
    "title": "Data, interaktivní komponenty a styly ukázek",
    "wave": 1,
    "files": [
      "frontend/src/components/landing/miniDemoData.js",
      "frontend/src/components/landing/miniDemoData.test.js",
      "frontend/src/components/landing/MiniAllocation.jsx",
      "frontend/src/components/landing/MiniAllocation.test.jsx",
      "frontend/src/components/landing/MiniDividends.jsx",
      "frontend/src/components/landing/MiniDividends.test.jsx",
      "frontend/src/components/landing/miniDemos.css",
      "frontend/src/components/landing/miniDemos.css.test.js"
    ],
    "test_commands": [
      "cd frontend && npx vitest run --mode edition-local src/components/landing",
      "cd frontend && npm test",
      "cd frontend && npm run test:cloud"
    ]
  },
  {
    "id": "S3",
    "title": "Schránka s líným načtením, zapojení do úvodní stránky a DESIGN.md",
    "wave": 2,
    "files": [
      "frontend/src/components/landing/MiniDemoSlot.jsx",
      "frontend/src/components/landing/MiniDemoSlot.test.jsx",
      "frontend/src/components/landing/FeatureList.jsx",
      "frontend/src/components/landing/FeatureList.test.jsx",
      "frontend/src/pages/Welcome.jsx",
      "frontend/src/pages/Welcome.test.jsx",
      "DESIGN.md"
    ],
    "test_commands": [
      "cd frontend && npx vitest run --mode edition-local src/components/landing src/pages/Welcome.test.jsx",
      "cd frontend && npm test",
      "cd frontend && npm run test:cloud",
      "cd frontend && npm run build",
      "cd frontend && npm run build:cloud && node scripts/measure-initial-bundle.mjs dist src/pages/Welcome.jsx && node scripts/measure-initial-bundle.mjs dist"
    ]
  }
]
```
