# Právní dokumenty Portfyl – otevřené body a poznámky pro právníka

Stav k 2026-10-19. Návrhy v této složce jsou **pracovní verze 0.1** a nesmí se
zveřejnit, dokud nejsou vyřešeny body označené **BLOKUJE** a texty
nezkontroluje český advokát (viz brána ve
[../compliance/private-test-legal-status.md](../compliance/private-test-legal-status.md)).

## Dokumenty

| Dokument | Česky | Anglicky |
|---|---|---|
| Obchodní podmínky a podmínky užívání (vč. upozornění „není investiční poradenství“, reklamací, odstoupení a vzorového formuláře) | [podminky-uzivani-cs.md](podminky-uzivani-cs.md) | [terms-of-service-en.md](terms-of-service-en.md) |
| Zásady ochrany osobních údajů a cookies (vč. seznamu zpracovatelů) | [zasady-ochrany-osobnich-udaju-cs.md](zasady-ochrany-osobnich-udaju-cs.md) | [privacy-policy-en.md](privacy-policy-en.md) |

## Rozhodnutí provozovatele (2026-10-18)

- Provozovatel a správce: **Jakub Zoubek**, OSVČ, místo podnikání
  Brusinková 1983, 252 28 Černošice.
- Kontakt pro podporu, ochranu osobních údajů a bezpečnost:
  **support@portfyl.com**.
- Služba je jen pro osoby **18+**.
- Placené tarify **měsíčně i ročně**, **zkušební období 10 dní**.
- Data po zrušení účtu smazat **co nejdříve**.
- Dokumenty v **češtině i angličtině**.

## Otevřené body

### 1. Vyřešeno – AI asistent odstraněn

Hostovaný AI asistent (DeepSeek, Čína) byl 2026-10-18 z aplikace úplně
odstraněn, včetně uložených klíčů v databázi (migrace `0024_remove_ai_assistant`).
Podmínky ani zásady proto AI nezmiňují. Pokud se AI v budoucnu vrátí, je nutné
nejdřív vybrat poskytovatele se smlouvou o zpracování (DPA) a zpracováním v EU
nebo v rámci Data Privacy Framework a dokumenty doplnit.

### 2. Platby: Stripe Managed Payments (Merchant of Record)

**Rozhodnutí:** návrhy podmínek a zásad nyní počítají se **Stripe Managed
Payments** jako prodejcem (*Merchant of Record*, MoR). Důvody jsou v rešerši
[../research/payment-providers-2026-09-28.html](../research/payment-providers-2026-09-28.html)
(GA od 22. 4. 2026, ČR je podporovaná země prodejce, Stripe omezuje jen
„investment and brokerage services“, což read-only tracker není).

**„Stripe“ neznamená jedno a totéž.** Je třeba rozlišit dva produkty:

| | Stripe Billing (+ Stripe Tax) | Stripe Managed Payments |
|---|---|---|
| Kdo prodává zákazníkovi | **provozovatel** (Jakub Zoubek); Stripe je jen platební brána | **Sold through Link, LLC** („Link SMP“), přidružená společnost Stripe; zákazník vidí „Sold through Link“ |
| DPH | provozovatel (české místo plnění do 10 000 € přeshraničních B2C prodejů v EU ročně, pak OSS) | Stripe vypočte, vybere a odvede DPH ve více než 80 zemích |
| Doklady zákazníkovi | provozovatel | Link (potvrzení, faktury, dobropisy posílá Link) |
| Podvody, spory, chargebacky | provozovatel | Stripe (sám rozhoduje, zda spor napadne, nebo přijme) |
| Podpora k platbám a předplatnému | provozovatel | Link (support.link.com); podpora k produktu zůstává provozovateli |
| Vracení peněz | provozovatel podle zákona a svých podmínek | Link podle svých podmínek; Stripe smí v některých případech vrátit platbu **do 60 dnů** i bez provozovatele (a také tehdy, když provozovatel do 48 hodin neodpoví na dotaz podpory) |
| Výpis z karty | podle nastavení účtu | **LINK.COM\*** + označení prodejce |
| Pokladna a předplatné | i vlastní formulář (Elements), vlastní doména | **jen Stripe Checkout / Payment Links**, bez vlastní domény; předplatné jen přes Checkout |
| Poplatek (EEA karta, orientačně) | ~2,7 % + 6,50 Kč | 1,5 % + 3,5 % + 6,50 Kč |
| Daňový pohled provozovatele | prodej spotřebitelům | prodej služby firmě (Link SMP) – souhrnné hlášení, viz rešerše |

Předchozí verze této poznámky („Stripe je jen platební brána“) platila jen pro
Stripe Billing. Pro Managed Payments neplatí.

**Ověřeno na stripe.com / link.com (2026-10-19):**

- Prodávajícím je **Sold through Link, LLC**, přidružená společnost Stripe;
  dříve **LemonSqueezy LLC** (faktury vydané před 6. 4. 2026 mohou nést
  starý název). Zdroj: [Stripe Support – Why is Sold through Link, LLC the
  legal entity on my invoice…](https://support.stripe.com/questions/why-is-sold-through-link-llc-the-legal-entity-on-my-invoice-for-stripe-managed-payments-fees)
  a [Link Terms – Sold Through Link Terms / Purchase Terms](https://link.com/terms#sold-through-link-terms).
- Podle podmínek Link je pro daňové účely jediným plněním Link SMP vůči
  zákazníkovi produkt prodejce (Business User); prodejce dál odpovídá za
  produkt (dodání, kvalitu, vracení), Link neposkytuje podporu k používání
  produktu. Vracení peněz Link posuzuje „case-by-case“, za nevyužité období
  předplatného nevrací, pokud to nevyžaduje zákon; je-li politika prodejce
  přísnější, platí politika Linku. Spotřebitel v EU má 14denní „cooling off
  period“ od získání přístupu, uplatňuje ji u podpory Linku. Předplatné lze
  spravovat a zrušit v účtu Link; smazání účtu Link předplatné ruší.
  Zdroj: [link.com/terms](https://link.com/terms) (stav „Last updated
  30 September 2026“, ohlášená změna spotřebitelských podmínek k
  **20. 11. 2026** – před zveřejněním znovu zkontrolovat).
- DPH ve více než 80 zemích, podvody (Radar), spory, e-maily s doklady od
  Linku, podpora přes Link, refundace do 60 dnů, výpis LINK.COM\*, jen
  Checkout/Payment Links, bez vlastní domény. Zdroj: [Stripe Docs – How
  Managed Payments works](https://docs.stripe.com/payments/managed-payments/how-it-works).
- Transakce zpracovávají acquiringové společnosti Stripe (pro EU Stripe
  Technology Europe, Limited). Zdroj: tamtéž, oddíl „Payment processing“.
- Smluvní stranou účtu Link pro osoby mimo Ameriku je **Stripe Technology
  Company, Limited** (Irsko). Zdroj: [link.com/terms/contracting-entity](https://link.com/terms/contracting-entity).
  Pro samotný prodej „Sold through Link“ ale stránka žádnou EU společnost
  neuvádí – prodávajícím zůstává americká Sold through Link, LLC.

**Neověřeno – zůstává jako `[[DOPLNIT]]` / `[[PRÁVNÍK]]`:**

- **Sídlo, stát založení a registrační číslo Sold through Link, LLC** –
  na stripe.com ani link.com zveřejněno není. Vyžádat od podpory Stripe po
  schválení účtu pro Managed Payments (čl. 5.1 podmínek).
- **Kdo je vůči spotřebiteli povinný z odstoupení a z vad.** Kupní smlouvu o
  předplatném uzavírá spotřebitel s Link SMP, smlouvu o užívání Služby s
  provozovatelem. Čl. 6 a 7 podmínek dnes slibují odstoupení s poměrnou
  náhradou a reklamace u provozovatele; Link má vlastní, odlišná pravidla.
  Rozhodnout, zda čl. 6 jen odkáže na podmínky Linku, nebo zda provozovatel
  dává vlastní (případně štědřejší) závazek, a jak se to promítne do
  pokladny (výslovná žádost o okamžité plnění – Stripe Checkout má jen
  standardní patičku; vlastní podmínky lze přidat v nastavení Checkout).
- **Role Linku/Stripe podle GDPR** (samostatný správce) a právní základ
  předání do USA – zásady, část 4 a 5.
- **Varianta trialu přes Stripe.** Pokud by se 10denní trial zakládal přes
  Stripe Checkout, Link sám posílá e-mail o začátku trialu a u trialů nad
  7 dní připomínku před koncem (viz bod 4).

**Alternativy (nevybrané):** *Paddle* (Paddle.com Market Limited, Londýn) je
také MoR, ale jeho AUP řadí „investment or financial advice, including
trading signals“ mezi zakázané kategorie – riziko pozdějšího zrušení účtu.
Při návratu k Paddle by šlo hlavně o záměnu subjektu v čl. 5.1 podmínek a v
části 4 zásad. *Stripe Billing bez MoR* je nejlevnější, ale provozovatel by
byl prodejcem se všemi povinnostmi z tabulky výše a čl. 5 i 6 by bylo nutné
přepsat.

### 3. Odstoupení od smlouvy a vracení peněz

Návrh dává spotřebiteli zákonných 14 dní a při odstoupení vrací cenu sníženou
o poměrnou část za dobu užívání (§ 1834 OZ). **K ověření:** zda je pro
digitální službu s předplatným a předchozím bezplatným zkušebním obdobím
správnější nabídnout plnou refundaci, a jak formulovat výslovnou žádost o
okamžité zahájení plnění při objednávce (zaškrtávací pole v pokladně).

### 4. Zkušební období bez karty

Návrh předpokládá, že 10denní zkušební období **nevyžaduje kartu** a po
skončení se účet přepne na Free (bez automatického stržení peněz). Pokud by
zkušební období vyžadovalo kartu a automaticky přecházelo v předplatné, je
nutné přepsat čl. 4.3 a před prvním stržením uživatele upozornit. Trial
proto běží v aplikaci, ne přes Stripe Checkout (u trialu ve Stripe by Link
posílal vlastní e-maily o začátku a konci trialu, viz bod 2).

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
- Pokladna: výslovná žádost o okamžité zahájení služby (k bodu 3);
  odkaz na podmínky a zásady v nastavení Stripe Checkout.
- Integrace Stripe Managed Payments: do Checkout posílat jen e-mail a interní
  ID účtu (tak to popisují zásady, část 4); v nastavení Stripe uvést platný
  e-mail podpory (Stripe na něj eskaluje dotazy a bez odpovědi do 48 hodin
  může vrátit peníze sám).
- Případná změna lhůty pro smazání účtu (k bodu 5).

### 9. K ověření právníkem

- Akt o digitálních službách (DSA): rozsah povinností pro malý podnik, který
  ukládá data zadaná uživatelem (kontaktní místo je v čl. 15.1).
- Omezení odpovědnosti vůči spotřebiteli (čl. 12.3) a § 2898 OZ.
- Rovnocennost české a anglické verze (čl. 15.3).
- Zda smí PostHog odesílat bezcookiové souhrnné události bez souhlasu.
- Ověření DPA, certifikací DPF a regionů u Google Cloud, Firebase, Neon,
  Cloudflare, PostHog a Sentry; u Stripe / Sold through Link, LLC role
  samostatného správce a certifikace DPF (bod 2) (a zda je Sentry v produkci zapnutý).
- Lhůta uchování údajů o předplatném podle daňových předpisů.
- Pověřenec pro ochranu osobních údajů: potvrdit, že není povinný.
