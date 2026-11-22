---
slug: vykonnost-portfolia-vs-benchmark
target_query: "porovnání portfolia s indexem S&P 500" # GUESS, replace after the keyword research (alternatives to test: "výkonnost portfolia", "jak porovnat portfolio s indexem")
title: "Výkonnost portfolia a srovnání s indexem | Portfyl"
meta_description: "Jak Portfyl počítá výkonnost portfolia (TWR) a jak ji srovnává s indexy S&P 500, NASDAQ 100 a STOXX 50. Včetně limitů, které je dobré znát."
h1: "Výkonnost portfolia a srovnání s indexem"
language: cs
status: draft-needs-owner-review
---

# Výkonnost portfolia a srovnání s indexem

Zisk v korunách říká, kolik jste vydělali. Neříká, jestli jste si vedli dobře. K tomu potřebujete výnos v procentech, který nezávisí na tom, kdy jste vložili peníze, a nějaké měřítko, se kterým ho srovnáte. Portfyl počítá výkonnost z vašich obchodů a umožňuje ji porovnat s indexy S&P 500, NASDAQ 100 nebo STOXX 50 za týden, rok i celou historii.

## Co Portfyl ukazuje

**Vývoj portfolia.** Na přehledu vidíte graf hodnoty portfolia, nebo jeho růst v procentech. Období volíte mezi 7 dny, od začátku měsíce, měsícem, třemi měsíci, od začátku roku, rokem a celou historií.

**Srovnání s indexem.** Do grafu můžete přidat křivku S&P 500, NASDAQ 100 nebo STOXX 50. Podrobnější srovnání najdete na stránce Analytika. Je tam křivka portfolia proti zvolenému indexu za 3 měsíce až 2 roky, rozdíl obou výsledků a další ukazatele, například beta nebo alfa. Na výběr je víc přednastavených indexů a výchozím je S&P 500.

**Výnos v ročním vyjádření.** U zisku portfolia se může zobrazit i roční výnos IRR (XIRR), který bere v úvahu, kdy jste peníze vložili.

## Jak počítáme výnos

### Růst v procentech: časově vážený výnos (TWR)

Růst v procentech je časově vážený výnos. Portfyl ho počítá po jednotlivých dnech a dny pak řetězí za sebou. Díky tomu výsledek nezkresluje to, kdy jste peníze vložili nebo vybrali. Měří, jak se dařilo samotným investicím.

Vymyšlený příklad. Začínáte se 100 000 Kč a v prvním období portfolio vyroste o 10 %, takže má 110 000 Kč. Pak vložíte dalších 100 000 Kč, celkem tedy 210 000 Kč, a v druhém období portfolio klesne o 5 %. Na konci máte 199 500 Kč a vložili jste 200 000 Kč, takže jste o 500 Kč níž. Časově vážený výnos je přitom +4,5 % (1,10 × 0,95 = 1,045). Rozdíl vzniká tím, že větší část peněz byla v portfoliu právě v horším období.

Pokud historie obsahuje vklady a výběry (export z Trading 212 je obsahuje), hodnota portfolia zahrnuje i hotovost. Přijaté dividendy a úroky ji zvyšují, poplatky snižují, ale za vklad se nepočítají.

### Výnos IRR (XIRR)

IRR je naproti tomu peněžně vážený roční výnos. Zohledňuje načasování vkladů a výběrů, a proto vyjde jinak než TWR. Oba údaje odpovídají na jinou otázku, a tak se vzájemně nenahrazují.

### Měna

Zobrazení hodnoty portfolia si přepočítáte do měny, kterou zvolíte. Na stránce Analytika se výnos portfolia počítá v dolarech.

## Co srovnání s indexem neříká

- **Křivka indexu se nepřepočítává do vaší měny.** Je vedená v měně, ve které se index počítá. Výsledek vašeho portfolia ve zvolené měně a výsledek indexu tedy nejsou měřené stejnou měnou.
- **Portfolio a index nejsou měřené úplně stejně.** Pokud historie obsahuje vklady a výběry, počítá se do portfolia i přijatá dividenda a úrok z hotovosti. Křivka indexu vychází jen z jeho denních zavíracích cen.
- **Alfa a Sharpeův poměr počítají s pevně danou bezrizikovou sazbou 5 % ročně.** Neodpovídá aktuálnímu trhu.
- **Ukazatele vůči indexu potřebují dost dat.** Aby se spočítaly, musí portfolio a index překrývat nejméně 10 obchodních dnů.
- **Ceny pocházejí z veřejně dostupného zdroje.** Pokud ceny chybí, křivka může být neúplná nebo se nezobrazí.
- **Dostupnost funkcí závisí na typu účtu.** Graf hodnoty a růstu na přehledu s indexy je dostupný vždy. Srovnání na stránce Analytika, beta, alfa a IRR jsou součástí rozšířené analytiky. Podrobnosti najdete v části Ceník na [úvodní stránce](/).

Minulá výkonnost nezaručuje budoucí.

## Související

Jak se portfolio skládá, ukazuje článek [Rozložení portfolia podle sektorů a měn](/rozlozeni-portfolia). Kolik přichází na dividendách, popisuje článek [Sledování dividend po měsících](/sledovani-dividend). Jak data z Trading 212 dostat do Portfylu, vysvětluje [stránka o sledování portfolia z Trading 212](/sledovani-portfolia-trading-212).

## Není investiční poradenství

Portfyl ukazuje vaše vlastní data a veřejné údaje. Srovnání s indexem slouží k orientaci a není to investiční poradenství. Rozhodnutí zůstávají na vás.

## Podívejte se, jak srovnání vypadá

Na [úvodní stránce](/#funkce) si u funkce Výkonnost proti indexům můžete vyzkoušet ukázku na vymyšlených datech a porovnat ukázkové portfolio s indexem S&P 500. Registraci k tomu nepotřebujete.

<!-- OWNER: CTA wording depends on whether public sign-up is open (O6 in the SEO plan). -->

## Ověření tvrzení

| # | Tvrzení v textu | Důkaz v repu |
|---|---|---|
| 1 | Srovnání s S&P 500, NASDAQ 100, STOXX 50 za týden, rok i celou historii | `frontend/src/pages/welcomeCopy.js` cs.features[2] (řádky 60-66); `frontend/src/pages/Dashboard.jsx:46` PERIODS, `:49-54` BENCHMARKS |
| 2 | Graf hodnoty nebo růstu v %, období 7D, MTD, 1M, 3M, YTD, 1Y, All | `Dashboard.jsx:46` PERIODS; přepínač Value / Growth % (řádky 465-475); `backend/routers/portfolio.py:2406` `_resolve_start_date`, `:2420` `get_performance` |
| 3 | Do grafu lze přidat křivku S&P 500, NASDAQ 100, STOXX 50 | `Dashboard.jsx:49-54`; `backend/routers/portfolio.py:2763` BENCHMARK_TICKERS, `:2772` `get_benchmarks` |
| 4 | Stránka Analytika: období 3M až 2Y, křivka proti indexu, rozdíl, beta, alfa; výchozí S&P 500 | `frontend/src/pages/Analytics.jsx:24` PERIODS = 3M/6M/1Y/2Y, `:57-68` (Beta, Alpha, Active Return), `:158-166` výchozí S&P (`^GSPC`); `backend/routers/benchmarks.py:299` `benchmark_comparison`; `backend/routers/analytics.py:974` `resolve_benchmark` (S&P preset jako fallback) |
| 5 | Víc přednastavených indexů | `backend/alembic/versions/0001_multiuser_schema.py:456-462` (S&P 500, NASDAQ 100, Dow Jones, STOXX 50, MSCI World, MSCI ACWI, 60/40); `benchmarks.py:138` `list_benchmarks` |
| 6 | Roční výnos IRR (XIRR) u zisku portfolia | `Dashboard.jsx:234` (`riskMetrics.lifetime.xirr`, zobrazeno jen s analytikou); `analytics.py:1151` `_lifetime_money_weighted`, `portfolio.py:2345` `_xirr` |
| 7 | Růst v % je časově vážený výnos, počítaný po dnech a řetězený | `portfolio.py:2420` `get_performance` (`cumulative_twr *= 1.0 + daily_return`, `pnl_pct = (cumulative_twr - 1) * 100`); `analytics.py:871` `_modified_dietz_daily_returns` (r = (V_t - V_t-1 - C_t) / (V_t-1 + 0.5 C_t)) |
| 8 | Vklady a výběry výsledek nezkreslují | `analytics.py:871` (C = vnější toky se z výnosu odečítají); `analytics.py:689` docstring `_build_value_cashflow_series` |
| 9 | Příklad s čísly: 110 000 + 100 000 = 210 000, krát 0,95 = 199 500; 1,10 x 0,95 = 1,045 | Aritmetika; vymyšlená čísla, označena v textu. Odpovídá řetězení v bodě 7. |
| 10 | Při vkladech a výběrech zahrnuje hodnota hotovost; dividendy a úroky zvyšují, poplatky snižují, vklad to není | `analytics.py:689` docstring (`has_external_cashflows`: V zahrnuje běžný zůstatek hotovosti, "dividends, interest and lending income raise net worth while fees reduce it. None of those events enter C"); `backend/cash_ledger.py:52` `has_external_cashflows` |
| 11 | Export z Trading 212 obsahuje vklady a výběry | `backend/routers/portfolio.py:78-84` `_T212_CASH_ACTIONS` (deposit, withdrawal, ...) |
| 12 | IRR je peněžně vážený roční výnos, bere v úvahu načasování vkladů | `analytics.py:1151-1270` `_lifetime_money_weighted` (xirr_flows z vkladů a výběrů); `Analytics.jsx:99` "Annualized IRR (XIRR)" |
| 13 | Zobrazení přepočteno do zvolené měny (přehled) | `portfolio.py:2420` `get_performance(currency=...)` -> `_build_value_cashflow_series(display_currency=currency)`; `frontend/src/lib/displayCurrency.js:5` |
| 14 | Na stránce Analytika se výnos portfolia počítá v dolarech | `benchmarks.py:299` a `analytics.py:1039` volají `_build_value_cashflow_series(transactions, start_date)` s výchozím `display_currency="USD"` |
| 15 | Křivka indexu se nepřepočítává do vaší měny, je v měně indexu | `portfolio.py:2772` `get_benchmarks` (procentní změna zavíracích cen, bez FX); `analytics.py:950` `_benchmark_daily_returns` / `_ticker_daily_returns` (bez FX) |
| 16 | Křivka indexu vychází z denních zavíracích cen | `portfolio.py:2795-2813` (`raw["Close"]`); `analytics.py:908` `_ticker_daily_returns` (`pct_change` zavíracích cen) |
| 17 | Do portfolia se počítá i dividenda a úrok z hotovosti, jen když historie obsahuje vklady a výběry | viz bod 10 |
| 18 | Alfa a Sharpe s pevnou bezrizikovou sazbou 5 % | `analytics.py:25` `RISK_FREE_RATE = 0.05`, použito na `:1019` (alfa), `:1080` (Sharpe), `:1084` (Sortino) |
| 19 | Ukazatele vůči indexu potřebují aspoň 10 překrývajících se dnů | `analytics.py:1006` `_benchmark_compare_metrics` (`if len(aligned) < 10: return {}`) |
| 20 | Ceny z veřejně dostupného zdroje; chybějící ceny dají neúplnou křivku nebo žádnou | hub Market data; `analytics.py:689` (`return None, None, None` bez cenových dat), `benchmarks.py:299` (prázdná `series`), `Analytics.jsx:324` ("No overlapping data with this benchmark") |
| 21 | Dostupnost: graf na přehledu a překryv indexů dostupné vždy; srovnání na Analytice, beta, alfa, IRR v rozšířené analytice | `portfolio.py:2420` a `:2772` bez `require_capability`; `benchmarks.py:299` a `analytics.py:1039` mají `require_capability("portfolio_analytics")`; `backend/plans.py:81` (`portfolio_analytics` = Investor) |
| 22 | Nejde o investiční poradenství; ukázka na vymyšlených datech bez registrace | `welcomeCopy.js` cs.questions[3], cs.questions[0], `cs.miniDemo.performance` (S&P 500) |

## Neověřeno

- **Měnová nesrovnalost je skutečná a text ji přiznává.** Na přehledu se portfolio počítá ve zvolené měně a křivka indexu je v měně indexu. Na stránce Analytika se portfolio počítá v dolarech a index ve své měně. Pro investora v koruně to znamená, že srovnání míchá kurzovou změnu koruny. Je to rozhodnutí o metodice, ne chyba textu. Než stránku spustíte, zvažte, jestli chcete index převádět do zobrazovací měny. Text dnes říká jen pravdu o tom, co kód dělá.
- **Že index ze zdroje neobsahuje dividendy.** Kód stahuje zavírací ceny (`auto_adjust=True`) a věta v textu říká jen, že index vychází z cen. Zda použité symboly (`^GSPC`, `^NDX`, `^STOXX50E`) jsou čistě cenové indexy, je znalost z venku, kód ji nedokazuje. Text proto neříká, že index dividendy "nezahrnuje".
- **Přesnost cen a indexů ze zdroje** (yfinance) se neměřila. Pojmenování zdroje v textu není (práva k zobrazování tržních dat jsou otevřená).
- **Předvolená období v UI**: úvodní stránka slibuje "týden, rok i celou historii" a přehled to splňuje (7D, 1Y, All). Stránka Analytika má jen 3M až 2Y. Text rozlišuje obě.
- **Hotovost v hodnotě portfolia u portfolií bez vkladů a výběrů** (např. vlastní CSV jen s buy, sell, dividend) se počítá jinou, jednodušší větví (`analytics.py` větev `else`). Text proto tvrdí zahrnutí hotovosti jen pro historii s vklady a výběry. Chování druhé větve jsem do textu nepřidával.
- **Žádná reálná čísla, výkonnosti ani snímky obrazovky** v textu nejsou. Jediný číselný příklad je výslovně vymyšlený.
- **Přesné české názvy** oddílů v aplikaci (Analytika, Přehled) jsem ověřoval jen proti angličtině (`Analytics.jsx`, `Dashboard.jsx`). Před publikací je sjednoťte s `frontend/src/i18n/messages/cs.js`.

### Rozhodnutí pro vlastníka

1. **Měna srovnání** (viz první bod výše): přepočítat index do zobrazovací měny, nebo nechat a přiznávat?
2. **Zmínka o Bitcoinu.** Přehled nabízí vedle indexů i křivku Bitcoinu, v textu není, protože úvodní stránka ho nezmiňuje.
3. **IRR a TWR vedle sebe.** Je to hodnotný výklad, který konkurence tak jasně nedává (plán S10). Chcete na něj navázat samostatný článek (TWR vs XIRR)?

## Related

- [[Frontend structure]]
- [[Portfolio analytics]]
- [[2026-11-09-portfyl-seo]]
