# Zabezpečení Portfyl

Aktualizováno: 22. listopadu 2026

Portfyl je přehled portfolia: data o vašich investicích čte, ale **nikdy
nezadává obchodní pokyny ani příkazy k výběru**. Níže je popsáno, jak
chráníme vaše data, co můžete udělat sami a jak nám nahlásit zranitelnost.

## 1. Jak data chráníme

- **Klíče a tokeny brokerů** ukládáme šifrovaně. V cloudové verzi je šifruje
  Google Cloud KMS. Nezapisujeme je do provozních logů ani do exportů dat.
- **Šifrované spojení.** Portfyl se používá přes HTTPS. Přihlašovací cookie má
  příznaky `HttpOnly`, `Secure`, `SameSite=Lax` a prefix `__Host-`, takže se
  neposílá nešifrovaně a skripty stránky ji nepřečtou. Stránky posíláme
  s bezpečnostními hlavičkami (Content-Security-Policy, `X-Content-Type-Options`,
  `Referrer-Policy`) a nelze je vložit do cizího rámu.
- **Oddělení uživatelů.** Data každého uživatele jsou od ostatních oddělena
  dvakrát: v aplikaci a přímo v databázi PostgreSQL pomocí zabezpečení na
  úrovni řádků (row-level security).
- **Relace.** Po přihlášení dostanete náhodný neprůhlený token; na serveru
  ukládáme jen jeho otisk (hash), nikoli token samotný. Relace vyprší po
  30 dnech a lze ji zneplatnit: odhlášením, odhlášením ze všech zařízení nebo
  změnou hesla. Změny dat jsou chráněny proti CSRF a počet požadavků
  (včetně přihlašování a odesílání e-mailů) omezujeme.

## 2. Přihlášení a hesla

Přihlášení e-mailem a heslem nebo přes Google zajišťuje Firebase
Authentication (Google). Heslo odesíláte přímo službě Firebase; Portfyl jej
neukládá ve své databázi.

## 3. Vaše data a jejich smazání

- Vaše data **neprodáváme**.
- Když odpojíte brokera, uložený klíč se smaže.
- Smazání účtu proběhne okamžitě: data jsou odstraněna z databáze hned.
  Záložní kopie pro obnovu po havárii mohou smazaná data uchovat nejvýše
  7 dní, poté jsou nenávratně přepsána.

Podrobnosti o osobních údajích najdete v [Zásadách ochrany osobních
údajů](zasady-ochrany-osobnich-udaju-cs.md).

## 4. Co doporučujeme vám

- U brokera vytvořte pro Portfyl klíč **jen s právem čtení** (pokud to broker
  umožňuje) a nedávejte mu práva k obchodování ani k výběrům.
- Klíč můžete kdykoli zneplatnit v nastavení účtu u brokera; Portfyl pak
  přestane data tohoto brokera načítat.
- Používejte silné, jedinečné heslo a nikomu ho nesdělujte.

## 5. Jak nahlásit zranitelnost

Pokud jste našli bezpečnostní chybu, napište na **support@portfyl.com**.
Uveďte prosím, kde jste chybu našli, jak ji lze zopakovat a jaký může mít
dopad; nepřikládejte cizí data a chybu nezneužívejte. Odpovíme bez zbytečného
odkladu. Program odměn za nalezené chyby (bug bounty) nemáme.

Porušení zabezpečení osobních údajů řešíme podle článků 33 a 34 nařízení
GDPR (oznámení Úřadu pro ochranu osobních údajů a, vyžaduje-li to
závažnost rizika, i dotčeným osobám).
