---
slug: rozlozeni-portfolia
target_query: "rozložení portfolia podle sektorů" # GUESS, replace after the keyword research (alternatives to test: "alokace portfolia", "diverzifikace portfolia přehled")
title: "Rozložení portfolia podle sektorů a měn | Portfyl"
meta_description: "Podívejte se, jak je portfolio rozložené podle pozic, sektorů, zemí a měn, a nastavte si cílové váhy. Včetně toho, jak a z čeho se skupiny určují."
h1: "Rozložení portfolia podle sektorů, měn a zemí"
language: cs
status: draft-needs-owner-review
---

# Rozložení portfolia podle sektorů, měn a zemí

Pět akcií z jednoho oboru, nebo pět akcií z pěti? Většina portfolia v jedné měně, nebo ve třech? Rozložení portfolia na to odpoví a Portfyl ho spočítá z obchodů, které nahrajete z Trading 212 nebo z vlastního CSV. U každé pozice uvidíte její váhu a hodnotu a hned poznáte, jestli vám jedna akcie nebo jeden sektor netvoří příliš velkou část portfolia.

## Co Portfyl ukazuje

**Pozice.** Každá držená pozice s hodnotou a váhou na portfoliu. Váha pozice se počítá z hodnoty držených pozic bez hotovosti.

**Sektory.** Kolik portfolia připadá na jednotlivé sektory.

**Kategorie.** Rozdělení podle druhu cenného papíru, například akcie nebo ETF.

**Měny.** V jakých měnách jsou vaše pozice kótované. Hotovost se počítá ve své měně.

**Země.** Na přehledu (úvodní obrazovce) můžete skupiny přepnout mezi sektory, zeměmi a kategoriemi. U každé skupiny vidíte váhu, hodnotu a celkový zisk, tedy realizovaný i nerealizovaný.

Hodnota pozice je aktuální cena krát počet kusů, přepočtená kurzem do měny, kterou si zvolíte. Menší skupiny se v grafu slučují do jedné položky (skupiny pod 2 % váhy), zatímco v tabulce zůstanou všechny. Pokud o hotovosti portfolio ví (z napojení Trading 212 nebo z vkladů a výběrů v historii), objeví se jako samostatná skupina u sektorů, kategorií a měn. U zemí ne, protože hotovost žádnou zemi nemá, a váhy zemí se proto počítají jen z pozic.

## Jak se skupiny určují

Tady je dobré vědět, co Portfyl dělá a co ne.

- **Sektor a země pocházejí z veřejně dostupných údajů o firmě.** U jednotlivých akcií jde o sektor a zemi firmy.
- **ETF se nerozpadá na své složky.** Portfyl nedělá takzvaný pohled dovnitř fondu. Celý ETF patří do jedné skupiny. U ETF a fondů, které sektor nemají, se jako sektor použije kategorie fondu, a pokud ji zdroj nemá, skupina „Diversified ETF“. U země se použije region nebo trh fondu, a pokud chybí, „Other“. Portfolio, které je z velké části ETF, proto může u sektorů a zemí vypadat méně rozprostřené, než ve skutečnosti je.
- **Měna znamená měnu, ve které se cenný papír obchoduje.** Není to měna, ve které firma vydělává. Akcie americké firmy kótovaná v dolarech patří do dolarů, ať prodává kdekoli.
- **Váhy nejsou všude počítané ze stejného základu.** Váha pozice vychází z hodnoty pozic bez hotovosti. U sektorů, kategorií a měn je hotovost součástí základu, takže stejná akcie může mít na dvou místech trochu jinou váhu.
- **Údaje ze zdroje mohou být neúplné.** U méně obchodovaných titulů sektor nebo země může chybět a skončí ve skupině „Other“.

## Cílové váhy a odchylka

Pro pozice si můžete nastavit cílové váhy v procentech, případně je sdružit do vlastních skupin. Součet nesmí přesáhnout 100 %, ale nemusíte nastavit všechno najednou. Portfyl pak ukáže, o kolik procentních bodů se skutečná váha od cíle liší a kolik peněz do cílové váhy chybí, případně přebývá. Pozice, které cíl nemají, se v přehledu ukážou také, jen bez odchylky.

Je to nástroj na hlídání vlastního plánu. Neříká, jaké cílové váhy zvolit.

## Co je dostupné vždy a co závisí na typu účtu

Rozložení podle pozic a cílové váhy jsou k dispozici vždy. Rozpad podle sektorů, zemí, kategorií a měn je součástí rozšířené analytiky a jeho dostupnost závisí na typu účtu. Podrobnosti najdete v části Ceník na [úvodní stránce](/).

## Související

Jak se portfolio vyvíjí a jak si stojí proti indexu, ukazuje článek [Výkonnost portfolia a srovnání s indexem](/vykonnost-portfolia-vs-benchmark). Kolik z něj plyne na dividendách, popisuje článek [Sledování dividend po měsících](/sledovani-dividend). Jak data z Trading 212 dostat do Portfylu, vysvětluje [stránka o sledování portfolia z Trading 212](/sledovani-portfolia-trading-212).

## Není investiční poradenství

Portfyl ukazuje vaše vlastní data a veřejné údaje o firmách. Rozložení portfolia ani cílové váhy nejsou investiční poradenství a rozhodnutí o tom, jak mají vypadat, zůstávají na vás.

## Podívejte se, jak rozložení vypadá

Na [úvodní stránce](/#funkce) si u funkce Rozložení podle pozic, sektorů a měn můžete vyzkoušet ukázku na vymyšlených datech a přepínat mezi pozicemi, sektory a měnami. Registraci k tomu nepotřebujete.

<!-- OWNER: CTA wording depends on whether public sign-up is open (O6 in the SEO plan). -->

## Ověření tvrzení

| # | Tvrzení v textu | Důkaz v repu |
|---|---|---|
| 1 | Portfyl spočítá rozložení z obchodů z Trading 212 / CSV | `frontend/src/pages/welcomeCopy.js` cs.lead (řádek 32), cs.brokers |
| 2 | U každé pozice váha a hodnota; hned poznáte příliš velkou část jedné akcie nebo sektoru | `welcomeCopy.js` cs.features[0] (řádek 47-49); `backend/routers/portfolio.py:1430` `get_holdings` (`weight`, `market_value`, řádek 1489) |
| 3 | Pohledy: pozice, sektory, kategorie, měny | `frontend/src/pages/Allocation.jsx:86-91` (`sector`, `asset_type`, `currency`), `:121-127` CATEGORY_TITLE; `frontend/src/lib/allocationBreakdown.js:6-11` DIMENSIONS |
| 4 | Váha pozice je z hodnoty držených pozic bez hotovosti | `backend/allocation_targets.py` záhlaví modulu ("current-weight denominator is the market value of active holdings ... cash excluded, exactly like that endpoint's `weight`"); `portfolio.py:1489` |
| 5 | Kategorie = druh cenného papíru (akcie, ETF, ...) | `backend/routers/analytics.py:1286` `_QUOTE_TYPE_LABEL` (Equity, ETF, Indices, Crypto, FX, Bonds), `:1436-1437` |
| 6 | Měny = měna, v níž je cenný papír kótovaný; hotovost ve své měně | `analytics.py:1341` `_allocation_totals` (komentář "FX exposure groups by the security's native trading currency", `currency_totals[trade_ccy]`, `cash_by_ccy_display`) |
| 7 | Přehled: přepínač sektory / země / kategorie, váha, hodnota, celkový zisk (realizovaný + nerealizovaný) | `frontend/src/components/dashboard/CompositionCard.jsx:15-19` DIMENSIONS, `:44-47` komentář ("weight, value, and total profit (realized + unrealized)"); `analytics.py:1326` `_weighted` |
| 8 | Hodnota = cena krát kusy, přepočteno kurzem | `analytics.py:1341` `_allocation_totals` (`native_value = shares * price`, `market_value = native_value * live_fx`); `portfolio.py:1430` `get_holdings`; `frontend/src/lib/displayCurrency.js:5` |
| 9 | Menší skupiny (pod 2 %) se v grafu slučují, v tabulce zůstávají všechny | `frontend/src/lib/allocationBreakdown.js:3-4,35` `boundedAllocationRows(rows, minWeightPct = 2)`; `Allocation.jsx:83,91` (výchozí práh) |
| 10 | Hotovost jako samostatná skupina u sektorů, kategorií a měn, jen když o ní portfolio ví | `analytics.py:1341-1405` (`has_cash`: `broker_cash.current_t212_cash` nebo `has_external_cashflows`), `:1495-1499` (`sector_totals["Cash"]`, `type_totals["Cash"]`, `currency_totals[ccy]`) |
| 11 | Země: hotovost bez země, váhy zemí jen z pozic | `analytics.py:1404-1407` a `:1492-1493` (komentář "Country deliberately gets NO Cash slice") |
| 12 | Sektor a země z veřejně dostupných údajů o firmě | `analytics.py:1297` `_classify_sector` (`info["sector"]`), `:1315` `_classify_country` (`info["country"]`); data z `market_data.get_infos` (yfinance), hub Market data |
| 13 | ETF: sektor = kategorie fondu, jinak "Diversified ETF"; země = region/trh, jinak "Other"; ETF se nerozkládá na složky | `analytics.py:1297-1323` `_classify_sector`, `_classify_country`; v `_allocation_totals` je jedna skupina na ticker (žádná dekompozice složek) |
| 14 | Chybějící sektor/země skončí v "Other" | `analytics.py:1312` (`return "Other"`), `:1323` (`return "Other"`) |
| 15 | Sektory, kategorie a měny mají hotovost v základu; pozice ne | viz body 4 a 10 |
| 16 | Cílové váhy v %, skupiny, součet nesmí přesáhnout 100 %, uložit lze i neúplně | `backend/allocation_targets.py:59` `validate_target_set` (`MAX_GROUP_LENGTH`, "A partial set ... is allowed", chyba jen při součtu nad 100 %); `backend/routers/allocation_targets.py:81` |
| 17 | Odchylka v procentních bodech a částka do cíle; pozice bez cíle se ukážou bez odchylky | `allocation_targets.py:84-137` `compute_drift` (`drift_pct`, `value_to_target`, řádky s `target_pct: None`) |
| 18 | Rozložení podle pozic a cílové váhy vždy; rozpad podle sektorů/zemí/kategorií/měn v rozšířené analytice | `backend/plans.py:69-90` (`allocation` = Free, `portfolio_analytics` = Investor); `analytics.py:1510` `sector_breakdown` s `require_capability("portfolio_analytics")`; `routers/allocation_targets.py` a `get_holdings` bez omezení |
| 19 | Nejde o investiční poradenství; ukázka na vymyšlených datech, přepínání pozice/sektory/měny | `welcomeCopy.js` cs.questions[3], cs.miniDemo.allocation.groupings, cs.questions[0] |

## Neověřeno

- **Země v UI jen na přehledu.** Stránka Rozložení (`Allocation.jsx`) země nenabízí, jen sektory, kategorie a měny. Země jsou jen v kartě na přehledu (`CompositionCard.jsx`). Plán S9 (§5) mluví o "sektorech, měnách, zemích", text tedy zeměmi nelže, ale říká, kde jsou. Úvodní stránka země nezmiňuje.
- **Rozpad podle sektorů v jiné měně než CZK nebo USD.** `sector_breakdown` počítá jen v CZK nebo USD (`display_ccy = "CZK" if ... else "USD"`, `analytics.py:1516`) a stránka Rozložení tento údaj posílá s označením zvolené měny (`Allocation.jsx` `currencyLabel`). Pro zobrazení v EUR, GBP nebo PLN je tedy možné, že částky v tabulce jsou v dolarech s jiným označením. Jde o potenciální chybu produktu. Text proto slibuje jen váhy a "přepočtenou hodnotu" obecně. Před publikací to prověřte, případně opravte v kódu, a zvažte, zda přidat výslovný příklad v eurech.
- **Víc brokerů najednou v jednom rozložení.** Karta "Account" se na stránce Rozložení ukáže, jen když `breakdown.accounts` existuje, ale `sector_breakdown` toto pole nevrací. Text sloučení účtů do jedné tabulky netvrdí.
- **Přesnost sektorů a zemí** z veřejného zdroje (yfinance) se neměřila. Pojmenování zdroje v textu není (práva k zobrazování tržních dat jsou otevřená).
- **České názvy** pohledů ("Kategorie", "Země", "Sektory") jsou z `CompositionCard.jsx` a `welcomeCopy.js`; v aplikaci mohou být jinak. Před publikací sjednotit s `frontend/src/i18n/messages/cs.js`.
- **Konkrétní čísla, procenta a snímky** jsem nevymýšlel.

### Rozhodnutí pro vlastníka

1. **Pohled dovnitř ETF.** Většina investorů z Trading 212 drží ETF. Stránka přiznává, že Portfyl ETF nerozpadá. Je to poctivé, ale i slabé místo proti konkurenci. Chcete to říkat takto otevřeně?
2. **Země jako samostatný pohled.** Chcete ho přidat i na stránku Rozložení, než na ni začneme lákat?
3. **Dostupnost podle typu účtu.** Sektory, země, měny jsou v rozšířené analytice. Zmínka je jen odkazem na Ceník (zadání zakazuje zmiňovat plány).

## Related

- [[Frontend structure]]
- [[Portfolio analytics]]
- [[2026-11-09-portfyl-seo]]
