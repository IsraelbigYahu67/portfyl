# Czech keyword and intent validation (SEO plan Wave 2, S6-S10)

Research date: 2026-11-22. Scope: the Czech pages planned in
`docs/superpowers/plans/2026-11-09-portfyl-seo.md` section 5, Wave 2 (S6 to
S10). Research only; nothing in the product was changed.

## 0. Read this first: what changed versus the plan

1. **The plan's claim "no established Czech tracker with Trading 212 support,
   Czech commercial-intent queries look open" (section 3.4) is outdated.** At
   least eight Czech-language products or content sites already target exactly
   these queries: Veverio, Taxomat, Trackly, Hedger, Taxero, Alocano,
   SlicyFolio, FinGather, plus Portseido's Czech pages, Monery and Finex's free
   tracker. Most of them sell on **Czech tax** (daňové přiznání, časový test,
   export for EPO), which Portfyl cloud permanently excludes. Czech
   Trading 212 demand is largely tax demand.
2. **Competition is real but beatable on informational and guide queries.**
   Pure product queries ("sledování portfolia Trading 212") already have an
   exact-match competitor (Veverio). The CSV-export guide and the
   "TWR vs XIRR" style explainers are thinner or fragmented.
3. **"portfyl" has no brand demand and is read as a typo.** Seznam answers
   "Hledali jsme portfel" and offers "portfyl" only as an alternative; Google
   autocomplete returns "portál ..." completions. Brand-query handling is
   therefore an entity-building task, not a defence of existing demand.

## 1. Method and limits (be sceptical of this file accordingly)

What was used:

- **Google autocomplete** (`suggestqueries.google.com`, `hl=cs`, `gl=cz`),
  about 90 seed queries. Shows what Czech users type, not how often. Many
  Czech seeds return nothing; Czech users clearly type English for these
  topics.
- **Seznam suggest** (`suggest.seznam.cz`), same seeds. Mostly returned
  nothing useful for finance terms.
- **Seznam search result pages** (`search.seznam.cz`), about 20 queries, read
  through WebFetch, which summarises pages with a small model. Result lists
  below are therefore paraphrased, sponsored versus organic labelling is as
  reported by that summary, and ranks can differ from what a given user sees.
  I could not get Google's Czech result pages (cookie-consent redirect).
- **WebSearch** (US-only index) for a few English or mixed queries.
- **Direct page fetch** of about 18 competitor pages to read their `<title>`,
  meta description, H1 and H2s. Trading 212's own Czech academy page returned
  HTTP 403 and Alocano returned 429, so those were seen only in search
  snippets.

What was **not** available:

- **No search volumes.** I had no access to Sklik, Google Search Console,
  Keyword Planner or any paid tool. Every volume statement is "unverified".
  "Difficulty" below is a qualitative impression from who ranks, never a
  number. The presence of an autocomplete suggestion shows that people type a
  phrase, not that many do.
- Google CZ rankings were not observed. Seznam is a reasonable proxy for the
  Czech market but not identical.
- Competitor claims (features, prices, broker support) come from their own
  marketing text and are unverified.

## 2. Evidence table: what the suggest services showed

"G" is Google autocomplete (cs/CZ), "S" is Seznam suggest. All frequency is
unverified.

| Seed | Useful completions seen |
|---|---|
| `sledování portfolia` | G: sledování akciového portfolia, aplikace na sledování portfolia, kde sledovat portfolio, jak sledovat portfolio. S: sledování portfolia |
| `trading 212 export` | G (English): export csv, export portfolio, export to excel, export from pie, export history, export transactions, export statement |
| `trading 212 csv` | G (English): csv export, csv file, download csv, import csv, how to get trading 212 csv |
| `trading 212 výpis` | G: výpis z účtu, roční výpis |
| `trading 212 dividend(y)` | G: dividendy daně, kde najdu dividendy, dividend tracker, dividend calendar (English), dividendy daně z dividend |
| `trading 212 daně` | G: daně z dividend, podklady pro daňové přiznání, daňové přiznání, frakční akcie daně |
| `trading 212 portfolio` | G (English): portfolio tracker, portfolio export, portfolio csv, portfolio performance, transfer |
| `trading 212` | G: recenze, poplatky, vs xtb, výběr peněz. S: recenze, přihlášení, demoverze |
| `portfolio tracker` | G: portfolio tracker zdarma, portfolio tracker cz, portfolio tracker recenze, nejlepší portfolio tracker zdarma |
| `dividendový kalendář` | G: 2026, 2025, fio dividendový kalendář |
| `přehled dividend` | G: přehled dividend 2025/2024, fio přehled dividend |
| `výkonnost portfolia` | G: xtb výkonnost portfolia |
| `výnos portfolia` | G: očekávaný výnos portfolia, výnosnost portfolia |
| `rozložení portfolia` | G: rozložení investičního portfolia, rozdělení portfolia, ideální rozložení portfolia |
| `diverzifikace portfolia` | G: diverzifikace portfolia význam, diverzifikace investičního portfolia |
| `porovnat portfolio s benchmarkem` | G: portfolio benchmark, portfolio performance návod (names the open-source "Portfolio Performance" app) |
| `twr xirr` | G: twr vs xirr, twr irr (mostly English); S: nothing relevant |
| `xirr co je` | G: xirr co to je, irr česky, irr co znamená |
| `yield on cost` | G: mostly English, plus real-estate completions |
| `yield on cost dividendy` | G: yield on cost co to je |
| `portfyl` | G: portál ... only. S: spelling suggestion to "portfel" |

Empty (no suggestion at all, either engine): `sledování dividend`,
`sledování dividend aplikace` (only `dividend app`), `trading 212 sledování
portfolia`, `porovnání portfolia s indexem`, `jak porovnat portfolio s s&p 500`,
`diverzifikace měn`, `čistý výnos portfolia`. Many exact Czech phrases are
simply too rare for autocomplete, or people type English.

## 3. Pages

### S7. Trading 212 portfolio and dividend tracking page

**Candidate queries**

1. sledování portfolia Trading 212
2. Trading 212 portfolio tracker (English phrasing, Google suggests it)
3. aplikace na sledování portfolia (broad, generic)
4. sledování dividend Trading 212
5. Trading 212 dividendy (see intent note)
6. Trading 212 přehled portfolia / výkonnost (weak: autocomplete gave nothing)

**Observed intent.** "sledování portfolia Trading 212" and "aplikace na
sledování portfolia" are commercial (the user wants a tool). "Trading 212
dividendy" is mixed: Seznam showed only broker reviews and tax guides, and
Google suggests "kde najdu dividendy" and "daně z dividend", so the dominant
Czech intent is "where do I see / how do I tax my dividends", not "tracker".

**Who ranks (Seznam, 2026-11-22)**

- "aplikace na sledování portfolia trading 212": sponsored Taxomat portfolio
  tracker page; Google Play and App Store listings of Trading 212 itself and of
  getquin; **Veverio** `veverio.com/cs/trading212-portfolio-tracker`; review
  sites (finex.cz, investplus.cz); trading212.com/cs.
- "trading 212 portfolio tracker": Czech-language YouTube how-to, Trading 212's
  Play Store listing, **Portseido** `/portfolio-tracker/trading-212/`,
  tracker212.com spreadsheet article, prostocktracker.com, and vpenize.cz.
- "aplikace na sledování portfolia": getquin, Portseido, Marketlog, Parqet and
  PieFolio on Google Play, KB Online Portfolio, investplus.cz explainer; Taxomat
  sponsored.
- Wider field seen on other queries: Trackly, Hedger, Taxero, Alocano,
  FinGather (Czech blog and landing), Finex free tracker, Stock Events.

**Competitor on-page evidence (read directly)**

- Veverio: title "Sledování portfolia Trading 212 s českou daní | Veverio",
  H1 "Sledování portfolia Trading 212 s odhadem české daně", meta mentions a
  read-only API key, performance, dividends, allocation, Czech tax estimate.
- Trackly home: "Trackly – přehled investic a daní pro české investory",
  mentions XTB, Trading 212, IBKR, Fio uploads.
- Portseido CZ: title "Portseido – portfolio tracker pro akcie, ETF a
  kryptoměny"; its Trading 212 page is in English.

**Difficulty (qualitative): medium to strong.** Evidence: an exact-match Czech
page exists (Veverio), two paid-ad advertisers bid on the head term (Taxomat
sponsored on four of the queries checked), and broad queries are held by app
store listings and established Czech finance media. Unverified whether any of
these pages has strong backlinks.

**Recommended target query:** `sledování portfolia Trading 212`.
Secondary on the same page: `Trading 212 portfolio tracker`,
`sledování dividend Trading 212`.

**Working title (52 chars):** `Sledování portfolia z Trading 212: výnos a dividendy`
**Meta (120 chars):** `Nahrajte export z Trading 212 a uvidíte výnos, dividendy a rozložení portfolia v CZK. Vyzkoušejte ukázku bez registrace.`
(Check that the demo really needs no registration before using that phrase.)

**Gaps competitors leave open**

- Every Czech competitor leads with tax. A page that is honestly about
  **performance versus an index, allocation and dividends in CZK**, with no tax
  claims at all, is a distinct angle. State plainly that Portfyl does not
  prepare tax filings, so tax-intent visitors leave quickly rather than bounce
  confused.
- No Czech page observed shows a worked example of why "Trading 212 own return"
  differs from time-weighted or money-weighted return on the same account.
- Portseido's Trading 212 page is English-only; Veverio requires an API key.
  CSV import without handing over an API key is a trust point (Trading 212
  community threads show users reluctant to share keys; unverified how common).
- Screenshots from a demo portfolio of a Czech investor in CZK.

---

### S8. Trading 212 CSV export / import guide

**Candidate queries**

1. jak stáhnout výpis z Trading 212 (Czech vernacular is "výpis")
2. Trading 212 export CSV (English phrase, Google suggests many variants)
3. Trading 212 výpis z účtu (Google suggests it)
4. Trading 212 roční výpis (Google suggests it)
5. Trading 212 historie transakcí export
6. Trading 212 import CSV (to a tracker)

**Observed intent.** Informational and task-driven. Czech users overwhelmingly
say "výpis" (statement) in videos and guides; "export CSV" is the English
phrase they also use. Underlying motive is usually tax or a tracker import, so
the guide also has commercial pull.

**Who ranks (Seznam)**

- "trading 212 jak exportovat historii csv": **Taxero** import guide, two
  YouTube how-to videos (one 36 seconds, March 2024; one April 2025, 509
  views), **Monery** help-centre article (Zendesk), a Chrome extension
  "Trading212 CSV exporter", and noise (generic CSV and BGP pages). Weak SERP.
- "trading 212 export csv": trading212.com/cs home, legal documents, the Chrome
  extension, **portfolio-terminal.com** (English import page), and Trading 212's
  English help-centre article "What documents can I get from Trading 212?".
  Very weak SERP, no good Czech guide.
- "trading 212 daně z dividend" (adjacent): Investnews, Navigátor úvěru,
  trading212.com/cs/taxes, Taxero, Times.cz, jenakcie.cz, **Trackly blog**.
  Strong, but it is tax intent.
- Czech guides embedded in tax/tracker content: Trackly "Jak stáhnout historii
  (CSV)" section, Investnews "Stáhněte roční přehled, PDF a úplnou historii".

**Competitor on-page evidence**

- Taxero: "Import výpisu z Trading 212 do Taxero.cz – kompletní návod 2026";
  H2s: Jak stáhnout výpis, Jaké transakce Taxero zpracuje, Automatická
  detekce stock splitů, Co Taxero nezpracuje, Časté problémy a řešení.
- Trackly blog: "Trading 212 a daně: daňové přiznání krok za krokem"; H2
  "Proč nepoužít sloupec Result", "Pies, AutoInvest a frakce".
- Monery: "Trading 212" with "Ruční export dat" / token connection.

**Difficulty (qualitative): weak to medium.** Evidence: the top Czech results
for the exact phrases are a Chrome extension, a 36-second video, vendor help
articles, and sections inside tax pages; no dedicated, well-structured Czech
"how to export" guide appears for "trading 212 export csv". Taxero is the one
real competitor for the "výpis" phrasing.

**Recommended target query:** `jak stáhnout výpis z Trading 212` (primary),
with "export CSV" in the title and H1 so the English-typed variants match too.

**Working title (48 chars):** `Jak stáhnout výpis z Trading 212 jako CSV: návod`
**Meta (123 chars):** `Jak v Trading 212 exportovat historii obchodů, dividend a vkladů do CSV, na co si dát pozor a jak soubor nahrát do Portfyl.`

**Gaps competitors leave open**

- A neutral guide not tied to a tax product: what to tick (orders,
  dividends, transactions, interest), the export period limit, multi-year
  stitching, Pies and fractional shares, multi-currency accounts.
- Facts seen in search results but **unverified against a real export**:
  community and Sharesight text say the web export is limited to a period of up
  to one calendar year; the CFD help article says 12 months per export and a
  "Recent Exports" list; the API CSV report endpoint is rate-limited to one
  request per minute. Verify each step against a real export first (plan
  Task 0) and re-check it before every republish; Trading 212 changes its UI.
- Trackly says "do not use the Result column" for tax; a performance-oriented
  equivalent ("which columns Portfyl uses and why") is open.
- The official Trading 212 help-centre article is English-only for the
  documents topic (seen in Seznam results). A Czech, screenshot-led, current
  guide is the gap.
- Video exists but only as 36-second to short clips; no written, indexed
  step-by-step with screenshots was seen in the first page of either query.

---

### S9. Feature pages: dividends, benchmark, allocation

Three separate pages; each has its own intent. Keep them distinct from S7 and
from each other (cannibalisation risk, see section 6).

#### S9a. Dividend tracking

**Candidate queries**

1. sledování dividend
2. dividend tracker (English, used in Czech; Czech blog titles use it)
3. přehled dividend (but see intent note)
4. dividendový kalendář (suggested by Google; high-frequency data intent,
   volume unverified)
5. sledování dividend zdarma / aplikace (empty in suggest)
6. dividendové portfolio

**Observed intent.** Mixed. "sledování dividend" on Seznam returns a
sponsored Taxomat tracker plus Google Play apps, a FinGather blog, Stock Events,
and a large block of **informational dividend content** (Peníze.cz topic page,
Fio dividend news, Wikipedia, ČEZ dividend pages). "přehled dividend" and
"dividendový kalendář" lean to **lookup intent for Czech stock dividends**
("fio přehled dividend", "ČEZ dividenda"), which an analytics app cannot
satisfy.

**Who ranks.** Taxomat (sponsored), Zen Stocks and other Google Play apps,
Peníze.cz, **FinGather blog** "Dividend tracker: jak mít přehled o dividendách
a výnosech" (title/H1 read directly), Fio, Wikipedia, ČEZ, Stock Events
(`stockevents.app/cz/dividend-tracker`), Seznam Zprávy. Related searches:
dividendový kalendář, dividendový výnos, dividendové portfolio, akcie s
měsíční dividendou.

**Difficulty: medium** for "sledování dividend" plus a tool angle (apps and one
Czech blog hold it, many informational pages are off-intent). **Strong** for
generic "dividendy" or "dividendový kalendář" (banks, brokers, media, calendar
sites). Do not target the generic terms.

**Recommended target query:** `sledování dividend`.

**Title (48 chars):** `Sledování dividend: přehled příjmů z akcií a ETF`
**Meta (113 chars):** `Sledujte dividendy z akcií a ETF po měsících, po titulech a v CZK. Podívejte se na ukázku Portfyl bez registrace.`

**Gaps.** Net versus gross dividend and withholding tax shown in one place
(Portfyl stores a net dividend row after withholding); reinvested dividends;
dividends converted to CZK at payment date; cumulative dividend income and
yield on cost per holding (links to the S10 article). Do not mention tax
reports or filing. Do not promise a Czech dividend calendar unless the
product has one.

#### S9b. Performance versus benchmark

**Candidate queries**

1. porovnání portfolia s indexem
2. výkonnost portfolia vs S&P 500
3. porovnat portfolio s S&P 500 (empty in suggest)
4. benchmark portfolia
5. porovnání výkonnosti portfolia
6. výkonnost portfolia

**Observed intent.** Informational. People either want a definition
("co je benchmark") or to compare indices (S&P 500 vs MSCI World); a smaller
group wants to compare their own portfolio. Commercial intent is thin.

**Who ranks (Seznam)**

- "jak porovnat výkonnost portfolia s indexem": mesec.cz (2014 article),
  **Finax** blog on measuring real performance, **Stock Events**
  `stockevents.app/cz/blog/porfolio-performance-comparison`, Stonkee glossary
  "Co je výkonnost portfolia vs. S&P 500?", Evropský podnik, odpovedi.cz.
- "výkonnost portfolia benchmark": WOOD & Company glossary featured snippet,
  Evropský podnik "Měření výkonnosti portfolia", Finemia "Benchmark", mesec.cz,
  Aisa International, FinHacker (CZK performance).
- "jak porovnat portfolio s indexem S&P 500": S&P 500 explainers from
  Vpenize, Times.cz, Financera, eToro, Tovarnik, Pfolio, Testedbrokers, plus
  FinHacker "Porovnání výkonnosti indexů S&P 500, MSCI World a PX".
- getquin and Portseido Play Store pages appear for "aplikace na sledování
  portfolia" with benchmark snippets.

**Difficulty: weak to medium** for "porovnání portfolia s indexem" (old
articles, glossaries, one competing tool page). **Strong** if the page drifts
to "S&P 500" as a head term (all major Czech finance media rank).

**Recommended target query:** `porovnání portfolia s indexem`.

**Title (52 chars):** `Porovnání portfolia s indexem: výkonnost vs. S&P 500`
**Meta (126 chars):** `Porovnejte výkonnost svého portfolia s S&P 500 nebo jiným indexem a zjistěte, jestli vás trh opravdu poráží. Ukázka v Portfyl.`

**Gaps.** Czech sources are glossary-style or old. Open: benchmark in **CZK**
(FX effect, FinHacker shows demand for this angle), TWR versus index when you
deposit monthly, total-return versus price index, choosing a fair benchmark
for a USD/EUR portfolio. Methodology must be exact (FX to CZK, dividends).

#### S9c. Allocation (sectors, currencies, countries)

**Candidate queries**

1. rozložení portfolia
2. alokace portfolia
3. diverzifikace portfolia
4. rozložení portfolia podle sektorů / zemí
5. analýza portfolia ETF (country/sector X-ray)
6. diverzifikace měn (empty in suggest)

**Observed intent.** Mostly informational, and much of it is **institutional
asset allocation** (asset classes, wealth-management reports), which is the
wrong intent for a tracker page. The tool-shaped result is a free ETF
portfolio X-ray.

**Who ranks (Seznam, "alokace portfolia sektory země měny")**: FXstreet,
EnCor Wealth, Evropský podnik, Raiffeisenbank allocation PDF, euro.cz,
Finlord, **Portseido CZ** (home page), and **mojefinancnisvoboda.cz
"Analýza portfolia ETF zdarma: země, sektory a firmy"**, a free tool. Google
suggest shows "jak rozložit portfolio", "ideální rozložení portfolia",
"diverzifikace portfolia význam".

**Difficulty: medium** on the long-tail tool phrasing, **strong** on
"diverzifikace portfolia" / "alokace aktiv" (banks, fund managers, glossaries,
unverified depth).

**Recommended target query:** `rozložení portfolia podle sektorů, zemí a měn`
(long-tail); keep "diverzifikace portfolia" as a supporting term only.

**Title (45 chars):** `Rozložení portfolia podle sektorů, zemí a měn`
**Meta (115 chars):** `Jak vypadá vaše portfolio podle sektorů, zemí a měn? Přehled alokace akcií a ETF v CZK. Vyzkoušejte ukázku Portfyl.`

**Gaps.** **Currency exposure for a CZK investor** (USD/EUR/GBP share of the
portfolio) is not addressed by anything seen; ETF look-through is covered only
by a free tool; Trading 212 Pies. Say clearly what data source the sector and
country labels come from and how fresh it is (market-data rights are still an
open workstream, plan Wave 4: do not promise coverage Portfyl cannot back).

---

### S10. Explainers

#### S10a. TWR vs XIRR

**Candidate queries**

1. TWR vs XIRR
2. jak spočítat výnos portfolia
3. time weighted return (English; Google suggests 15 variants)
4. časově vážený výnos / TWR co to je
5. xirr co to je (Google suggests)
6. TWR a XIRR rozdíl

**Observed intent.** Informational, with high tool-vendor overlap because
vendors publish the same explanation next to their product.

**Who ranks (Seznam "twr xirr" and "časově vážený výnos TWR")**

- **Investnews** "Jak spočítat výnos portfolia: XIRR, TWR a pravidelné
  vklady" (title and H1 read directly; has a model example, FAQ).
- **Alocano** help page "Výkonnost portfolia: TWR, MWR a XIRR".
- **Hedger** methodology page, **Trackly** features page (title "TWR a XIRR"),
  **SlicyFolio** wiki ("Výnos portfolia: TWR a MWR", worked four-investor
  example), InvestTerminal, Edward.
- Glossaries: finzi.cz, Fkička, Saxo Help (Czech), PO Investment, pfinvize.
- **Trading 212's own Czech learn page** "Money-Weighted Rate of Return
  (MWRR) vs Time-Weighted Rate of Return (TWRR)" appeared in WebSearch (not
  fetchable; 403).
- English: finhisaab.com, p2pdash.com.

**Difficulty: strong** for the niche. Four to six Czech pages already match
the exact intent with worked examples, several by trackers with the same
motive as Portfyl. It is winnable only with something non-commodity.

**Recommended target query:** `TWR vs XIRR`.

**Title (48 chars):** `TWR vs XIRR: který výnos portfolia je ten pravý?`
**Meta (119 chars):** `Rozdíl mezi TWR a XIRR na jednom příkladu s vklady a výběry. Kdy použít který výnos a proč se vaše čísla liší od fondů.`

**Gaps.** Show **the same Trading 212 style account computed both ways with
numbers that tie to Portfyl's actual outputs and CZK conversion**; treatment
of dividends, fees and FX; why a broker's own return figure disagrees with
both (needs verification against the real Trading 212 figure before claiming).
Link the page to the S6 methodology page as the source of truth.

#### S10b. Yield on cost

**Candidate queries**

1. yield on cost dividendy
2. YOC dividendy
3. co je YOC
4. yield on cost co to je
5. yield on cost vzorec / výpočet
6. dividendový výnos z pořizovací ceny

**Observed intent.** Informational, and **ambiguous**: for Czech users the
phrase first returns the real-estate meaning (iO Partners, Fkička "FKI").
Dividend-meaning results are a single Czech glossary (**Investplus "Co je
YOC?"**), dividend.watch and dqydj.com (English, the latter a calculator).

**Difficulty: weak** for the dividend meaning in Czech (one glossary, no deep
guide seen), with an intent-clash risk from the real-estate definition.

**Recommended target query:** `yield on cost dividendy` (the added word
disambiguates; "YOC" in the H1).

**Title (47 chars):** `Yield on cost (YOC): jak ho spočítat u dividend`
**Meta (104 chars):** `Co je yield on cost u dividendových akcií, vzorec a příklad v korunách. Kdy je YOC užitečný a kdy klame.`

**Gaps.** A Czech worked example with reinvestment, FX and CZK; the honest
limitations (survivorship, ignores price change, misleading for comparisons);
the contrast with current dividend yield; link to the S9a dividend page.

#### S10c. Comparing a portfolio with an index

Same intent as S9b, see above. **Recommendation: do not publish both as
separate target pages for the same query.** Either merge into S9b, or make
S10c the how-to article and S9b the product page, with S10c targeting
`jak porovnat výkonnost portfolia s indexem` and S9b targeting
`porovnání portfolia s indexem`. Top results for the how-to phrasing are weak
(2014 mesec.cz, a Finax announcement, a glossary).

**Working title (52 chars):** `Jak porovnat portfolio s indexem: postup s příkladem`

---

### S6. Trust pages ("O nás", methodology) and brand query handling

**Brand query "portfyl" (observed)**

- Seznam: "Hledali jsme portfel", "portfyl" offered as an alternative; results
  are Polish wallets and films. Google suggest: "portál ..." only.
- A plain web search for "Portfyl" found no related page (unverified whether
  portfyl.com is indexed yet, I did not check Search Console).
- Conclusion: there is **zero visible brand demand today**, and the name is
  mistaken for "portfel/portál/portfolio". Do not assume branded traffic.

**Handling**

1. Homepage title and H1 carry "Portfyl" plus the descriptor ("Portfyl:
   přehled portfolia pro investory"), so the typo-ish word is attached to the
   category words people do search.
2. Organization and WebSite structured data with `name` Portfyl, and `sameAs`
   to every real profile once they exist. "O nás" is the page that connects
   name, operator, company details and contact (YMYL trust).
3. Register Search Console and Seznam Webmaster, then watch whether
   "portfyl" queries appear; consider a one-line "Portfyl (čti 'portfil')"
   pronunciation hint only if real users ask.
4. "O nás" title `O nás | Portfyl` is fine; it is a trust page, not a query
   target. Needs real names, company details and contact.
5. **Methodology page has non-brand value.** Hedger's methodology page ranks
   on the "twr xirr" query, so a page with exact definitions can earn
   traffic itself. Suggest title `Metodika: jak Portfyl počítá výnos, TWR a XIRR`
   (46 chars) and meta `Jak Portfyl počítá výkonnost portfolia, TWR, XIRR, přepočet měn na CZK a
   dividendy. Vzorce, zdroje dat a známá omezení.` (119 chars). Target query:
   `jak se počítá výnos portfolia` (unverified demand; weak suggest evidence).

## 4. Prioritised order to publish

Ordered by (a) value to a Czech Trading 212 investor, (b) winnability, (c)
dependency on trust and verification.

1. **S6 trust pages** (O nás, methodology). Every other page cites them; ship
   first, even though they will not draw traffic by themselves.
2. **S8 Trading 212 export guide.** Weakest competition on the exact phrases,
   directly feeds the import funnel. Requires a real-export verification pass
   first.
3. **S7 Trading 212 tracking page.** Highest commercial value; medium to
   strong competition, so publish it after S8 and S6 so it has internal links
   and proof. Lead with the non-tax angle.
4. **S9a dividend tracking.** Medium competition, strong product fit.
5. **S10b yield on cost.** Weak competition, quick win, supports S9a.
6. **S9c allocation (currencies/CZK angle).**
7. **S9b benchmark comparison** (merge or split with S10c as described).
8. **S10a TWR vs XIRR.** Last of the explainers: strongest competition, so it
   needs the methodology page and real worked examples first. Do not rush it.

Czech-tax queries ("Trading 212 daně", "podklady pro daňové přiznání")
are the largest visible Czech demand but are **out of scope** for the cloud
edition. Do not build pages for them; the competitors there (Taxero, Trackly,
Investnews, jenakcie.cz, Navigátor úvěru) are established.

## 5. Gap summary (what to differentiate on)

- No tax claims; focus on performance, benchmark, allocation, dividends.
- CZK-first multi-currency views (FX effect on returns, currency exposure).
- CSV import without an API key, with an honest, screenshot-based export
  guide.
- Worked examples that tie to the product's real numbers and to a
  citable methodology page.
- Demo portfolio so a visitor sees the product without registering (verify
  the demo's real behaviour before claiming it).

## 6. Risks

- **YMYL.** All pages touch money decisions. Needs a named operator, real
  author or reviewer, dated content, sources, and a short "not investment
  advice" note. Never state yields or returns as promises.
- **Scaled-content abuse.** S9 and S10 share a template (same intro,
  same CTA). Each page needs its own examples, screenshots and numbers, written
  or reviewed by a person; do not generate variants per broker, ticker or
  index. Eight pages with near-identical structure is itself a signal.
- **Cannibalisation.** S9b versus S10c (same intent), S7 versus S9a ("sledování
  dividend Trading 212"), and S8 versus S7 (both mention the Trading 212
  import). Assign one target query per page in
  `frontend/src/seo/pages/*.js` and do not reuse it.
- **Factual drift.** Trading 212's export UI and limits change; competitor
  features and prices change. Date every guide and recheck quarterly.
  Anything about Trading 212 limits in this file is unverified until Task 0.
- **Plan assumption was wrong.** The plan expected an open Czech market; it is
  not. Re-set the expectation: realistic goal is the long tail and the
  guide queries, not the head terms. Recheck Search Console impressions after
  S1 before committing to S7 head-term wording.
- **Name confusion.** "Portfyl" looks like "portfel" (wallet) or "portfolio".
  Misspelling-friendly wording and entity markup mitigate, but expect low
  brand recall early.
- **Real-estate meaning of "yield on cost".** Page must open by saying it is
  about dividends.
- **Competitor claims.** None verified; do not repeat their feature or price
  claims on a comparison page without checking them. Holdista (named in the
  plan as a pre-launch competitor) was not found in any result (Seznam only
  suggested the spelling); status unverified.
- **Cloud boundary.** Never mention Tax Report or Screener in page copy
  (plan S9).

## 7. Unverified items (checklist)

- All search volumes and relative rankings between queries.
- Google CZ organic results (only Seznam observed).
- Trading 212 export limits and button location (community text only).
- Trading 212's own Czech TWRR/MWRR page content (403; snippet only).
- Alocano page content (429; snippet only).
- Backlink strength of any competitor page.
- Whether portfyl.com is indexed and what Google shows for "portfyl".
- Whether the Portfyl demo works without registration (copy depends on it).

## Related

- [[2026-11-09-portfyl-seo]]
- [[Portfyl]]
