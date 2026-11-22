---
slug: sledovani-dividend
target_query: "sledování dividend" # GUESS, replace after the keyword research (alternatives to test: "přehled dividend portfolio", "dividendový kalendář")
title: "Sledování dividend po měsících | Portfyl"
meta_description: "Přijaté a očekávané dividendy po měsících, kalendář ex-dat a růst dividend v jednom přehledu. Portfyl počítá z dat z Trading 212 nebo CSV."
h1: "Sledování dividend po měsících"
language: cs
status: draft-needs-owner-review
---

# Sledování dividend po měsících

Dividendy z akcií a ETF chodí od různých firem a v různých měsících. Portfyl je sečte za celé portfolio: kolik přišlo, od koho a jak váš dividendový příjem roste. Vychází z obchodů a dividend, které do Portfylu nahrajete z Trading 212 nebo z vlastního souboru CSV. Jak data dostat dovnitř, popisuje [stránka o sledování portfolia z Trading 212](/sledovani-portfolia-trading-212).

## Co přehled dividend ukazuje

### Přijaté dividendy

Přehled ukazuje dividendy po měsících za aktuální rok a k tomu součet za celou historii. U každého měsíce vidíte rozpis podle akcie, tedy od koho dividenda přišla.

Odkud se částky berou, záleží na zdroji dat. U importu z Trading 212 jde o částku, která vám byla skutečně připsána na účet. U vlastního CSV platí to, co do souboru zadáte: počet kusů krát dividenda na kus.

### Očekávané platby na dalších 12 měsíců

Druhá část ukazuje, co můžete v příštích 12 měsících očekávat. Platby, u kterých už zdroj dat uvádí datum výplaty, jsou označené jako potvrzené. Ostatní jsou odhad.

### Kalendář ex-dat a dat výplaty

Tabulka u každé držené akcie ukazuje počet kusů, dividendu na akcii, odhad ročního příjmu (dividenda na akcii krát počet kusů, které držíte), dividendový výnos a ex-datum s datem výplaty. Řádky, u kterých datum chybí nebo si navzájem neodpovídají, jsou zvlášť, v oddílu k ověření.

### Růst dividend

U každé držené akcie přehled počítá, kolik let po sobě dividenda rostla, jaký byl průměrný roční růst (CAGR) za posledních až pět uzavřených let, meziroční změnu a výplatní poměr, pokud je k dispozici.

## Jak se odhad počítá

Odhad vychází z dividend, které firma vyplatila za posledních zhruba 13 měsíců. Portfyl každou platbu posune z ex-data na typický den výplaty, promítne ji o rok dopředu a vynásobí počtem kusů, které držíte dnes. Platby, které už vám přišly, se z odhadu odečtou.

Odhad je tedy prodloužená minulost, ne příslib. Firma může dividendu změnit, nebo ji úplně vynechat, a Portfyl s tím předem počítat nemůže.

## Na co si dát pozor

- **Přijaté a odhadované částky nejsou stejného druhu.** Přijaté dividendy vycházejí z toho, co vám bylo připsáno. Odhad počítá dividendu na akcii krát počet kusů, bez jakékoli srážky. Obě řady proto nesčítejte bez rozmyslu.
- **Odhad je počítaný v dolarech.** Do zvolené měny se přepočítá aktuálním kurzem, takže jeho výše v korunách kolísá s kurzem.
- **Data o dividendách pocházejí z veřejně dostupného zdroje.** U méně obchodovaných titulů mohou data nebo termíny chybět nebo být nepřesné. Proto existuje oddíl k ověření.
- **Kalendář a odhad se týkají pozic, které držíte teď.** Dividendy z už prodaných pozic jsou zahrnuty v přijatých částkách, ale do kalendáře ani odhadu nevstupují.
- **Odhad a růst dividend nejsou součástí každého typu účtu.** Podrobnosti najdete v části Ceník na [úvodní stránce](/). Kalendář ex-dat a dat výplaty je k dispozici vždy.

## Související

Jak se mění hodnota portfolia a jak si stojí proti indexu, popisuje článek [Výkonnost portfolia a srovnání s indexem](/vykonnost-portfolia-vs-benchmark). Jak jsou rozložené vaše pozice, ukazuje článek [Rozložení portfolia podle sektorů a měn](/rozlozeni-portfolia).

## Není investiční poradenství

Přehled dividend slouží k orientaci ve vašem vlastním portfoliu. Není to investiční poradenství ani daňový podklad a rozhodnutí zůstávají na vás.

## Podívejte se, jak přehled vypadá

Na [úvodní stránce](/#funkce) si u funkce Dividendy měsíc po měsíci můžete vyzkoušet ukázku na vymyšlených datech. Registraci k tomu nepotřebujete.

<!-- OWNER: CTA wording depends on whether public sign-up is open (O6 in the SEO plan). -->

## Ověření tvrzení

| # | Tvrzení v textu | Důkaz v repu |
|---|---|---|
| 1 | Portfyl sečte dividendy za celé portfolio: kolik, od koho, jak příjem roste | `frontend/src/pages/welcomeCopy.js` cs.features[3] (řádky 68-70); `frontend/src/pages/Dividends.jsx` |
| 2 | Přijaté po měsících za aktuální rok + součet za celou historii | `backend/routers/portfolio.py:2127` `get_dividend_forecast` (`months[].paid`, `total_paid`, `total_paid_all_time`); `Dividends.jsx` DividendBars ("{year} so far", "All time") |
| 3 | Rozpis podle akcie v měsíci | `portfolio.py:2127` (`entries_by_month` s `ticker`, `name`, `amount`, `status: "paid"`) |
| 4 | Import z Trading 212 = skutečně připsaná částka | `backend/t212_sync.py:1453` `_finalize_dividend_event` (`txn._native_cash_amount = net_amount` z pole `amount`); CSV: `backend/routers/portfolio.py:132-330` `_normalize_t212_detailed` (`cash_amount = abs(total)`); čtení v `backend/cash_ledger.py:28` `signed_cash` |
| 5 | Vlastní CSV: počet kusů krát dividenda na kus | `backend/routers/portfolio.py:404` `_NATIVE_IMPORT_TYPES` (dividend), `:499` povinné sloupce `shares`, `price`; `cash_ledger.py:46-47` (bez `cash_amount` je to `shares * price`) |
| 6 | Očekávané platby na 12 měsíců; potvrzené (zdroj uvádí datum) vs odhad | `portfolio.py:2107` `_build_outlook`, docstring `get_dividend_forecast` ("confirmed" / "forecasted"), `:2022` `_announced_payment` |
| 7 | Kalendář: počet kusů, dividenda na akcii, roční příjem = dividenda na akcii x kusy, výnos, ex-date, datum výplaty | `portfolio.py:1914` `get_dividends` (`_normalize_dividend_row`, `ex_date`, `pay_date`, `dividend_rate`, `dividend_yield`); `Dividends.jsx` `buildColumns` (komentář "Rate per share x the shares you hold") |
| 8 | Řádky s chybějícím nebo nesouhlasným datem zvlášť k ověření | `Dividends.jsx` (`needsReview` = `date_status === "inconsistent"` nebo bez `ex_date`; sekce "Date unavailable or needs review") |
| 9 | Růst: série let růstu, CAGR za až 5 uzavřených let, meziroční změna, výplatní poměr | `backend/dividend_growth.py` `_streak` (řádek 47), `_cagr` (`max_years=5`, řádek 60), `_yoy`, `compute_dividend_growth` (`payout_ratio_pct` z `info["payoutRatio"]`); `Dividends.jsx` GrowthSection |
| 10 | Odhad: posledních ~13 měsíců, posun z ex-data na výplatu, projekce o rok, krát dnešní kusy | docstring `portfolio.py:2127` ("trailing ~13 months", "shift each payment from its ex-date to its pay date", "scaled by the user's current share count"); `:2039` `_project_payments`; cutoff `Timedelta(days=400)` |
| 11 | Už přišlé platby se z odhadu odečtou | `portfolio.py:2039` `_project_payments(..., paid_dates=credited)`; komentář "cancel the projection it fulfils" v `get_dividend_forecast` |
| 12 | Odhad je bez srážky (dividenda na akcii x kusy x kurz) | `portfolio.py` `get_dividend_forecast`: `amount = shares * event["per_share"] * usd_rate`, žádná srážka |
| 13 | Odhad je počítaný v dolarech, do zvolené měny přepočten aktuálním kurzem | `get_dividend_forecast` vrací `"currency": "USD"`; `Dividends.jsx` DividendBars (komentář "The forecast is in USD; `rate` is display units per USD") |
| 14 | Data z veřejně dostupného zdroje, mohou chybět | hub Market data (yfinance, "possibly delisted"); `backend/market_data.py`; `portfolio.py:1914` (řádky bez sazby se vynechají, data výplaty z `calendar` jako fallback) |
| 15 | Kalendář a odhad jen pro držené pozice, přijaté zahrnují i prodané | `portfolio.py:1914` a `:2127` (`_build_holdings(transactions)` = aktivní pozice); přijaté: smyčka přes všechny `Transaction` typu `dividend` |
| 16 | Odhad a růst nejsou v každém typu účtu, kalendář ano | `backend/plans.py:69-90` MINIMUM_PLAN (`dividend_analysis` = Investor, `dividends` = Free); dekorátory `require_capability("dividend_analysis")` na `portfolio.py:2127` a `:2307`, bez dekorátoru na `:1914` |
| 17 | Ukázka na vymyšlených datech bez registrace | `welcomeCopy.js` cs.questions[0], cs.miniDemo.disclaimer; `cs.features[3].demo = "dividends"` |
| 18 | Nejde o investiční poradenství | `welcomeCopy.js` cs.questions[3] |

## Neověřeno

- **Že částka dividendy z Trading 212 je čistá po srážce u zdroje.** Úvodní stránka to tvrdí ("Částky jsou v čisté výši, po srážce u zdroje") a kód používá skutečně připsanou částku, ale chování není ověřené na řádku s konkrétní srážkou. Text proto říká "skutečně připsaná částka" a čistotu výslovně netvrdí. Pokud to chcete tvrdit, ověřte to jedním reálným řádkem.
- **Co přesně znamená "potvrzené".** Kód označí platbu jako potvrzenou, když zdroj dat (yfinance) uvádí datum výplaty. Není to potvrzení společností. Text proto říká "zdroj dat uvádí datum výplaty".
- **Přesnost dat o dividendách** z veřejného zdroje se neměřila. Text slibuje jen, že data mohou chybět.
- **Pojmenování zdroje dat** (Yahoo Finance / yfinance) v textu není. Práva k zobrazování tržních dat jsou stále otevřená (Workstream A), rozhodnutí je na vlastníkovi.
- **České názvy** oddílu "k ověření" a dalších popisků rozhraní jsem nepřebíral z `frontend/src/i18n/messages/cs.js`, popisuji je slovy. Před publikací je případně sjednoťte s popisky v aplikaci.
- **Kolik zdrojů dat se dnes používá pro růst dividend**: kód preferuje Shibui a padá zpět na yfinance (`dividend_growth.py`). V textu není, protože zdroj se může měnit.
- **Konkrétní čísla, snímky obrazovky a příklady z reálných portfolií** jsem nevymýšlel.

### Rozhodnutí pro vlastníka

1. **Odhad v dolarech.** Odhad je interně v USD a přepočítává se. Chcete to na stránce říkat takhle otevřeně (ano), nebo nejdřív zlepšit výpočet v koruně?
2. **Daň a srážka.** Stránka záměrně neřeší daně (SEO plán §8). Věta "není daňový podklad" je jediná zmínka. Souhlasíte?
3. **Slug a registrace stránky** v `frontend/src/seo/publicPages.js` zůstává na implementaci.

## Related

- [[Frontend structure]]
- [[Portfolio analytics]]
- [[2026-11-09-portfyl-seo]]
