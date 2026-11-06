# Kontrola zásad ochrany osobních údajů – soulad s právem EU a ČR

Datum kontroly: 2026-11-06 \
Kontrolovaný text: [../legal/zasady-ochrany-osobnich-udaju-cs.md](../legal/zasady-ochrany-osobnich-udaju-cs.md)
(verze 0.1, návrh) a anglický protějšek
[../legal/privacy-policy-en.md](../legal/privacy-policy-en.md) \
Stav kódu: `main` @ `6d36b93` \
Autor: technická kontrola (Claude Code), **není to právní stanovisko**. Výsledky
jsou podklad pro advokáta, který texty musí schválit před zveřejněním (viz
[private-test-legal-status.md](private-test-legal-status.md) a
[../legal/poznamky-pro-pravnika.md](../legal/poznamky-pro-pravnika.md)).

## Shrnutí

Struktura zásad odpovídá čl. 13 a 14 GDPR a pokrývá většinu povinných
náležitostí. Text ale **na čtyřech místech nepopisuje skutečné chování
aplikace** a chybí v něm několik náležitostí, které GDPR výslovně vyžaduje.
Nejzávažnější je analytika PostHog: po **odmítnutí** souhlasu dál odesílá
události (bezcookiový režim), zatímco zásady i banner tvrdí opak.

| # | Zjištění | Závažnost | Typ opravy |
|---|---|---|---|
| A1 | PostHog posílá události i po odmítnutí souhlasu | **vysoká – blokuje zapnutí analytiky** | kód (doporučeno) nebo text + právní posouzení |
| A2 | Analytika je popsána jako „anonymní“, ve skutečnosti je pseudonymní | střední | text zásad + banneru |
| A3 | Volba souhlasu je cookie (180 dní), ne localStorage | nízká–střední | text |
| A4 | Tabulka cookies a úložiště není úplná | střední | text |
| B1 | Chybí informace o povinnosti poskytnout údaje a důsledcích (čl. 13 odst. 2 písm. e) | střední | text |
| B2 | Chybí způsob získání kopie záruk při předání mimo EU (čl. 13 odst. 1 písm. f) | nízká–střední | text |
| B3 | Právo vznést námitku není uvedeno odděleně (čl. 21 odst. 4) | nízká–střední | text |
| B4 | Chybí odkaz na § 89 odst. 3 zákona č. 127/2005 Sb. | nízká | text |
| B5 | Informace se neposkytují v okamžiku získání údajů (registrace, banner) | střední | kód |
| B6 | Lhůta pro odpověď na žádost neuvádí možné prodloužení (čl. 12 odst. 3) | nízká | text |
| C | Nevyřešená rozhodnutí (`[[DOPLNIT]]`, `[[ROZHODNOUT]]`) | blokuje zveřejnění | rozhodnutí provozovatele / právníka |
| D | Rozpory mezi interními dokumenty | nízká (interní) | dokumentace |

Co je v pořádku, je shrnuto na konci (oddíl E).

## Použitý právní rámec

- **Nařízení (EU) 2016/679 (GDPR)** – zejména čl. 5, 6, 7, 12–14, 17, 21,
  28, 37, 44–46.
- **Zákon č. 110/2019 Sb., o zpracování osobních údajů** – mj. § 7 (věk 15 let
  pro souhlas dítěte se službami informační společnosti).
- **Zákon č. 127/2005 Sb., o elektronických komunikacích, § 89 odst. 3** –
  ukládání informací do koncového zařízení uživatele nebo přístup k nim
  jen se souhlasem (opt-in od 1. 1. 2022), s výjimkou technicky nezbytného
  uložení. Provádí čl. 5 odst. 3 směrnice 2002/58/ES (ePrivacy).
- **EDPB Guidelines 2/2023 on Technical Scope of Art. 5(3) of ePrivacy
  Directive** – za „přístup“ ke koncovému zařízení považují i případy, kdy
  skript v prohlížeči z pokynu poskytovatele odešle data (pixely, tracking
  bez cookies, fingerprinting), nejen cookies.
- **EDPB Guidelines 05/2020 on consent** – informovanost a dobrovolnost
  souhlasu, odmítnutí stejně snadné jako udělení.

---

## A. Rozpory mezi textem a skutečným chováním kódu

### A1. PostHog odesílá události i po odmítnutí souhlasu

**Co říkají zásady:**

- čl. 2, tabulka: „Analytika (jen se souhlasem) … automaticky, pouze pokud
  souhlasíte“;
- čl. 3: právní základ analytiky je **souhlas** – čl. 6 odst. 1 písm. a);
- čl. 4: PostHog – „analytika používání – **jen pokud udělíte souhlas**“;
- čl. 8: „Bez souhlasu se analytické cookies neukládají.“ (pravdivé, ale
  zavádějící – viz níže).

Banner ([analyticsCopy.js](../../frontend/src/analytics/analyticsCopy.js))
navíc říká „Volitelná analytika … Odmítnutí nijak neomezí funkčnost“, takže
uživatel rozumně očekává, že po odmítnutí se nic neměří.

**Co dělá kód:**

- [analyticsClient.js](../../frontend/src/analytics/analyticsClient.js),
  `buildOptions()`: `cookieless_mode: "on_reject"` a při odmítnutí
  `persistence: "memory"`;
- `loadPostHogAdapter()`: při `consent === "rejected"` SDK **inicializuje**
  a zavolá `opt_out_capturing()`. V režimu `on_reject` to podle chování
  posthog-js znamená přepnutí do bezcookiového sběru, ne ukončení sběru;
- [AnalyticsProvider.jsx](../../frontend/src/analytics/AnalyticsProvider.jsx):
  `capture()` se blokuje jen ve stavu `pending`; ve stavu `rejected` se
  události posílají adaptéru;
- [data-processing-inventory.md](data-processing-inventory.md) to potvrzuje:
  „rejected traffic sends cookieless aggregate events by design“.

Po odmítnutí tedy prohlížeč dál posílá na `eu.i.posthog.com` události
z povoleného seznamu. Server PostHogu z IP adresy, User-Agentu a denní soli
počítá hash, aby rozlišil návštěvníky. IP adresa a hash jsou osobní údaje.

**Proč je to problém:**

1. **Nepravdivá informace** – rozpor s čl. 5 odst. 1 písm. a) (transparentnost)
   a čl. 13 GDPR. Uživatel, který odmítl, je zpracováván, aniž by se to
   dozvěděl.
2. **ePrivacy / § 89 odst. 3 ZEK** – podle EDPB 2/2023 i bezcookiové
   odeslání dat skriptem z prohlížeče spadá pod pravidlo o přístupu ke
   koncovému zařízení. Analytika není „nezbytná“ pro poskytnutí služby, takže
   výjimka se neuplatní a vyžaduje se souhlas. Ten uživatel výslovně odmítl.
3. **Právní základ podle GDPR** – zpracování po odmítnutí nemůže stát na
   souhlasu. Šlo by jen o oprávněný zájem (čl. 6 odst. 1 písm. f), který
   zásady neuvádějí, nemá zpracovaný balanční test a i tak by neobstál
   proti bodu 2.
4. **Důvěryhodnost banneru** – odmítnutí, které nic nezmění, je přesně typ
   praktiky, na kterou se zaměřují dozorové úřady (dark patterns).

**Aktuální dopad:** zatím žádný. `VITE_POSTHOG_KEY` / `VITE_POSTHOG_HOST`
nejsou nastavené ve `frontend/.env.local` a produkční build proto používá
no-op adaptér. Commit `6d36b93` ale build args do Dockerfile a Cloud Build už
zapojil, takže analytiku zapne jediný řádek v `.env.local`.

**Doporučení (v pořadí preference):**

1. **Kód – při odmítnutí nic neposílat.** V `defaultAdapterFactory()`
   (`AnalyticsProvider.jsx`) vracet pro `consent === "rejected"`
   `createNoopAdapter()`, nebo v `loadPostHogAdapter()` pro odmítnutí vůbec
   neinicializovat SDK a odstranit `cookieless_mode`. Upravit testy
   (`analyticsClient.test.js`, `AnalyticsProvider.test.jsx`) a odstavec
   v `data-processing-inventory.md` a `docs/operations/posthog-activation-analytics.md`.
   Zásady pak platí, jak jsou napsané.
2. Pokud provozovatel bezcookiové měření po odmítnutí chce zachovat:
   nechat ho posoudit advokátem (ePrivacy), doplnit do zásad samostatný
   účel, právní základ a balanční test, a přepsat banner, aby bylo jasné, co
   odmítnutí znamená. Toto řešení je právně rizikové a nedoporučuje se.

**Do vyřešení A1 nenastavovat `VITE_POSTHOG_KEY` v žádném prostředí.**

### A2. „Anonymní“ analytika je ve skutečnosti pseudonymní

**Zásady:** čl. 2 „anonymní události o používání aplikace“; banner
„měřit anonymní použití produktu“ / „anonymous product use“.

**Kód:** po přijetí souhlasu
[AuthProvider.jsx](../../frontend/src/auth/AuthProvider.jsx) volá
`analytics.identify(user.id)` s interním ID uživatele a PostHog ukládá
`ph_*_posthog` s `distinct_id`. Události jsou tedy přiřazené ke
konkrétnímu účtu, který Portfyl umí ztotožnit s e-mailem.

**Proč je to problém:** anonymní údaje nespadají pod GDPR (recitál 26).
Pseudonymní údaje ano (čl. 4 bod 5). Slovo „anonymní“ je zavádějící
a v souhlasu podstatné – uživatel se rozhoduje na základě nepravdivé
informace (EDPB 05/2020, informovanost souhlasu).

**Doporučení:** v zásadách (CZ i EN) i v banneru nahradit „anonymní“ za
„pseudonymní“ / „bez jména a e-mailu“ a výslovně uvést: „Po přihlášení
události spojujeme s interním identifikátorem vašeho účtu, ne s e-mailem
ani jménem.“

### A3. Volba souhlasu je cookie, ne localStorage

**Zásady, čl. 8:** „volba souhlasu s analytikou (localStorage) … dokud ji
nezměníte“.

**Kód:** [consent.js](../../frontend/src/analytics/consent.js) ukládá
**cookie** `portfyl_analytics_consent` s `Max-Age=15552000` (**180 dní**),
v produkci s `Domain=.portfyl.com`, `Secure`, `SameSite=Lax`.

**Doporučení:** v tabulce uvést název `portfyl_analytics_consent`, typ cookie
(první strana, sdílená mezi `portfyl.com` a subdoménami) a dobu 180 dní.
Uložení volby je technicky nezbytné a souhlas nevyžaduje, ale popis musí být
přesný.

### A4. Tabulka cookies a úložiště není úplná

Zásady v čl. 8 uvádějí jen `__Host-portfyl_session`, pět klíčů `sb_*`,
volbu souhlasu a `__cf_bm`. V kódu jsou navíc:

| Název | Typ | Kdy | Účel | Doba |
|---|---|---|---|---|
| `ph_<projekt>_posthog` | cookie + localStorage (PostHog) | jen po přijetí analytiky | identifikátor návštěvníka/relace pro analytiku | dle PostHogu, typicky 1 rok |
| `portfyl_captured_once:*` | localStorage | jen po přijetí analytiky | aby se jednorázové události neposlaly dvakrát | do smazání |
| `portfyl_activation_v1:<user>:<workspace>` | localStorage | jen po přijetí analytiky ([activationState.js](../../frontend/src/analytics/activationState.js)) | stav aktivace pro analytiku | do smazání |
| `portfyl_landing_language` | localStorage | vždy | jazyk úvodní stránky a právních textů | do smazání |
| `sb_view_mode` | localStorage | vždy | režim zobrazení | do smazání |
| `sb_dashboard_layout_v3`, `sb_dashboard_widget_order_v4`, `sb_dashboard_widgets_hidden` | localStorage | vždy | rozložení dashboardu | do smazání |
| `sb_stock_report_sections`, `sb_stock_report_tabs` | localStorage | vždy | nastavení detailu akcie | do smazání |
| `CF_Authorization` (Cloudflare Access) | cookie | jen v soukromém testu na `app.portfyl.com` | přístup testerů | dle Cloudflare Access |
| `portfyl_session` | cookie | jen mimo HTTPS (lokální vývoj) | relace | 30 dní |

Pozn.: tři položky s analytikou ukládá jen při souhlasu, takže je zařadit pod
„Analytické (jen se souhlasem)“. Ostatní spadají pod výjimku pro
nezbytné/uživatelem požadované funkce (§ 89 odst. 3 ZEK), ale mají být
uvedené – buď výčtem, nebo souhrnem „další nastavení vzhledu a rozložení
(klíče `sb_*`)“. `portfyl_session` se v produkci nepoužívá a do veřejných
zásad nepatří.

---

## B. Chybějící náležitosti podle GDPR a českého práva

### B1. Povinnost poskytnout údaje a důsledky neposkytnutí – čl. 13 odst. 2 písm. e)

Zásady neuvádějí, zda je poskytnutí údajů zákonným nebo smluvním požadavkem
a co se stane, když je uživatel neposkytne.

**Návrh textu (nový odstavec na konci čl. 2):**
> Poskytnutí e-mailu je nutné k vytvoření účtu – bez něj vám Službu nemůžeme
> poskytovat. Údaje o portfoliu, připojení k brokerovi a Discord jsou
> dobrovolné; bez nich jen nebudou dostupné příslušné funkce. Souhlas
> s analytikou je zcela dobrovolný a na funkčnost nemá vliv.

### B2. Kopie vhodných záruk při předání mimo EU – čl. 13 odst. 1 písm. f)

Čl. 5 uvádí DPF a standardní smluvní doložky, ale ne „prostředky, jak
získat jejich kopii nebo kde byly zpřístupněny“.

**Návrh:** doplnit větu „Kopii standardních smluvních doložek vám na žádost
poskytneme na support@portfyl.com; seznam certifikovaných společností DPF je
na https://www.dataprivacyframework.gov.“

### B3. Právo vznést námitku musí být uvedeno odděleně – čl. 21 odst. 4

Čl. 21 odst. 4 GDPR vyžaduje, aby na právo vznést námitku byl subjekt
„výslovně upozorněn … jasně a odděleně od jakýchkoli jiných informací“.
V zásadách je jen jako jedna z odrážek v čl. 7.

**Návrh:** samostatný, vizuálně oddělený odstavec, např. tučně:
> **Právo vznést námitku.** Proti zpracování, které provádíme na základě
> oprávněného zájmu (zabezpečení, ochrana právních nároků), můžete kdykoli
> vznést námitku na support@portfyl.com. Zpracování ukončíme, pokud
> neprokážeme závažné oprávněné důvody, které převažují nad vašimi zájmy.

### B4. Chybí odkaz na zákon o elektronických komunikacích

Úvod zásad cituje jen GDPR a zákon č. 110/2019 Sb. Pravidla pro cookies
a úložiště v prohlížeči (čl. 8) vycházejí z § 89 odst. 3 zákona
č. 127/2005 Sb. Doporučuji ho v úvodu i v čl. 8 doplnit.

### B5. Informace se uživateli nedávají v okamžiku získání údajů

Čl. 13 odst. 1 GDPR: informace se poskytují „v okamžiku získání osobních
údajů“.

- **Registrace** – ve `frontend/src/auth/` není odkaz na `/privacy` ani na
  `/terms` a chybí potvrzení věku 18+. Poznámky pro právníka (bod 8) to už
  požadují; dosud není implementováno. Uživatel tak zásady při registraci
  vůbec nevidí (odkazy jsou jen v Nastavení a v patičce veřejných stránek).
- **Banner souhlasu** ([ConsentBanner.jsx](../../frontend/src/analytics/ConsentBanner.jsx))
  neodkazuje na `/privacy` (čl. 8 zásad). Souhlas má být informovaný – banner
  by měl odkazovat na podrobnosti: kdo (PostHog, EU), co se měří, jak dlouho.

**Doporučení:** na registrační formulář přidat zaškrtávací pole „Je mi
18 let a souhlasím s obchodními podmínkami“ s odkazy na `/terms` a
`/privacy`, uložit verzi a čas potvrzení; do banneru přidat odkaz
„Podrobnosti“ na `/privacy#8-cookies-a-uloziste-v-prohlizeci` (dle
skutečného ID nadpisu).

### B6. Lhůta pro odpověď na žádost – čl. 12 odst. 3

Zásady: „Odpovíme do 1 měsíce.“ GDPR umožňuje prodloužení o další dva
měsíce u složitých žádostí, o kterém je nutné subjekt informovat. Doplnit:
„… v odůvodněných případech můžeme lhůtu prodloužit o další dva měsíce;
o prodloužení vás předem informujeme.“

---

## C. Nevyřešená místa v textu (blokují zveřejnění)

| Místo v zásadách | Co chybí | Podklad z kontroly |
|---|---|---|
| čl. 1 – pověřenec `[[PRÁVNÍK: ověřit]]` | potvrzení, že DPO není povinný | Čl. 37 GDPR: Portfyl není orgán veřejné moci, nezpracovává zvláštní kategorie údajů ve velkém rozsahu a jeho hlavní činností není rozsáhlé systematické monitorování. Povinnost DPO pravděpodobně nevzniká – potvrdit advokátem. |
| čl. 4 – Google Cloud `[[OVĚŘIT]]` | region | **Ověřeno 2026-11-06:** produkční Cloud Run služba `portfyl` běží v `europe-west1` (Belgie). Značku lze odstranit. |
| čl. 4 – Neon `[[OVĚŘIT]]` | region | ověřit v konzoli Neonu |
| čl. 4 – Sentry `[[OVĚŘIT …]]`, `[[DOPLNIT]]` | zda je zapnutý, region | **Ověřeno 2026-11-06:** produkční služba nemá `SENTRY_DSN` a `frontend/.env.local` nemá `VITE_SENTRY_DSN` → Sentry v produkci **neběží**. Řádek lze ze zásad odstranit, nebo ponechat s poznámkou „pokud bude zapnut“ – lepší odstranit a doplnit až se zapnutím. |
| čl. 4 – Platební partner `[[DOPLNIT]]` | přesný název a sídlo subjektu Stripe/Link | z podmínek pro kupující na platební stránce |
| čl. 5 – `[[PRÁVNÍK: …]]` | DPA a certifikace DPF u každého dodavatele | Certifikaci každého dodavatele (Google, Cloudflare, Neon, PostHog) ověřit v seznamu na dataprivacyframework.gov; DPA u všech uzavřít/přijmout v konzolích. |
| čl. 6 – zálohy `[[DOPLNIT: 7 dní]]` | skutečná doba PITR | dnes 6 hodin (private-test baseline); pro veřejný provoz plán 7 dní – uvést hodnotu, která bude v provozu |
| čl. 6 – doklady `[[PRÁVNÍK: doplnit lhůtu]]` | lhůta uchování údajů o předplatném | DPH: 10 let (§ 35 zákona o DPH), daňová evidence OSVČ: lhůta pro stanovení daně (§ 148 daňového řádu). Protože doklady vystavuje Stripe jako MoR, potvrdit s daňovým poradcem, co musí uchovávat sám provozovatel. |
| čl. 6 – smazání `[[ROZHODNOUT …]]` | 30denní lhůta nebo okamžité smazání | Kód dnes maže **po 30 dnech** s možností zrušení. Obě varianty jsou s čl. 17 („bez zbytečného odkladu“) slučitelné, pokud je lhůta v zásadách uvedena a odůvodněna (ochrana před omylem / zneužitím účtu). Text musí odpovídat kódu. |
| čl. 8 – `[[PRÁVNÍK: … bezcookiové …]]` | posouzení bezcookiových událostí | viz A1 – doporučeno vypnout v kódu, pak poznámku odstranit |
| čl. 10 – `[[DOPLNIT: URL]]` | adresa zásad | `https://portfyl.com/privacy` (stránka už existuje, `Legal.jsx`) |

---

## D. Rozpory mezi interními dokumenty

Nejde přímo o soulad zásad se zákonem, ale advokát pracuje s
`data-processing-inventory.md` jako s technickým podkladem, takže by měl
odpovídat zásadám:

- **Kontakt:** inventura uvádí `tom.zoubek@gmail.com`, zásady
  `support@portfyl.com`.
- **Věk:** inventura „No 18+ product restriction is intended“, zásady
  a poznámky pro právníka „jen 18+“.
- **Identita správce:** inventura „not decided“, zásady už uvádějí jméno,
  IČO a adresu.
- **Brokeři:** inventura zmiňuje jen Trading 212 a IBKR, zásady i kód
  (`PORTFYL_ETORO_APP_KEY`, router `etoro`) i eToro.
- **Zkušební období:** poznámky pro právníka (rozhodnutí 2026-10-28) uvádějí
  10denní zkušební období, CLAUDE.md a ceník „bez zkušebního období“. Týká se
  hlavně obchodních podmínek, ale je třeba sjednotit.

Doporučení: aktualizovat `data-processing-inventory.md` (oddíl „Current
operator and release status“ a tabulku služeb) a sjednotit informaci o
zkušebním období.

---

## E. Co je v pořádku

- **Správce a kontakt** (čl. 13 odst. 1 písm. a) – jméno, IČO, adresa, e-mail.
- **Účely a právní základy** – jasná tabulka; u oprávněného zájmu je uveden
  konkrétní zájem (bezpečný provoz, ochrana nároků), jak vyžaduje čl. 13
  odst. 1 písm. d).
- **Příjemci** – rozlišení zpracovatelů a samostatných správců, včetně
  regionů; tržní data správně popsána jako bez osobních údajů.
- **Předávání mimo EU** – uveden mechanismus (DPF / SCC); chybí jen B2.
- **Doby uchování** – konkrétní lhůty pro většinu kategorií; logy 30 dní
  odpovídají `_Default` bucketu Cloud Logging (`_Required` bucket s 400 dny
  obsahuje auditní záznamy Google Cloud o správě projektu, ne požadavky
  uživatelů – lze zmínit pro úplnost).
- **Práva subjektů** – všechna práva podle čl. 15–22, stížnost u ÚOOÚ
  s adresou, samoobslužný export (JSON) a smazání v aplikaci.
- **Automatizované rozhodování** – výslovně vyloučeno.
- **Věk** – služba 18+, tedy nad hranicí 15 let podle § 7 zákona
  č. 110/2019 Sb. (zbývá implementovat potvrzení při registraci, B5).
- **Zabezpečení** – popis odpovídá implementaci (KMS, RLS, odvolatelné relace,
  redakce logů).
- **Banner souhlasu** – před rozhodnutím se nic neodesílá ani neukládá,
  tlačítka „Přijmout“ a „Odmítnout“ jsou rovnocenná, volbu lze změnit
  z patičky („Nastavení analytiky“).
- **Chybějící AI** – AI asistent byl odstraněn (migrace
  `0024_remove_ai_assistant`) a zásady ho správně nezmiňují.

---

## Doporučené pořadí kroků

1. **A1 v kódu** – při odmítnutí nepoužívat PostHog vůbec; upravit testy
   a inventuru. Do té doby nenastavovat `VITE_POSTHOG_*`.
2. **A2–A4, B1–B4, B6 v textu** – opravit CZ i EN verzi současně (Legal.jsx
   čte oba soubory při buildu, takže změna se projeví po dalším deployi).
3. **B5 v kódu** – odkazy a potvrzení 18+ při registraci, odkaz v banneru.
4. **C** – doplnit rozhodnutí a ověřené údaje, odstranit značky `[[…]]`.
5. **D** – sjednotit interní dokumenty.
6. Předat advokátovi tento report spolu s
   [../legal/poznamky-pro-pravnika.md](../legal/poznamky-pro-pravnika.md).
