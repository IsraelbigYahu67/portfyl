# Právní dokumenty Portfyl – otevřené body a poznámky pro právníka

Stav k 2026-10-28. Návrhy v této složce jsou **pracovní verze 0.1** a nesmí se
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

Návrh (čl. 6) dává spotřebiteli zákonných 14 dní od první platby, výslovnou
žádost o okamžité zahájení plnění (§ 1823 OZ) a při odstoupení vrací cenu
sníženou o poměrnou část za dobu užívání (§ 1834 OZ). Doplněno:

- Lhůta běží k jedné smlouvě **jen jednou**; měsíční obnovení novou lhůtu
  nezakládá. Podle rozsudku SDEU C-565/22 (Sofatutor, 5. 10. 2023) to platí
  i po bezplatném zkušebním období, je-li spotřebitel předem jasně informován
  o ceně a o tom, že po zkušebním období začne platit
  ([shrnutí](https://pravniprostor.cz/clanky/obcanske-pravo/dobra-zprava-pro-podnikatele-spatna-pro-spotrebitele-v-pripade-online-predplatnych-bezi-jen-jedna-lhuta-pro-odstoupeni-od-smlouvy)).
- Bez řádného poučení se lhůta prodlužuje až o 12 měsíců.
- Nový čl. 6.4 popisuje 60denní refundace Stripe.

**K ověření:**

- Vůči komu spotřebitel odstupuje, když je prodávajícím Stripe/Link (MoR), a
  zda je čl. 6 v souladu s podmínkami Linku pro kupující.
- Zda provozovatel musí mít na webu vlastní **funkci pro odstoupení** podle
  směrnice (EU) 2023/2673 (podle sekundárních zdrojů od 19. 6. 2026 – ověřit
  datum i transpozici v ČR), nebo ji za něj zajišťuje Stripe jako prodávající.
- Zda postačí poměrná náhrada, nebo nabídnout plnou refundaci.
- Jak formulovat výslovnou žádost o okamžité zahájení plnění na platební
  stránce Stripe (vlastní text nebo zaškrtávací pole v nastavení Checkout).

### 4. Zkušební období bez karty

Návrh předpokládá, že 10denní zkušební období **nevyžaduje kartu** a po
skončení se účet přepne na Free (bez automatického stržení peněz). Pokud by
zkušební období vyžadovalo kartu a automaticky přecházelo v předplatné, je
nutné přepsat čl. 4.3 a před prvním stržením uživatele upozornit.

### 5. Rychlost smazání dat

Dnešní kód maže účet **až po 30denní lhůtě**, během níž lze smazání zrušit
(ochrana před omylem nebo zneužitím účtu). Zálohy databáze (Neon PITR) dnes
drží 6 hodin; pro veřejný provoz plán počítá s nejméně 7 dny. Provozovatel
chce mazat co nejdříve. **Možnosti:** (a) zkrátit lhůtu na 7 dní, (b) mazat
ihned po novém přihlášení a potvrzení. V zásadách je místo
`[[ROZHODNOUT]]`; změna kódu je samostatný úkol.

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

- Registrace: zaškrtávací pole „Je mi 18 let a souhlasím s obchodními
  podmínkami“ + odkaz na zásady ochrany osobních údajů; uložit verzi a čas
  souhlasu.
- Veřejné stránky `/terms` a `/privacy` (CZ/EN) a odkazy v patičce webu i
  aplikace.
- Pokladna (Stripe Checkout s Managed Payments): výslovná žádost o okamžité
  zahájení služby (k bodu 3); URL obchodních podmínek a zásad nastavit ve
  Stripe (Settings → Public details / Checkout), aby se na platební stránce
  zobrazovaly.
- Ve Stripe Dashboardu udržovat aktuální e-mail podpory (support@portfyl.com)
  a odpovídat na dotazy Stripe do 48 hodin (k bodu 2).
- Případná změna lhůty pro smazání účtu (k bodu 5).

### 9. K ověření právníkem

- Akt o digitálních službách (DSA): rozsah povinností pro malý podnik, který
  ukládá data zadaná uživatelem (kontaktní místo je v čl. 15.1).
- Omezení odpovědnosti vůči spotřebiteli (čl. 12.3) a § 2898 OZ.
- Rovnocennost české a anglické verze (čl. 15.3).
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
