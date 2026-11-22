---
slug: porovnani-portfolia-s-indexem
target_query: "jak porovnat portfolio s indexem" (ODHAD autora konceptu, neověřeno klíčovými slovy; jiný agent dělá keyword research)
title: "Jak porovnat portfolio s indexem (benchmarkem)"
meta_description: "Jak férově porovnat výnos svého portfolia s indexem: vklady, měna, cenový vs. total return index a procentní body. Příklady s čísly."
h1: "Jak porovnat portfolio s indexem"
language: cs
status: draft-needs-owner-review
---

# Jak porovnat portfolio s indexem

„Porazil jsem trh?“ je nejčastější otázka investora. Odpověď ale závisí na tom, jak porovnání uděláte. Špatně zvolený výnos, jiná měna nebo index, který nepočítá dividendy, mohou obrátit závěr naruby. Tady je postup, jak srovnání udělat férově, s příklady a čísly.

## Proč srovnávat s indexem

Index (benchmark) je měřítko: ukazuje, kolik by vydělal pasivní nákup celého trhu nebo jeho části. Smyslem není „vyhrát“, ale zjistit, zda vaše rozhodnutí (výběr akcií, načasování) přinesla něco navíc oproti jednoduché alternativě. Pokud držíte hlavně americké akcie, je rozumné srovnávat s americkým indexem. Srovnávat evropské dividendové akcie s indexem technologických firem nedává smysl.

## Pravidlo 1: srovnávejte stejné období

Index i portfolio musí být měřeny od stejného dne do stejného dne. Pokud jste většinu peněz vložili před třemi měsíci, srovnání s indexem za poslední rok vás klame, protože v prvních devíti měsících jste peníze v portfoliu neměli.

## Pravidlo 2: odstraňte vliv vkladů

Index nemá žádné vklady a výběry. Vaše portfolio ano. Proto nelze prostě podělit konečnou hodnotu počáteční. Použijte výnos, který vklady neutralizuje, tedy časově vážený výnos (TWR), viz [TWR vs XIRR](/twr-vs-xirr).

**Příklad (smyšlená čísla).** Začnete se 100 000 Kč. Po půl roce má portfolio 108 000 Kč (+8 %), vložíte 50 000 Kč a na konci roku máte 168 000 Kč. Index za stejné dva úseky: +8 % a +6 %.

- Naivní výpočet „konec děleno začátek“: 168 000 / 100 000 − 1 = +68 %. To je nesmysl, většinu z toho tvoří váš vklad.
- Skutečný zisk je 168 000 − 100 000 − 50 000 = 18 000 Kč.
- TWR: druhý úsek 168 000 / (108 000 + 50 000) = 1,0633, takže 1,08 × 1,0633 − 1 = **+14,84 %**.
- Index: 1,08 × 1,06 − 1 = **+14,48 %**.
- Rozdíl: 14,84 − 14,48 = **0,36 procentního bodu** ve váš prospěch.

## Pravidlo 3: rozdíl počítejte v procentních bodech

Portfolio +12 % a index +9 % znamená náskok 3 procentní body (12 − 9). Poměr výnosů je ale (1,12 / 1,09) − 1 = 2,75 %. Obě čísla jsou „správně“, každé odpovídá jiné otázce. Pro čitelnost se obvykle uvádí rozdíl v procentních bodech. Důležité je psát to jasně, aby bylo vidět, o které číslo jde.

## Pravidlo 4: stejná měna

Index v dolarech porovnávaný s vaším portfoliem v korunách srovnává dvě různé věci. Příklad: index vzroste o 10 % v USD, ale koruna za rok posílí z 24 na 22,8 Kč za dolar, tedy dolar ztratí vůči koruně 5 %. V korunách vyjde 1,10 × (22,8 / 24) − 1 = **+4,5 %**, ne 10 %. Pokud vaše portfolio vyšlo v korunách +8 %, vypadá proti indexu v dolarech (+10 %) slabě, proti indexu v korunách (+4,5 %) ale dobře.

## Pravidlo 5: cenový index, nebo total return?

Cenový index sleduje jen změnu cen akcií. Total return index navíc zahrnuje reinvestované dividendy. Portfolio, kterému přicházejí dividendy, se správně srovnává s total return variantou, jinak se mu připíše výhoda, která tam není.

**Příklad (hypotetický).** Cenový index za tři roky vzroste o 30 %. Firmy v indexu vyplácejí 1,5 % ročně a dividendy se reinvestují. Total return: 1,30 × 1,015³ − 1 = **+35,94 %**. Rozdíl téměř 6 procentních bodů vzniká jen kvůli dividendám.

Zkontrolujte tedy vždy, jestli je ukazatel, se kterým srovnáváte, cenový nebo total return, a podle toho vyberte.

## Co ještě stojí za pohled

Samotný výnos neříká všechno. Dvě portfolia se stejným výnosem se mohou lišit rizikem. Proto se k srovnání přidávají míry jako beta (jak moc se portfolio hýbe s indexem), tracking error (jak moc se od indexu odchyluje) nebo největší pokles. Beta 1,2 znamená, že portfolio v minulosti pohyby indexu zesilovalo. Je to historický údaj, ne předpověď.

## Jak to dělá Portfyl

Stránka Analytics porovnává portfolio s vybraným benchmarkem. Jako předvolby nabízí S&P 500, NASDAQ 100, Dow Jones, STOXX 50, MSCI World, MSCI ACWI a kombinaci 60/40 (světové akcie a dluhopisy), a můžete přidat vlastní benchmark: jeden ticker nebo košík s váhami.

Postup je tentýž jako výše: portfolio se přepočte na denní výnosy, které neutralizují vklady a výběry (metoda Modified Dietz, viz [TWR vs XIRR](/twr-vs-xirr)). Stejně se spočítají denní výnosy benchmarku. Obě řady se spojí v dnech, kdy jsou k dispozici obě, a složí se do kumulativních křivek. Aktivní výnos je kumulativní výnos portfolia minus kumulativní výnos benchmarku, v procentních bodech. Z denních výnosů Portfyl dopočítá i betu, tracking error a další míry. Na přehledu lze do grafu výkonnosti přidat také jednoduché srovnání s indexem: procentní změna ceny indexu od začátku zvoleného období.

Dvě poznámky: benchmark bere Portfyl v měně, v níž je kótovaný, bez přepočtu na měnu portfolia. Stránka Analytics navíc počítá portfolio v amerických dolarech. U indexu v jiné měně se proto do rozdílu promítne i vývoj kurzu (viz pravidlo 4).

Chcete-li si to vyzkoušet na vlastních datech, nahrajte export z Trading 212 (CSV). Můžete začít i s ukázkovým portfoliem.

*Není investiční poradenství.* Text je jen vzdělávací. Minulé výnosy nezaručují budoucí. Příklady jsou smyšlené.

**Odkazy (návrh):** [domovská stránka Portfyl](/) · [TWR vs XIRR](/twr-vs-xirr) · [Yield on cost](/yield-on-cost) (URL jsou orientační).

## Výpočet

Přepočítáno v Pythonu (Python 3.14).

- Příklad s vkladem: druhý úsek portfolia 168 000 / 158 000 = 1,063291 (+6,329 %). TWR = 1,08 × 1,063291 − 1 = 14,8354 %. Index: 1,08 × 1,06 − 1 = 14,48 %. Rozdíl 0,3554 p. b. Naivně 168 000 / 100 000 − 1 = 68 %. Zisk 168 000 − 100 000 − 50 000 = 18 000.
- Body vs. poměr: 12 − 9 = 3 p. b.; 1,12 / 1,09 − 1 = 2,7523 %.
- Měna: 22,8 / 24 − 1 = −5,0 %; 1,10 × 0,95 − 1 = 4,5 %.
- Cenový vs. total return: 1,015³ = 1,045678; 1,30 × 1,045678 − 1 = 35,938 %; rozdíl 5,94 p. b.
- Denní Modified Dietz funkce Portfyl (`_modified_dietz_daily_returns`) byla spuštěna na jednoduchém příkladu a odpovídá ručnímu výpočtu (viz draft twr-vs-xirr).

## Ověření tvrzení

| Tvrzení | Zdroj v kódu |
|---|---|
| Předvolby S&P 500, NASDAQ 100, Dow Jones, STOXX 50, MSCI World, MSCI ACWI, 60/40 košík (7 řádků seedu; MSCI World je ETF URTH) | `alembic/versions/0001_multiuser_schema.py` (seznam preset benchmarků) |
| Vlastní benchmark = ticker nebo košík s váhami | `analytics._benchmark_daily_returns`, `_basket_daily_returns`; `routers/benchmarks.py` |
| Aktivní výnos = výnos portfolia − výnos benchmarku (p. b.) | `routers/benchmarks.py` `benchmark_comparison` (`active_return`), `frontend/src/pages/Analytics.jsx` (INFO „PortfolioReturn − BenchmarkReturn“) |
| Kumulativní křivky z denních výnosů, jen společné dny | `benchmark_comparison` (`pd.DataFrame(...).dropna()`, `(1 + ...).cumprod() - 1`) |
| Beta, tracking error atd. z denních výnosů | `analytics._benchmark_compare_metrics` |
| Benchmark bez přepočtu měny | `analytics._ticker_daily_returns` (jen `pct_change` z kurzu v měně kótace); portfolio v USD: `risk_metrics`/`benchmark_comparison` volají `_build_value_cashflow_series` bez `display_currency` |
| Jednoduché srovnání na přehledu: % změna ceny od začátku období | `routers/portfolio.py` `get_benchmarks` (`(v - base) / base`), `BENCHMARK_TICKERS`; použití `Dashboard.jsx` (`fetchBenchmarks`) |

**Rozdíly oproti učebnici / možné slabiny (k rozhodnutí vlastníka):**
1. Žádný přepočet měny u benchmarku. U STOXX 50 (EUR) a podobných vzniká měnový rozdíl v „aktivním výnosu“. Buď to zůstane přiznané v textu (jako teď), nebo se opraví v kódu a text se přepíše.
2. Srovnání na Analytics je v USD, ne v CZK, i když zbytek aplikace normalizuje na CZK.
3. Přehledový graf (`/portfolio/benchmarks`) bere cenu indexu od prvního dne období, portfolio je v tomtéž grafu TWR, takže definice jsou mírně jiné než na stránce Analytics.

## Neověřeno

- Zda jsou předvolené indexy (^GSPC, ^NDX, ^DJI, ^STOXX50E) u poskytovatele dat cenové, nebo total return. V textu tedy tvrdíme jen obecnou radu „zkontrolujte, který typ je“. Údaj o URTH jako ETF s úpravou na dividendy nebyl ověřen.
- Že beta 1,2 „zesiluje pohyby“ je obecná definice, ne měření Portfyl.
- Jakákoli skutečná tržní data nebo výnosy indexů: nepoužity.

## Related

[[Portfolio analytics]] · [[Portfyl]] · [[2026-11-09-portfyl-seo]]
