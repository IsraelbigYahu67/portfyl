# Právní dokumenty Portfyl – otevřené body a poznámky pro právníka

Stav k 2026-11-24. Návrhy v této složce jsou **pracovní verze 0.1** a nesmí se
zveřejnit, dokud nejsou vyřešeny body označené **BLOKUJE** a texty
nezkontroluje český advokát (viz brána ve
[../compliance/private-test-legal-status.md](../compliance/private-test-legal-status.md)).

## Dokumenty

| Dokument | Česky | Anglicky |
|---|---|---|
| Obchodní podmínky a podmínky užívání (vč. upozornění „není investiční poradenství“, reklamací, odstoupení a vzorového formuláře) | [podminky-uzivani-cs.md](podminky-uzivani-cs.md) | [terms-of-service-en.md](terms-of-service-en.md) |
| Zásady ochrany osobních údajů a cookies (vč. seznamu zpracovatelů) | [zasady-ochrany-osobnich-udaju-cs.md](zasady-ochrany-osobnich-udaju-cs.md) | [privacy-policy-en.md](privacy-policy-en.md) |

Technická kontrola zásad proti kódu a GDPR/ZEK (2026-11-06), včetně rozporů,
které je nutné opravit před zveřejněním:
[../compliance/2026-11-06-privacy-notice-review.md](../compliance/2026-11-06-privacy-notice-review.md).

## Rozhodnutí provozovatele (2026-10-18)

- Provozovatel a správce: **Jakub Zoubek**, OSVČ, místo podnikání
  Brusinková 1983, 252 28 Černošice.
- Kontakt pro podporu, ochranu osobních údajů a bezpečnost:
  **support@portfyl.com**.
- Služba je jen pro osoby **18+**.
- Placené tarify **jen měsíčně** (změna 2026-10-28): Investor **5,99 €**,
  Pro **9,99 €** měsíčně vč. DPH; roční tarify zatím nejsou. **Zkušební
  období 10 dní**.
- Platby přes **Stripe Managed Payments** (Stripe/Link jako *Merchant of
  Record*) – rozhodnuto 2026-10-28, viz bod 2.
- Data po zrušení účtu smazat **co nejdříve**.
- Dokumenty v **češtině i angličtině**.

## Změny 2026-11-22 (porovnání s konkurencí, výhradně podle práva EU/ČR)

Texty se srovnávaly s dokumenty konkurenční služby, ale přebíralo se jen to,
co vyžaduje nebo opravňuje právo EU (přednostně) a ČR. Ustanovení
v americkém stylu (zákaz refundací, zkrácené promlčení, cizí soud, marketing
bez souhlasu) se nepřebírala.

- **Podmínky:**
  - 3.1 „alespoň 18 let“ (dříve „starší 18 let“). Hranice 18+ je smluvní
    podmínka provozovatele, zákon ji nevyžaduje.
  - 3.6–3.7 pracovní prostor je osobní a sdílení se nenabízí (v kódu je jen
    role owner).
  - 5.5 neúspěšná platba.
  - 6 přepsán podle směrnice 2011/83/EU (čl. 9, 14 odst. 3, 16 písm. a)).
  - 8.2 přesný rozsah exportu; 8.3 a 15.1 nevratné okamžité smazání.
  - 9 pověření a odvolání API klíče.
  - 10 zakázané užití a výjimka pro sdílení vlastních výsledků.
  - Nové čl. 11 (duševní vlastnictví a licence) a 12 (zpětná vazba).
  - 13.1 dostupnost bez dotčení práv z vad.
  - 14 strop odpovědnosti jen vůči podnikatelům.
  - 17.4 salvátorská klauzule.
  - Původní čl. 11–15 jsou nyní 13–17.
- **Zásady:**
  - Brevo jako zpracovatel transakčních e-mailů.
  - Co předáváme Stripe.
  - Oddíl Děti.
  - Konkrétní doby uložení, zálohy „nejvýše 7 dní“.
  - Stížnost i u dozorového úřadu jiného členského státu (čl. 77 GDPR).
  - Záznam o přijetí podmínek.
- **Nové:** stránka Zabezpečení (`security-cs.md` / `security-en.md`, `/security`)
  a `/.well-known/security.txt`. Kontakt pro bezpečnost je support@portfyl.com.
- **Nové otevřené značky** k posouzení:
  - `[[OVĚŘIT]]` u § 1837 a § 1832 OZ (čl. 6) a u licenčních ustanovení
    (čl. 11, § 2358 a násl. OZ);
  - `[[PRÁVNÍK: výše stropu]]` (čl. 14);
  - `[[OVĚŘIT]]` / `[[DOPLNIT]]` u Brevo (smluvní strana, DPA, předání mimo
    EHP, doba uchování);
  - `[[PRÁVNÍK]]` u právního základu záznamu o přijetí podmínek.

## Změny 2026-11-24 (odstoupení od smlouvy, smazání s předplatným, ochrana osobních údajů)

Pozadí: rozhodnutí provozovatele z 2026-11-24 a dvě předběžné AI kontroly
(spotřebitelské právo; ochrana osobních údajů). Nejsou to právní posudky;
články předpisů byly čteny jen v kopiích (EUR-Lex a zakonyprolidi.cz nebyly
dostupné). **Všechno níže je k ověření právníkem.**

**Proč:**

- **SDEU C-234/25 Sky Österreich (9. 7. 2026, tisková zpráva 97/26):** dynamická
  služba, která se přizpůsobuje uživateli, nemůže o právo na odstoupení přijít
  tím, že spotřebitel souhlasí s okamžitým zahájením; při odstoupení dluží jen
  „přiměřenou náhradu“, zásadně podle doby užívání. Dosavadní text „zahájením
  ztratím právo na odstoupení“ byl proto nesprávný a musí zmizet všude (podmínky,
  zaškrtávací pole v pokladně, FAQ). Plný rozsudek nebyl čten.
- **Politika provozovatele:** do 14 dnů od **první placené objednávky** (ne od
  registrace, ne od zkušebního období) se vrací **100 %** zaplacené ceny, bez
  výpočtu a sporů (nad zákonné minimum, které by dovolovalo poměrnou část).
  Po 14 dnech se při dobrovolném ukončení zbývající období nevrací.
- **Smazání pracovního prostoru s předplatným** předplatné ihned ukončí: do 14
  dnů jde o odstoupení a plnou refundaci, později se zbytek období nevrací
  (zákazník to výslovně potvrdí v okně; může místo toho předplatné nejprve
  zrušit a smazat až po konci období). Práva z vadného plnění (směrnice 2019/770)
  zůstávají.
- **Stripe/Link** je prodejce (Merchant of Record). Refund může provést i Link
  (do 60 dnů; po 48 hodinách bez odpovědi provozovatele). Vlastní refund přes
  API je v dokumentaci Stripe popsán, **zrušení předplatného přes
  `DELETE /v1/subscriptions` v Managed Payments v dokumentaci potvrzeno není** a
  musí se vyzkoušet v testovacím režimu před spuštěním plateb (viz
  [../operations/withdrawal-refund.md](../operations/withdrawal-refund.md)).
- **Platby jsou v produkci dál vypnuté** (`PORTFYL_BILLING_ENABLED` není
  nastaveno); nic z toho není nasazeno.

**Podmínky (CS i EN, čísla článků beze změny):**

- Hlavička: „Poslední aktualizace textu 24. 11. 2026“, verze 0.2. (Kód:
  `LEGAL_TERMS_VERSION` / `LEGAL_PRIVACY_VERSION` = `2026-11-24`.)
- Čl. 1: kdo je smluvní strana a vůči komu se uplatňuje odstoupení; značky
  pro DIČ a telefon.
- Čl. 2.3 a 2.4: informativní povaha dat bez vyloučení práv z vad; nová
  informace o funkčnosti a slučitelnosti (§ 1820 odst. 1 písm. r), s) OZ).
- Čl. 3.1 a 15.2: vrácení nevyčerpané části při zrušení účtu nezletilého nebo
  při zrušení bez podstatného porušení.
- Čl. 5.1, 5.3: sjednocení, kdo je prodejce a kdo vrací; zrušení nevrací zaplacené
  období. Čl. 5.4: konkrétní důvody změny ceny, 30 dní předem, právo zrušit
  do 30 dnů od oznámení nebo změny (později z nich).
- **Čl. 6 přepsán:** 14 dnů od první placené objednávky; způsob (jakékoli
  jednoznačné prohlášení, e-mail, smazání pracovního prostoru do 14 dnů,
  vzorový formulář); plná refundace jako politika nad zákonné minimum; kdo
  vrací; po 14 dnech bez refundace. Odstraněna všechna tvrzení, že zahájení
  služby právo ukončuje, i věta o zániku při úplném poskytnutí.
- **Vzorový formulář a poučení:** ověřeno z textu nařízení vlády č. 29/2023 Sb.
  ve znění č. 66/2026 Sb. (účinné od 19. 6. 2026; ruší dřívější č. 363/2013 Sb.).
  Znění poučení a formuláře je převzato, upraveno jen o plnou refundaci. Anglický
  překlad není oficiální (vychází z přílohy I(B) směrnice 2011/83/EU).
  Doplněk pro tlačítko (pokyn č. 4) se vkládá jen tehdy, je-li provozovatel
  povinen tlačítko nabízet; zatím vynecháno (viz „Co musí doplnit provozovatel“).
- Čl. 7.3: vrácení ceny i za dobu po ukončení (čl. 16 odst. 1 směrnice 2019/770);
  čl. 7.4: spotřebitel se může obrátit na soud, i v místě svého bydliště
  (nařízení č. 1215/2012).
- **Čl. 8.3 a 15.1:** nové znění podle rozhodnutí (včetně návrhu věty od
  předběžné kontroly); již neplatí, že lze smazat jen prostor se zrušeným
  předplatným.
- Čl. 9.3, 14.2: povaha dat jako informace, ne vyloučení práv z vad.
- Čl. 13.2 a 16: oprávněné důvody změny, 30 dní, právo ukončit bez sankce do 30
  dnů od oznámení nebo změny (čl. 19 směrnice 2019/770).

**Zásady (CS i EN):**

- Hlavička jako u podmínek; doplněna jen ověřitelná fakta (region Neon,
  údaje o předplatném); neověřené zůstává jako značka (viz seznam níže).
- Nedokončená registrace: čekající záznam o přijetí podmínek a neověřený účet
  se odstraní nejpozději po 30 dnech (kód: `purge_stale_pending`, denní úloha
  `account_deletion_cleanup`).
- Co o předplatném skutečně uchováváme (`billing_customers`, `subscriptions`:
  smažou se s prostorem) a co ne (doklady má Stripe/Link jako samostatný správce;
  `stripe_events` zůstávají, lhůta čeká na rozhodnutí).
- Smazání účtu: seznam výjimek z okamžitého výmazu (otisky proti zneužití
  zkušebního období, `stripe_events`, Stripe/Link, Brevo, PostHog až 1 rok,
  podpora 1 rok, logy 30 dní) a vyřízení námitky/výmazu otisku.
- Google jako příjemce a samostatný správce při přihlášení; skript Google se
  načte už při zobrazení stránky (IP před kliknutím).
- Nový podklad: [../compliance/trial-fingerprint-balancing-test.md](../compliance/trial-fingerprint-balancing-test.md)
  (test vyváženosti; **otevřené rozhodnutí o zkrácení 12 měsíců**, např. na 90 dní).
- `data-processing-inventory.md`: číslo schématu exportu 9 (dříve 8).

## Otevřené body

### 1. Vyřešeno – AI asistent odstraněn

Hostovaný AI asistent (DeepSeek, Čína) byl 2026-10-18 z aplikace úplně
odstraněn, včetně uložených klíčů v databázi (migrace `0024_remove_ai_assistant`).
Podmínky ani zásady proto AI nezmiňují. Pokud se AI v budoucnu vrátí, je nutné
nejdřív vybrat poskytovatele se smlouvou o zpracování (DPA) a zpracováním v EU
nebo v rámci Data Privacy Framework a dokumenty doplnit.

### 2. Vyřešeno – Stripe Managed Payments (Merchant of Record)

Provozovatel zvolil **Stripe Managed Payments**. Prodávajícím vůči zákazníkovi
je společnost ze skupiny Stripe pod značkou **Link** (zákazník vidí „Sold
through Link“, na výpisu `LINK.COM* PORTFYL`). Stripe podle své dokumentace:

- odvádí DPH ve všech státech, vystavuje doklady a posílá potvrzení;
- vyřizuje platební podporu, spory (chargebacky) a správu předplatného na
  webu link.com;
- uplatňuje zákonné lhůty pro odstoupení („regional cooling off periods“);
- smí v odůvodněných případech vrátit platbu **do 60 dnů**; pokud provozovatel
  na dotaz Stripe neodpoví do **48 hodin**, může refundovat bez jeho souhlasu.

Poplatek: 1,5 % (EEA karta) + 3,5 % za Managed Payments + 6,50 Kč za platbu.

Podmínky (čl. 5 a 6) a zásady (část 4) jsou na tuto variantu přepsané.
**K doplnění:** přesný název a sídlo prodávajícího subjektu Stripe/Link –
uvádějí ho podmínky pro kupující na platební stránce.

Zdroje: [How Managed Payments works](https://docs.stripe.com/payments/managed-payments/how-it-works),
[Managed Payments eligibility](https://docs.stripe.com/payments/managed-payments/eligibility).

**Daňová stránka:** provozovatel neprodává spotřebitelům, ale platformě Stripe
(služba osobě v jiném státě EU) – vykazuje se v souhrnném hlášení a do obratu
pro plátcovství se nepočítá. Kvůli přijímaným zahraničním službám (Google
Cloud, Neon atd.) bude provozovatel identifikovanou osobou. Ověřit s daňovým
poradcem.

### 3. Odstoupení od smlouvy a vracení peněz

**Stav k 2026-11-24** (nahrazuje dřívější návrh s poměrnou náhradou): čl. 6
podmínek dává spotřebiteli 14 dnů od první placené objednávky (čl. 9 směrnice
2011/83/EU, § 1829 OZ) a **vrací celou zaplacenou cenu** jako politiku
provozovatele nad zákonné minimum (zákon by dovoloval poměrnou část za dobu
užívání, čl. 14 odst. 3 směrnice, § 1834 OZ). Zahájení služby právo
na odstoupení neukončuje. Text zaškrtávacího pole v pokladně (`Pricing.jsx`,
`ConnectStep.jsx`) a `CHECKOUT_CONSENT_VERSION` mění samostatná změna kódu
(2026-11-24); v pokladně má být výslovný souhlas s okamžitým zahájením a odkaz na
podmínky odstoupení. Doplněno:

- Lhůta běží k jedné smlouvě **jen jednou**; měsíční obnovení novou lhůtu
  nezakládá. Podle rozsudku SDEU C-565/22 (Sofatutor, 5. 10. 2023) to platí
  i po bezplatném zkušebním období, je-li spotřebitel předem jasně informován
  o ceně a o tom, že po zkušebním období začne platit
  ([shrnutí](https://pravniprostor.cz/clanky/obcanske-pravo/dobra-zprava-pro-podnikatele-spatna-pro-spotrebitele-v-pripade-online-predplatnych-bezi-jen-jedna-lhuta-pro-odstoupeni-od-smlouvy)).
- Bez řádného poučení se lhůta prodlužuje až o 12 měsíců.
- Slib 60denních refundací Stripe zůstává z čl. 6.4 vypuštěn (politika třetí
  strany); čl. 6.4 uvádí jen, že vrácení provede provozovatel přes Platebního
  partnera, případně přímo on.

**K ověření:** viz otázky 1 až 6 v oddíle „Otázky pro právníka“ níže.

### 4. Zkušební období bez karty

Návrh předpokládá, že 10denní zkušební období **nevyžaduje kartu** a po
skončení se účet přepne na Free (bez automatického stržení peněz). Pokud by
zkušební období vyžadovalo kartu a automaticky přecházelo v předplatné, je
nutné přepsat čl. 4.3 a před prvním stržením uživatele upozornit.

Od 2026-11-19 je zkušebním tarifem **Pro**. Podmínky (čl. 4.3, 4.5, 4.6)
popisují i to, že zkušební období lze nepřiznat nebo předčasně ukončit, pokud
stejná schránka, síť, účet u brokera nebo historie transakcí už zkušební období
měly. Technické řešení a otevřené otázky jsou v bodě 10.

### 5. Rychlost smazání dat


Od 2026-11-18 kód maže účet **okamžitě** (rozhodl provozovatel): po novém
přihlášení, napsání názvu pracovního prostoru a upozornění s 10sekundovým
časovačem. Odvolání není možné; žádná ochranná lhůta neexistuje (dříve 30 dní).
Pouze žádosti naplánované před touto změnou dokončuje denní úloha. Zálohy
databáze (Neon PITR) dnes drží 6 hodin; pro veřejný provoz plán počítá
s nejméně 7 dny, a právě tuto dobu musí zásady uvádět jako dobu, po kterou
smazaná data mohou zůstat v záloze.

### 6. Identifikační údaje provozovatele

IČO je **67772366** (doplněno 2026-10-18). Chybí ještě informace, zda je
provozovatel **plátcem DPH**. Bez ní nelze
podmínky ani zásady zveřejnit. Ověřit také, že živnostenské oprávnění pokrývá
poskytování softwaru (volná živnost, obor „Poskytování software, poradenství
v oblasti informačních technologií…“).

### 7. Práva k tržním datům

Ceny a fundamentální údaje dnes pocházejí z Yahoo/yfinance, jehož podmínky
komerční použití nedovolují. Před placenou verzí je nutné vybrat licencovaného
poskytovatele dat a podle jeho licence upravit čl. 9.3 a 10 podmínek.

### 8. Úpravy aplikace před spuštěním (technické úkoly)

- ~~Registrace: zaškrtávací pole „Je mi 18 let a souhlasím s obchodními
  podmínkami“ + odkaz na zásady; uložit verzi a čas souhlasu.~~ Hotovo
  2026-11-22: tabulka `terms_acceptances` (migrace `0029`), verze v
  `backend/legal_acceptance.py`; přijetí zásad se ukládá jako „informace
  poskytnuta“, ne jako souhlas podle GDPR. Při každé změně textu podmínek nebo
  zásad zvýšit `LEGAL_TERMS_VERSION` / `LEGAL_PRIVACY_VERSION`.
- Veřejné stránky `/terms`, `/privacy` a nově `/security` (CZ/EN) a odkazy
  v patičce webu i aplikace; `/.well-known/security.txt` (RFC 9116, platnost
  do 2027-10-22 – před vypršením obnovit).
- Pokladna (Stripe Checkout s Managed Payments): výslovná žádost o okamžité
  zahájení služby (k bodu 3); URL obchodních podmínek a zásad nastavit ve
  Stripe (Settings → Public details / Checkout), aby se na platební stránce
  zobrazovaly.
- Ve Stripe Dashboardu udržovat aktuální e-mail podpory (support@portfyl.com)
  a odpovídat na dotazy Stripe do 48 hodin (k bodu 2).
- Případná změna lhůty pro smazání účtu (k bodu 5).

### 9. K ověření právníkem

- Akt o digitálních službách (DSA): rozsah povinností pro malý podnik, který
  ukládá data zadaná uživatelem (kontaktní místo je v čl. 17.1).
- Omezení odpovědnosti (čl. 14): strop nyní jen vůči podnikatelům, vůči
  spotřebiteli odpovědnost podle zákona (§ 1814 a § 2898 OZ, směrnice 93/13/EHS
  příloha bod 1 písm. b)); ověřit výši stropu.
- Rovnocennost české a anglické verze (čl. 17.3).
- Zda smí PostHog odesílat bezcookiové souhrnné události bez souhlasu.
- Ověření DPA, certifikací DPF a regionů u Google Cloud, Firebase, Neon,
  Cloudflare, PostHog a Sentry (a zda je Sentry v produkci zapnutý).
- Lhůta uchování údajů o předplatném podle daňových předpisů.
- Změny zásad z 2026-11-14 (česká i anglická verze): nová kategorie „požadavky
  na brokery“ (název brokera zadaný uživatelem, propojený s účtem, smazaný
  spolu s účtem) v čl. 2 a 6 a nové klíče úložiště `portfyl_intended_broker`,
  `portfyl_preferences_confirmed` a `portfyl_getting_started:<workspaceId>`
  v čl. 8. Vyžadují kontrolu právníkem, zejména zda je lze uvádět mezi
  nezbytným úložištěm bez souhlasu.
- Pověřenec pro ochranu osobních údajů: potvrdit, že není povinný.
- Změny z 2026-11-19 (česká i anglická verze): zkušební období Pro, klíčované
  otisky proti jeho zneužití (čl. 2, 3, 6, 7 zásad), kontrola Cloudflare
  Turnstile při vytvoření účtu (čl. 4 a 8 zásad, čl. 3.5 podmínek) a čl. 4.3,
  4.5, 4.6 podmínek. Otázky jsou v bodě 10.

### 10. Ochrana zkušební doby (HMAC otisky, Turnstile)

Co kód dělá (podklad: [../compliance/data-processing-inventory.md](../compliance/data-processing-inventory.md)):
nové pracovní prostory dostanou 10 dní tarifu Pro bez karty. Aby šlo zkušební
období využít jen jednou na osobu, ukládáme jen klíčované otisky (HMAC-SHA256),
nikdy surový e-mail, IP adresu ani číslo účtu u brokera: kanonický e-mail
(12 měsíců, zůstává i po smazání účtu), IP adresu (30 dní), čísla účtů u
brokerů a identifikátory 5 nejstarších transakcí (12 měsíců). Při shodě se
zkušební období nepřizná, nebo se předčasně ukončí; účet zůstává na Free. Při
vytvoření nového účtu navíc běží kontrola Cloudflare Turnstile.

Otevřené otázky:

1. Test vyváženosti pro oprávněný zájem (čl. 6 odst. 1 písm. f) GDPR) u
   záznamů proti zneužití zkušebního období.
2. Jsou klíčované otisky (HMAC) osobními údaji, a jak se uchování otisku e-mailu
   a účtu u brokera po smazání účtu snáší s právem na výmaz (čl. 17 GDPR)?
3. Čl. 22 GDPR: je automatizované nepřiznání nebo ukončení zkušebního období
   rozhodnutím s významnými účinky?
4. Transparentnost: zkontrolovat znění v aplikaci. Banner a stránka Ceník
   používají tyto čtyři anglické věty (a jejich překlady do 8 jazyků):
   „This account starts on the Free plan, because a free trial was already used
   for this e-mail address or network.“; „Your Pro trial ended early, because
   this broker account already had a free trial in another Portfyl account. Your
   data stays; anything over the Free limits is read-only.“; „Your Pro trial
   ended early, because the same transaction history already had a free trial in
   another Portfyl account. Your data stays; anything over the Free limits is
   read-only.“; „When the trial ends, the account moves to the Free plan unless
   you subscribe. Nothing is charged automatically.“
5. Spotřebitelské právo: tvrzení na úvodní stránce „každý nový účet dostane
   10 dní“ vs. nepřiznání zkušebního období (čl. 4.5 podmínek).
6. Role Cloudflare u Turnstile (zpracovatel, nebo samostatný správce), DPA, a
   zda kontrola zařízení spadá pod výjimku „nezbytně nutné“ podle ePrivacy.
7. Minimalizace údajů u otisků historie transakcí (5 nejstarších transakcí,
   shoda alespoň 3 z 5).

## Otázky pro právníka (souhrn k 2026-11-24)

Číslování je pevné; **NOVÉ** = přibylo 2026-11-24. Starší otázky zůstávají v
bodech 3, 9 a 10 výše a nejsou zde opakovány.

1. **NOVÉ** Kdo je při Stripe Managed Payments „podnikatelem“ (provozovatel,
   nebo Link): komu se odstoupení doručuje, kdo musí dát předsmluvní
   informace a potvrzení na trvalém nosiči?
2. **NOVÉ** Je SaaS „službou“ (čl. 16 písm. a), poměrná platba), nebo
   „digitálním obsahem“ (čl. 16 písm. m))? Tisková zpráva k C-234/25 říká, že
   dynamické předplatné je služba; plný rozsudek nebyl čten.
3. **NOVÉ** Stačí zaškrtávací pole v aplikaci před přesměrováním na Stripe (čl. 8
   odst. 8 směrnice)?
4. **NOVÉ** Je smazání účtu odstoupením? Musí se po smazání uchovat záznam o
   odstoupení a platbě?
5. **NOVÉ** Je trvalé nevrácení zbytku období po 14. dni přiměřené vůči čl. 15.3
   a 16 podmínek (příloha 93/13/EHS bod 1 písm. d))? Je nutná alternativa
   „zrušit ke konci období“ (podmínky ji nabízejí v čl. 5.3 a 8.3)?
6. **NOVÉ** Stav tlačítka pro odstoupení (§ 1830a OZ, v ČR podle zdrojů od
   1. 1. 2027; směrnice od 19. 6. 2026): přímý účinek směrnice? Vložit do poučení
   doplněk z pokynu č. 4 nařízení č. 29/2023 Sb. ve znění č. 66/2026 Sb.?
7. **NOVÉ** Je tvrzení „každý nový účet dostane 10 dní“ klamavé, když lze
   zkušební období nepřiznat (antiabuzivní ochrany)? (Navazuje na bod 10.5.)
8. **NOVÉ** Je klíčovaný HMAC otisk osobním údajem a je 12 měsíců po smazání
   přiměřených (čl. 6 odst. 1 písm. f), recitál 47)? Jak vyřídit námitku/výmaz
   jednoho otisku? Viz
   [../compliance/trial-fingerprint-balancing-test.md](../compliance/trial-fingerprint-balancing-test.md).
9. **NOVÉ** Má minimální důkaz o přijetí podmínek přežít smazání účtu
   (promlčecí lhůty, čl. 17 odst. 3 písm. e))?
10. **NOVÉ** Je Cloudflare Turnstile „nezbytně nutný“ (§ 89 odst. 3 zák.
    č. 127/2005 Sb.)? Je Cloudflare zpracovatel, nebo samostatný správce?
11. **NOVÉ** Je Portfyl poskytovatelem hostingové služby podle aktu o digitálních
    službách (čl. 11, 12, 16)?
12. **NOVÉ** Jaké záznamy o předplatném musí Portfyl vést, když je prodejcem
    Stripe/Link?
13. **NOVÉ** Skript Google pro přihlášení se načte už při zobrazení přihlašovací
    stránky (Google obdrží IP před kliknutím): je to v pořádku podle ePrivacy a
    GDPR a je popis v zásadách (Google jako příjemce a samostatný správce)
    dostatečný?
14. **NOVÉ** Je lhůta 30 dnů pro neukončenou registraci (čekající záznam o přijetí
    podmínek, neověřený účet) přiměřená?
15. **NOVÉ** Jak dlouho smí zůstat technické záznamy `stripe_events` (jen
    identifikátory Stripe) po smazání účtu?
16. **NOVÉ** Antiabuzivní kontrola odmítá jednorázové e-mailové domény; kód to
    nepíše do podmínek (čl. 4.5 uvádí schránku, síť, účet u brokera, historii).
    Doplnit?
17. **NOVÉ** Anglický překlad vzorového formuláře a poučení: stačí, když oficiální
    je jen český text (nařízení č. 29/2023 Sb.)?

## Co musí doplnit provozovatel

Jediný kontrolní seznam. Zástupné značky `[[...]]` v textech se na webu
zobrazují jako „čeká na doplnění“; počítadlo na stránce `/terms` a `/privacy`
ukazuje, kolik jich zbývá. Text se nesmí zveřejnit, dokud nejsou vyřešeny
body označené BLOKUJE a texty nezkontroluje právník.

### A. Zástupné značky v textech

| Soubor (CS / EN) | Článek | Co je potřeba |
|---|---|---|
| podmínky, zásady | hlavička | datum účinnosti (zveřejnění); po zveřejnění zvýšit verzi na „1.0“ a upravit hlavičku |
| podmínky | 1 | zda je provozovatel plátcem DPH, popřípadě DIČ (**BLOKUJE**) |
| podmínky | 1 | telefonní číslo, pokud ho provozovatel má (vyžaduje je vzorové poučení o odstoupení); jinak řádek vypustit |
| podmínky | 3.5 | právník: zda kontrola Turnstile nevyžaduje souhlas |
| podmínky | 4.1 | adresa stránky s ceníkem po jejím zveřejnění |
| podmínky | 4.3 | rozhodnutí: zkušební období zůstává bez karty (jinak přepsat) |
| podmínky | 4.5 | právník: antiabuzivní odepření zkušebního období |
| podmínky, zásady | 5.1; zásady 4 | přesný název a sídlo prodávajícího subjektu Stripe/Link (z podmínek pro kupující na platební stránce) (**BLOKUJE**) |
| podmínky | 6 | právník: otázky (a)–(e); ověřit znění poučení a formuláře a § 1832 OZ |
| podmínky | 11 | právník: ustanovení o licenci (§ 2358 a násl. OZ) a § 66 autorského zákona |
| podmínky | 14.3, 14.4 | právník: výše stropu odpovědnosti pro podnikatele a strop pro spotřebitele |
| podmínky | 17.3 | právník: rovnocennost jazykových verzí |
| zásady | 1 | právník: že není nutný pověřenec |
| zásady | 3 | právník: právní základ záznamu o přijetí podmínek; test vyváženosti u otisků |
| zásady | 4 | Neon: potvrdit region v konzoli (v dokumentaci ověřeno 2026-09-09: AWS `eu-central-1`) |
| zásady | 4 | Cloudflare: zpracovatel, nebo samostatný správce; DPA |
| zásady | 4 | Brevo: název a sídlo smluvní strany, umístění zpracování, DPA, předání mimo EHP (**BLOKUJE**) |
| zásady | 5 | DPA a certifikace DPF u každého dodavatele (Google, Cloudflare, Neon, PostHog, Brevo, Stripe/Link) |
| zásady | 6 | doba uchování záznamů o doručení u Brevo |
| zásady | 6 | právník: výmaz podle čl. 17 vs. uchování otisku po smazání (a rozhodnutí o zkrácení z 12 měsíců, viz B) |
| zásady | 6 | doba uchování `stripe_events` (kód dnes nemaže); rozhodnutí provozovatele |
| zásady | 6 | lhůta pro naše účetní a daňové záznamy a co vedeme mimo aplikaci (daňový poradce) |
| zásady | 7 | právník: postup vyřízení námitky/výmazu otisku |
| zásady | 8 | právník: skript Google při zobrazení přihlášení; Turnstile jako „nezbytně nutný“ |

### B. Další otevřené položky (mimo značky)

- **Tlačítko pro odstoupení (čl. 11a směrnice 2011/83/EU).** Zatím
  nepostaveno; později. Ověřit s právníkem datum závaznosti (otázka 6) a pak ho
  doplnit do aplikace a do poučení.
- **Identifikace provozovatele v patičce webu.** Dnes je v patičce jen e-mail;
  jméno, IČO a adresa jsou jen v podmínkách. Změna UI později.
- **Označení tlačítka závazné objednávky** na platební stránce Stripe
  (§ 1826a odst. 2 OZ: musí jasně říkat, že objednávka zavazuje k platbě): zkontrolovat
  skutečný text mimo repozitář (tlačítko „Upgrade to {plan}“ v aplikaci vede na
  Stripe).
- **Stripe v testovacím režimu před spuštěním plateb:** zrušení předplatného přes
  API v Managed Payments, plný refund včetně daně, chování při opakování
  (podrobně v [../operations/withdrawal-refund.md](../operations/withdrawal-refund.md),
  píše jiná část práce).
- **PostHog:** postup a ověření smazání profilu po smazání účtu (profil může
  zůstat až 1 rok); dnes je analytika v produkci vypnutá.
- **Skript Google pro přihlášení** se načítá hned při zobrazení přihlašovací
  stránky (záměrně, aby okno Google nebylo zablokováno): rozhodnout, zda tak
  zůstane (otázka 13), a popis v zásadách držet v souladu s kódem.
- **Zkrácení uchování otisků proti zneužití zkušební doby** z 12 měsíců
  (otevřené rozhodnutí provozovatele, např. na 90 dní; viz test vyváženosti).
- **Stránka `/.well-known/security.txt`:** po nasazení ověřit, že se podává
  jako `text/plain`; obnovit před 2027-10-22.
- **Úklid nedokončených registrací:** po nasazení ověřit, že denní úloha
  `account_deletion_cleanup` maže čekající záznamy po 30 dnech (a že se
  odstraňují i neověřené účty ve Firebase, pokud to zásady slibují).
- **Zálohy:** doba uchování smazaných dat v záloze (7 dní) musí odpovídat
  skutečné konfiguraci Neon (dnes 6 hodin).
- **Veřejné zveřejnění:** `[[...]]` značky pryč, právník, nová verze
  `LEGAL_TERMS_VERSION` / `LEGAL_PRIVACY_VERSION`.

## Related

- Architecture: [[Portfyl]] · [[Secrets and security]] · [[Account deletion and data lifecycle]]
- Docs: [[legal/podminky-uzivani-cs]] · [[legal/privacy-policy-en]]
