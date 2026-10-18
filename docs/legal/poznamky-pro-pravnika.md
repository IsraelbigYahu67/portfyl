# Právní dokumenty Portfyl – otevřené body a poznámky pro právníka

Stav k 2026-10-18. Návrhy v této složce jsou **pracovní verze 0.1** a nesmí se
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

### 2. Platební brána: Paddle, nebo Stripe

- **Paddle (doporučeno)** je *Merchant of Record*: formálně prodává zákazníkovi
  on, sám odvádí DPH ve všech státech, vystavuje doklady a vyřizuje refundace
  podle svých podmínek. Pro OSVČ to znamená nejméně daňové a administrativní
  práce. Poplatek je vyšší (orientačně 5 % + 0,50 USD za transakci – ověřit
  aktuální ceník).
- **Stripe** je jen platební brána: prodávajícím je provozovatel. Musí sám
  řešit DPH u prodeje spotřebitelům v jiných státech EU (režim OSS po
  překročení limitu), vystavovat daňové doklady a vést evidenci. Pravidla
  vracení peněz Stripe **neřeší** – určuje je provozovatel a platí pro ně
  zákon (čl. 6 podmínek).
- Návrh podmínek počítá s Paddle. Při volbě Stripe je nutné přepsat čl. 5 a
  6 podmínek a část 4 zásad.

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
- Pokladna: výslovná žádost o okamžité zahájení služby (k bodu 3).
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
- Pověřenec pro ochranu osobních údajů: potvrdit, že není povinný.
