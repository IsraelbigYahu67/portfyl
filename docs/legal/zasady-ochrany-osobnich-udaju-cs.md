# Zásady ochrany osobních údajů a cookies – Portfyl

> **NÁVRH – NEZVEŘEJŇOVAT.** Text čeká na doplnění údajů označených
> `[[DOPLNIT]]` a na kontrolu českým advokátem. Technický podklad je v
> [../compliance/data-processing-inventory.md](../compliance/data-processing-inventory.md),
> otevřené body v [poznamky-pro-pravnika.md](poznamky-pro-pravnika.md).

Účinnost od: `[[DOPLNIT: datum zveřejnění]]` \
Verze: 0.1 (návrh)

Tyto zásady vysvětlují, jaké osobní údaje služba Portfyl zpracovává, proč,
jak dlouho, komu je předává a jaká máte práva. Řídí se nařízením (EU)
2016/679 (GDPR), zákonem č. 110/2019 Sb., o zpracování osobních údajů, a
pro cookies a ukládání informací v prohlížeči také § 89 odst. 3 zákona
č. 127/2005 Sb., o elektronických komunikacích.

## 1. Správce a kontakt

**Jakub Zoubek**, IČO 67772366, místo podnikání Brusinková 1983,
252 28 Černošice, Česká republika (dále jen „**my**“).

Ve všech věcech ochrany osobních údajů nás kontaktujte na
**support@portfyl.com**. Pověřence pro ochranu osobních údajů jsme
nejmenovali, protože nám tato povinnost nevzniká. `[[PRÁVNÍK: ověřit]]`

## 2. Jaké údaje zpracováváme

| Kategorie | Příklady | Odkud je máme |
|---|---|---|
| **Údaje o účtu** | e-mail, jméno (pokud se přihlásíte přes Google), interní identifikátor účtu, datum ověření e-mailu | od vás při registraci, případně od Googlu při přihlášení přes Google |
| **Údaje o portfoliu** | názvy portfolií, transakce, tickery, počty kusů, ceny, měny, data, hotovost, dividendy, opce, poznámky | od vás (ruční zadání, import souboru) nebo od vašeho brokera, pokud ho připojíte |
| **Připojení k brokerům a službám** | šifrované API klíče, stav synchronizace, anonymizovaný otisk čísla účtu u brokera, šifrovaná adresa Discord webhooku | od vás |
| **Požadavky na brokery** | brokeři, které nás požádáte podporovat (název, který jste napsali), propojení s vaším účtem | od vás |
| **Údaje o předplatném** | tarif, období, stav předplatného, identifikátor zákazníka a transakce u Platebního partnera, země | od Platebního partnera; **číslo karty nikdy nedostáváme** |
| **Technické a bezpečnostní údaje** | IP adresa, typ prohlížeče, otisky (hashe) přihlašovacích relací, čas posledního přihlášení, bezpečnostní záznamy (audit log), počty použití funkcí | automaticky při používání Služby |
| **Komunikace s podporou** | obsah e-mailů, které nám pošlete | od vás |
| **Analytika (jen se souhlasem)** | pseudonymní události o používání aplikace – po přihlášení je spojujeme s interním identifikátorem účtu, nikoli s e-mailem ani jménem; viz čl. 8 | automaticky, pouze pokud souhlasíte |

Nezpracováváme zvláštní kategorie údajů (např. o zdraví) a nežádáme rodné
číslo ani doklady totožnosti. Službu mohou používat jen osoby starší 18 let.

**Povinnost poskytnout údaje.** Poskytnutí e-mailu je nutné k vytvoření
účtu – bez něj vám Službu nemůžeme poskytovat. Údaje o portfoliu, připojení
k brokerovi a Discord jsou dobrovolné; bez nich jen nebudou dostupné
příslušné funkce. Souhlas s analytikou je zcela dobrovolný a na funkčnost
nemá vliv.

## 3. Proč údaje zpracováváme a na jakém právním základě

| Účel | Právní základ (čl. 6 GDPR) |
|---|---|
| Vytvoření a správa účtu, poskytování Služby (výpočty, importy, synchronizace s brokerem, upozornění) | **plnění smlouvy** – čl. 6 odst. 1 písm. b) |
| Správa předplatného a komunikace o něm | **plnění smlouvy** – čl. 6 odst. 1 písm. b) |
| Zabezpečení Služby, prevence zneužití, ochrana oddělení dat uživatelů, řešení incidentů, chybové záznamy | **oprávněný zájem** na bezpečném provozu – čl. 6 odst. 1 písm. f) |
| Vyřizování reklamací, dotazů a uplatňování práv | **plnění smlouvy** / **právní povinnost** – čl. 6 odst. 1 písm. b) a c) |
| Plnění daňových a účetních povinností | **právní povinnost** – čl. 6 odst. 1 písm. c) |
| Ochrana našich právních nároků | **oprávněný zájem** – čl. 6 odst. 1 písm. f) |
| Analytika používání aplikace | **souhlas** – čl. 6 odst. 1 písm. a); souhlas můžete kdykoli odvolat |

Marketingové e-maily neposíláme. Pokud bychom je v budoucnu chtěli posílat,
požádáme vás předem o souhlas.

Nepoužíváme automatizované rozhodování ani profilování, které by pro vás
mělo právní nebo podobně závažné účinky.

## 4. Komu údaje předáváme

Údaje neprodáváme. Předáváme je jen dodavatelům, kteří nám pomáhají Službu
provozovat (**zpracovatelé**), a to v rozsahu nezbytném pro jejich úkol a na
základě smlouvy o zpracování osobních údajů:

| Dodavatel | Co dělá | Kde se data zpracovávají |
|---|---|---|
| Google Cloud (Google Cloud EMEA Ltd. / Google LLC) | hosting aplikace (Cloud Run), šifrovací klíče, provozní záznamy, plánované úlohy | EU – Belgie (`europe-west1`); podpora může přistupovat z USA |
| Google Firebase Authentication | registrace, přihlášení, ověření e-mailu, přihlášení přes Google | EU/USA |
| Neon Inc. | databáze (PostgreSQL) a zálohy | EU – Frankfurt `[[OVĚŘIT]]` |
| Cloudflare, Inc. | DNS, šifrované spojení (TLS), ochrana proti útokům | globální síť |
| PostHog Inc. (PostHog Cloud EU) | analytika používání – **jen pokud udělíte souhlas** | EU – Frankfurt |

**Samostatní správci** – tyto subjekty zpracovávají údaje podle vlastních
zásad:

- **Platební partner** – společnost ze skupiny Stripe vystupující pod značkou
  Link (Stripe Managed Payments) `[[DOPLNIT: přesný název a sídlo
  prodávajícího subjektu]]` – přijímá platby jako prodejce, vystavuje doklady,
  odvádí DPH a vyřizuje dotazy k platbám, vracení peněz a správu předplatného
  na webu link.com.
- **Váš broker** (např. Trading 212, Interactive Brokers, eToro) – jen pokud
  ho sami připojíte; posíláme mu vaše API přihlášení a dostáváme od něj
  údaje o účtu.
- **Discord** – jen pokud si nastavíte upozornění do Discordu.
- **Poskytovatelé tržních dat** (např. Yahoo Finance, SEC EDGAR) – dostávají
  pouze tickery a časová období, ne vaše osobní údaje ani obsah portfolia.

Údaje můžeme předat také orgánům veřejné moci, pokud nám to ukládá zákon.

## 5. Předávání mimo EU

Někteří dodavatelé (Google, Cloudflare, Neon, PostHog) jsou
společnosti z USA nebo mají podporu mimo EU. Předávání do USA se opírá o
rozhodnutí Evropské komise o odpovídající ochraně (**EU-U.S. Data Privacy
Framework**), pokud je dodavatel certifikován, jinak o **standardní smluvní
doložky** schválené Evropskou komisí. `[[PRÁVNÍK: ověřit certifikace a DPA
každého dodavatele]]` Kopii standardních smluvních doložek vám na žádost
poskytneme na support@portfyl.com; seznam certifikovaných společností
EU-U.S. Data Privacy Framework je na https://www.dataprivacyframework.gov.

## 6. Jak dlouho údaje uchováváme

| Údaje | Doba uložení |
|---|---|
| Účet, portfolia a všechna data v aplikaci | po dobu existence účtu; po vaší žádosti o smazání viz níže |
| Zálohy databáze | data smazaná z aplikace mohou zůstat v záloze ještě nejvýše `[[DOPLNIT: 7 dní]]`, pak jsou nenávratně přepsána |
| Provozní záznamy (logy) | 30 dní; neobsahují obsah portfolia ani hesla |
| Záznamy o přihlašovacích relacích | 30 dní po vypršení nebo odhlášení |
| Bezpečnostní záznamy (audit log) | po dobu existence účtu, smažou se spolu s ním |
| Požadavky na brokery (názvy brokerů, které nás požádáte podporovat) | po dobu existence účtu, smažou se spolu s ním |
| Komunikace s podporou | 1 rok od vyřízení |
| Doklady o platbách | uchovává Platební partner; my údaje o předplatném po dobu, kterou vyžadují daňové předpisy `[[PRÁVNÍK: doplnit lhůtu]]` |
| Analytická data (se souhlasem) | nejvýše 1 rok |

**Smazání účtu:** Účet smažete v Nastavení → Data a soukromí. Z
bezpečnostních důvodů vás nejprve požádáme o nové přihlášení. Smazání
proběhne po 30denní lhůtě, během níž ho můžete zrušit; poté jsou všechna data účtu odstraněna z databáze a ze záloh
zmizí nejpozději po uplynutí doby uvedené výše.

Zrušení předplatného účet **nemaže** – účet se jen přepne na tarif Free.

## 7. Vaše práva

Máte právo:

- **na přístup** – zjistit, jaké údaje o vás zpracováváme;
- **na opravu** nepřesných údajů;
- **na výmaz** („být zapomenut“) – účet si můžete smazat sami v aplikaci;
- **na omezení zpracování**;
- **na přenositelnost** – data si můžete sami stáhnout ve formátu JSON
  v Nastavení;
- **odvolat souhlas** (např. s analytikou) – kdykoli v nastavení cookies,
  aniž by to ovlivnilo předchozí zpracování;
- **podat stížnost** u Úřadu pro ochranu osobních údajů, Pplk. Sochora 27,
  170 00 Praha 7, `https://uoou.gov.cz`.

**Právo vznést námitku.** Proti zpracování, které provádíme na základě
oprávněného zájmu (zabezpečení, ochrana právních nároků), můžete kdykoli
vznést námitku na support@portfyl.com. Zpracování ukončíme, pokud
neprokážeme závažné oprávněné důvody, které převažují nad vašimi zájmy.

Žádosti posílejte na **support@portfyl.com**. Odpovíme do 1 měsíce; v
odůvodněných případech můžeme lhůtu prodloužit o další dva měsíce a o
prodloužení vás předem informujeme. Abychom
ochránili váš účet, můžeme vás požádat o ověření, že žádost posíláte z
e-mailu svého účtu.

## 8. Cookies a úložiště v prohlížeči

**Nezbytné nebo vámi vyžádané (bez souhlasu, § 89 odst. 3 zákona
č. 127/2005 Sb.)** – bez nich Služba nefunguje nebo by si nezapamatovala vaše
nastavení:

| Název | Typ | K čemu slouží | Doba |
|---|---|---|---|
| `__Host-portfyl_session` | cookie | udržení přihlášení (náhodný identifikátor relace) | nejvýše 30 dní |
| `portfyl_analytics_consent` | cookie první strany, sdílená mezi `portfyl.com` a subdoménami | zapamatování vaší volby souhlasu s analytikou | 180 dní |
| `sb_theme`, `sb_theme_style`, `sb_palette`, `sb_currency`, `sb_portfolio_id`, `sb_view_mode`, `portfyl_landing_language` | localStorage | vzhled, měna, vybrané portfolio, režim zobrazení a jazyk úvodní stránky | dokud je nesmažete |
| `portfyl_intended_broker` | localStorage | zapamatování brokera, kterého jste si zvolili před registrací | dokud ho nesmažete nebo nevytvoříte první portfolio |
| `portfyl_preferences_confirmed` | localStorage | zapamatování, že jste potvrdili jazyk a měnu | dokud ho nesmažete |
| `portfyl_getting_started:<workspaceId>` | localStorage | zapamatování postupu v úvodním seznamu úkolů | dokud ho nesmažete |
| `sb_dashboard_layout_v3`, `sb_dashboard_widget_order_v4`, `sb_dashboard_widgets_hidden`, `sb_stock_report_sections`, `sb_stock_report_tabs` | localStorage | rozložení přehledu a nastavení detailu akcie | dokud je nesmažete |
| `__cf_bm` a další cookies Cloudflare | cookie | ochrana proti robotům a útokům | nejvýše 30 minut |

**Analytické (jen se souhlasem)** – PostHog Cloud EU. Ukládají se pouze po
tom, co analytiku přijmete:

| Název | Typ | K čemu slouží | Doba |
|---|---|---|---|
| `ph_<projekt>_posthog` | cookie a localStorage | identifikátor návštěvníka a relace pro analytiku | dle PostHogu, typicky 1 rok |
| `portfyl_captured_once:*`, `portfyl_activation_v1:*` | localStorage | aby se jednorázové události neposlaly dvakrát a aby se zapamatoval stav aktivace | dokud je nesmažete |

Měříme pouze předem určený seznam událostí (např. „otevřel ukázku“,
„vytvořil portfolio“). Po přihlášení je spojujeme s interním identifikátorem
vašeho účtu (pseudonym), nikoli s e-mailem ani jménem. Nikdy nesbíráme
e-mail, jméno, obsah portfolia, transakce, částky ani poznámky. Nahrávání
obrazovky je vypnuté. **Pokud analytiku odmítnete nebo se ještě
nerozhodnete, do PostHogu neodesíláme nic** a žádné analytické cookies ani
úložiště se nevytvářejí.

Reklamní ani sledovací cookies třetích stran nepoužíváme.

## 9. Zabezpečení

Data chráníme mimo jiné šifrovaným spojením (HTTPS), šifrováním API klíčů a
webhooků pomocí klíčů spravovaných v Google Cloud KMS, oddělením dat
jednotlivých uživatelů na úrovni databáze, odvolatelnými relacemi a
záznamem bezpečnostních událostí. Z provozních záznamů vylučujeme obsah
portfolií a tajné údaje.

## 10. Změny zásad

Zásady můžeme aktualizovat. O podstatných změnách vás informujeme e-mailem
nebo v aplikaci předem. Aktuální verze je vždy na https://portfyl.com/privacy.
