---
slug: twr-vs-xirr
target_query: "twr vs xirr" (ODHAD autora konceptu, neověřeno klíčovými slovy; jiný agent dělá keyword research)
title: "TWR vs XIRR: jak počítat výnos portfolia"
meta_description: "TWR měří, jak si vedly vaše investice. XIRR měří, jak si vedly vaše peníze. Rozdíl na příkladu s čísly a jak oba výnosy počítá Portfyl."
h1: "TWR vs XIRR: jak počítat výnos portfolia"
language: cs
status: draft-needs-owner-review
---

# TWR vs XIRR: jak počítat výnos portfolia

Dva investoři si koupí stejné akcie a každý dnes vidí jiný „výnos“. Pokaždé je to správně, jen odpovídají na jinou otázku. Ukážeme si, na jakou otázku odpovídá TWR a na jakou XIRR, spočítáme to na příkladu s čísly a řekneme, jak oba ukazatele počítá Portfyl.

## Dvě otázky, dva ukazatele

**TWR (time-weighted return, časově vážený výnos)** odpovídá na otázku: *jak si vedly samotné investice?* Neřeší, kdy jste doplnili peníze nebo je vybrali. Hodí se k porovnání s indexem nebo s jiným fondem, protože hodnotí „výkon portfolia“ bez vlivu vašich vkladů.

**XIRR (rozšířená vnitřní míra výnosnosti, money-weighted return)** odpovídá na otázku: *jak si vedly moje peníze?* Bere v úvahu, kolik jste kdy vložili a kdy to bylo. Roční sazba, kterou vyjde, říká, jakým úrokem by se musely zhodnocovat vaše vklady, aby skončily na dnešní hodnotě. Hodí se k osobnímu hodnocení: „Vydělal jsem při svém načasování vkladů dobře?“

## Jak se TWR počítá

Období se rozdělí na úseky vždy při pohybu peněz (vklad, výběr). V každém úseku se spočítá výnos a ty se pak násobí:

TWR = (1 + r₁) × (1 + r₂) × … × (1 + rₙ) − 1

Každé r je výnos jednoho úseku, tedy konečná hodnota děleno počáteční hodnotou mínus 1, přičemž nový vklad do počáteční hodnoty příštího úseku patří. Vklad tedy výnos „neovlivní“, protože každý úsek se hodnotí zvlášť.

## Jak se XIRR počítá

Hledá se taková roční sazba r, při které součet všech peněžních toků diskontovaných na dnešek dává nulu:

Σ CFᵢ / (1 + r)^(dᵢ/365) = 0

CFᵢ je tok v den dᵢ (měřeno ve dnech od prvního toku). Vklady jsou záporné, dnešní hodnota portfolia (a případné výběry) kladná. Rovnici nelze vyřešit vzorcem, proto se hledá přibližně (Newtonova metoda, bisekce). Stejný princip používá funkce XIRR v Excelu.

## Příklad: stejné TWR, jiné XIRR

Všechna čísla jsou smyšlená a slouží jen k vysvětlení. Dva investoři začnou 1. 1. 2025 s 100 000 Kč. Za půl roku (2. 7. 2025) každý vloží dalších 100 000 Kč. Trh se pohybuje takto:

- **Investor A:** první půlrok +10 %, vloží peníze na vrcholu, druhý půlrok −10 %. Konec: 189 000 Kč.
- **Investor B:** první půlrok −10 %, vloží peníze na dně, druhý půlrok +10 %. Konec: 209 000 Kč.

**TWR** je u obou stejné: 1,10 × 0,90 − 1 = −1,0 % (a stejně 0,90 × 1,10 − 1 = −1,0 %). Jejich investice se vyvíjely stejně, jen v opačném pořadí.

**XIRR** už ale vychází různě. U A (vklady −100 000 a −100 000, konec +189 000) je to přibližně −7,28 % ročně. U B (konec +209 000) je to přibližně +6,02 % ročně. A vložil víc peněz těsně před poklesem, B těsně před růstem. Peněžně je A v mínusu 11 000 Kč, B v plusu 9 000 Kč, přestože portfolia „jako produkt“ dopadla stejně.

Proto platí: TWR hodnotí výběr investic, XIRR hodnotí výběr investic i načasování vkladů.

## Který ukazatel kdy použít

- **Porovnání s indexem nebo jiným portfoliem:** TWR. Index žádné vklady nemá, takže srovnání je férové jen tehdy, když ze svého výnosu vliv vkladů odstraníte.
- **„Kolik mi to vlastně vydělalo za celou dobu?“:** XIRR (nebo prostý zisk v korunách).
- Oba čísla spolu nemusejí souhlasit a není to chyba. Čím víc vkladů a výběrů, tím víc se mohou rozejít.

Pozor na krátká období: XIRR i CAGR jsou přepočet na rok. Z pár týdnů vyjde roční číslo, které nic neslibuje.

## Jak to počítá Portfyl

**TWR.** Portfyl denně sleduje hodnotu portfolia a pohyby peněz zvenku (vklady, výběry) a denní výnos počítá metodou Modified Dietz: výnos dne = (hodnota dnes − hodnota včera − tok dne) / (hodnota včera + 0,5 × tok dne). Denní výnosy se násobí. Je to tedy denní aproximace „čistého“ TWR: rozdíl může vzniknout jen uvnitř jednoho dne, kdy se předpokládá, že peníze přišly v půlce dne. Pokud import obsahuje vklady a výběry, jsou jediným vnějším tokem a nákupy a prodeje jsou jen přesun mezi hotovostí a akciemi. Dividendy a poplatky hodnotu portfolia mění, ale tokem nejsou.

**XIRR.** Portfyl řeší stejnou rovnici s dny děleno 365, jak ji zná Excel. Toky jsou vklady a výběry a na konci dnešní hodnota. Je to výnos za celou historii portfolia, ne za zvolené období.

**Měna.** Stránka Analytics počítá TWR i XIRR v amerických dolarech (přepočet kurzem). Výkonnostní graf na přehledu ukazuje stejný výpočet ve vybrané měně zobrazení.

## Co si z toho odnést

TWR není lepší než XIRR ani naopak. Každé odpovídá na jinou otázku, a když znáte obě odpovědi, rozumíte svému výsledku lépe. Zkuste si to na vlastních číslech: do Portfyl nahrajete export z Trading 212 (CSV) a oba ukazatele uvidíte vedle sebe. Můžete začít i s ukázkovým portfoliem.

*Není investiční poradenství.* Text je jen vzdělávací. Minulé výnosy nezaručují budoucí. Příklady jsou smyšlené.

**Odkazy (návrh):** [domovská stránka Portfyl](/) · [Yield on cost](/yield-on-cost) · [Jak porovnat portfolio s indexem](/porovnani-portfolia-s-indexem) (URL jsou orientační, vychází z routy S4).

## Výpočet

Skript načetl funkce `_xirr` (backend/routers/portfolio.py) a `_modified_dietz_daily_returns` (backend/routers/analytics.py) přímo ze zdrojového souboru a spustil je (Python 3.14, pandas 3.0.2).

- Denní příklad Modified Dietz: V = 100 000, 101 000, 153 000; tok třetí den 50 000. r₁ = 1 000/100 000 = 1,0 %; r₂ = (153 000 − 101 000 − 50 000)/(101 000 + 25 000) = 2 000/126 000 = 1,5873 %. Řetěz: 1,01 × 1,015873 − 1 = 2,6032 %. Funkce Portfyl vrátila [0,01, 0,015873], řetěz 2,6032 %. Shoda.
- Investor A: úsek 1 +10 % (100 000 → 110 000), úsek 2: 189 000/(110 000 + 100 000) − 1 = −10,0 %. TWR = 1,10 × 0,90 − 1 = −1,0 %. Vloženo 200 000, konec 189 000, prostý výsledek −5,5 %. Dny: 2. 7. 2025 je den 182, 1. 1. 2026 je den 365. XIRR (funkce Portfyl) = −7,2808 %; kontrola NPV při této sazbě = 0,0.
- Investor B: úsek 1 −10 % (100 000 → 90 000), úsek 2: 209 000/(90 000 + 100 000) − 1 = +10,0 % (209 000/190 000 = 1,10). TWR = 0,90 × 1,10 − 1 = −1,0 %. Prostý výsledek (209 000 − 200 000)/200 000 = +4,5 %. XIRR = +6,0239 %.

## Ověření tvrzení

| Tvrzení v textu | Zdroj v kódu |
|---|---|
| Denní Modified Dietz, vzorec výnosu dne | `analytics._modified_dietz_daily_returns` (docstring i kód) |
| Denní výnosy se řetězí (kumulativní TWR) | `analytics.risk_metrics` (`cumulative = (1 + daily_returns).cumprod()`, `"method": "modified-dietz-twr"`) a `portfolio.get_performance` (`cumulative_twr`) |
| Při vkladech/výběrech jsou jediným tokem C, hodnota zahrnuje hotovost, nákupy/prodeje nejsou tok | `analytics._build_value_cashflow_series` (větev `has_external_cashflows`), `cash_ledger.EXTERNAL_FLOW_TYPES` = deposit, withdrawal, card_debit, cashback |
| Dividendy/poplatky mění hodnotu, tokem nejsou | docstring `_build_value_cashflow_series` |
| XIRR: dny/365, Newton + bisekce | `portfolio._xirr`; popis v `frontend/src/pages/Analytics.jsx` (INFO.xirr) |
| XIRR je za celou historii | `analytics._lifetime_money_weighted` |
| Toky XIRR = vklady/výběry + čistá hodnota na konci (cash-aware větev) | `_lifetime_money_weighted` |
| Stránka Analytics v USD; graf výkonu v měně zobrazení | `analytics.risk_metrics` volá `_build_value_cashflow_series(transactions, start_date)` bez `display_currency` (výchozí USD), `_lifetime_money_weighted` má `"currency": "USD"`; `frontend/src/api.js` `fetchRiskMetrics` neposílá měnu; `portfolio.get_performance` předává `display_currency=currency` |

**Rozdíly oproti učebnici (k rozhodnutí vlastníka):**
1. TWR je denní aproximace (konce dnů, toky v půlce dne), ne přesné přecenění při každém toku. Pro denní data běžné.
2. XIRR se počítá v USD a historické toky se převádějí aktuálním kurzem (`_live_to_usd`), ne kurzem v den toku (komentář v kódu to uvádí). Pro investora v CZK to není „čisté“ XIRR v korunách.
3. Pokud `_xirr` nenajde kořen (nebo všechny toky mají stejné znaménko), vrací 0,0, tedy UI ukáže 0 %, ne „nelze spočítat“.

## Neověřeno

- Že export Trading 212 vždy obsahuje vklady a výběry (ovlivňuje, která větev výpočtu se použije; netestováno s reálným exportem).
- Že odchylka denní aproximace oproti přesnému TWR je v praxi zanedbatelná (v textu je jen logické tvrzení, že vzniká uvnitř dne).
- Reálná čísla Trading 212 nebo jakékoli tržní statistiky: nepoužity.
- Zda stránka Analytics bude u všech uživatelů dostupná: do textu nepatří, vlastník ať rozhodne o vhodnosti CTA.

## Related

[[Portfolio analytics]] · [[Portfyl]] · [[2026-11-09-portfyl-seo]]
