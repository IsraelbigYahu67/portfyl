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
| **Záznamy proti zneužití zkušebního období** | klíčované otisky (HMAC-SHA256 s tajným klíčem) kanonického e-mailu (malá písmena, bez `+tagu`, u Gmailu bez teček), IP adresy (IPv6 zkrácená na /64), čísel účtů u brokerů a identifikátorů 5 nejstarších importovaných transakcí; značka, že zkušební období nebylo přiznáno. Samotné hodnoty neukládáme | vytváříme je my při registraci a při importu či synchronizaci dat od brokera |
| **Záznam o přijetí podmínek** | potvrzení věku alespoň 18 let, verze obchodních podmínek a těchto zásad, které byly při registraci zobrazeny, čas a způsob registrace (e-mailem, nebo přes Google); před ověřením e-mailu je záznam veden pod identifikátorem Firebase | vytváří server při registraci |
| **Komunikace s podporou** | obsah e-mailů, které nám pošlete | od vás |
| **Analytika (jen se souhlasem)** | pseudonymní události o používání aplikace – po přihlášení je spojujeme s interním identifikátorem účtu, nikoli s e-mailem ani jménem; viz čl. 8 | automaticky, pouze pokud souhlasíte |

Nezpracováváme zvláštní kategorie údajů (např. o zdraví) a nežádáme rodné
číslo ani doklady totožnosti.

### Děti

Služba je určena jen osobám, které dosáhly věku **alespoň 18 let**. Je to
podmínka smlouvy, kterou při registraci potvrzujete zaškrtnutím. Vědomě
nezpracováváme osobní údaje osob mladších 18 let. Pokud zjistíme, že účet
patří osobě mladší 18 let, účet smažeme. Pokud se domníváte, že účet založila
osoba mladší 18 let, napište nám na support@portfyl.com.

Hlavním základem zpracování je smlouva (čl. 6 odst. 1 písm. b) GDPR), nikoli
souhlas. Věková hranice 18 let proto nevychází z čl. 8 GDPR ani z § 7 zákona
č. 110/2019 Sb. (věk, od něhož dítě samo uděluje souhlas se zpracováním
v souvislosti se službami informační společnosti), ale je smluvní podmínkou
užívání Služby.

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
| Doložení, že jste při registraci potvrdili věk alespoň 18 let a přijali podmínky a že vám byly tyto zásady zpřístupněny | **oprávněný zájem** na prokázání uzavření smlouvy a splnění informační povinnosti – čl. 6 odst. 1 písm. f) `[[PRÁVNÍK: ověřit právní základ]]` |
| Zasílání transakčních e-mailů k účtu: ověření e-mailu, obnovení hesla, upozornění na změnu hesla a oznámení o smazání účtu (odesíláme je přes dodavatele Brevo, viz čl. 4) | **plnění smlouvy** – čl. 6 odst. 1 písm. b) |
| Zabezpečení Služby, prevence zneužití, ochrana oddělení dat uživatelů, řešení incidentů, chybové záznamy | **oprávněný zájem** na bezpečném provozu – čl. 6 odst. 1 písm. f) |
| Nabídnutí jednoho zkušebního období na osobu (rozpoznání, že stejná schránka, síť, účet u brokera nebo historie transakcí už zkušební období měly) | **oprávněný zájem** na ochraně zkušebního období před zneužitím – čl. 6 odst. 1 písm. f) `[[PRÁVNÍK: test vyváženosti; jsou klíčované otisky zde pseudonymizovanými osobními údaji?]]` |
| Vyřizování reklamací, dotazů a uplatňování práv | **plnění smlouvy** / **právní povinnost** – čl. 6 odst. 1 písm. b) a c) |
| Plnění daňových a účetních povinností | **právní povinnost** – čl. 6 odst. 1 písm. c) |
| Ochrana našich právních nároků | **oprávněný zájem** – čl. 6 odst. 1 písm. f) |
| Analytika používání aplikace | **souhlas** – čl. 6 odst. 1 písm. a); souhlas můžete kdykoli odvolat |

Transakční e-maily uvedené výše slouží jen k provozu a zabezpečení vašeho
účtu; nejsou marketingové. Marketingové e-maily neposíláme. Pokud bychom je
v budoucnu chtěli posílat, požádáme vás předem o souhlas.

Nepoužíváme automatizované rozhodování ani profilování, které by pro vás
mělo právní nebo podobně závažné účinky. Rozpoznání, že stejná schránka,
síť, účet u brokera nebo historie transakcí už zkušební období měly, probíhá
automaticky; nepřiznání zkušebního období však nemá právní ani obdobně
významný účinek – Služba vám zůstává dostupná v tarifu Free.

## 4. Komu údaje předáváme

Údaje neprodáváme. Předáváme je jen dodavatelům, kteří nám pomáhají Službu
provozovat (**zpracovatelé**), a to v rozsahu nezbytném pro jejich úkol a na
základě smlouvy o zpracování osobních údajů:

| Dodavatel | Co dělá | Kde se data zpracovávají |
|---|---|---|
| Google Cloud (Google Cloud EMEA Ltd. / Google LLC) | hosting aplikace (Cloud Run), šifrovací klíče, provozní záznamy, plánované úlohy | EU – Belgie (`europe-west1`); podpora může přistupovat z USA |
| Google Firebase Authentication | registrace, přihlášení, ověření e-mailu, přihlášení přes Google | EU/USA |
| Neon Inc. | databáze (PostgreSQL) a zálohy | EU – Frankfurt `[[OVĚŘIT]]` |
| Cloudflare, Inc. | DNS, šifrované spojení (TLS), ochrana proti útokům a kontrola proti robotům při vytvoření nového účtu (Turnstile) `[[PRÁVNÍK: zpracovatel, nebo samostatný správce; DPA]]` | globální síť |
| PostHog Inc. (PostHog Cloud EU) | analytika používání – **jen pokud udělíte souhlas** | EU – Frankfurt |
| Brevo (společnost se sídlem ve Francii) `[[DOPLNIT: přesný název a sídlo smluvní strany podle smlouvy s Brevo]]` | odesílání transakčních e-mailů z účtu (ověření e-mailu, obnovení hesla, upozornění na změnu hesla, oznámení o smazání účtu). Brevo dostává e-mailovou adresu příjemce a obsah zprávy (včetně odkazu, data a času události); odkazy v e-mailech vedou přes sledovací doménu Brevo. Pokud odeslání přes Brevo API selže, pošle ověřovací nebo resetovací e-mail Firebase Authentication, který jde rovněž přes Brevo | `[[OVĚŘIT: umístění zpracování, DPA a předání mimo EHP]]` |

**Samostatní správci** – tyto subjekty zpracovávají údaje podle vlastních
zásad:

- **Platební partner** – společnost ze skupiny Stripe vystupující pod značkou
  Link (Stripe Managed Payments) `[[DOPLNIT: přesný název a sídlo
  prodávajícího subjektu]]` – přijímá platby jako prodejce, vystavuje doklady,
  odvádí DPH a vyřizuje dotazy k platbám, vracení peněz a správu předplatného
  na webu link.com. **Platebnímu partnerovi (Stripe) předáváme** při zahájení
  platby e-mailovou adresu vašeho účtu, identifikátor vašeho pracovního
  prostoru v Portfyl (náhodné UUID, podle kterého platbu přiřadíme k vašemu
  účtu) a zvolený tarif. Údaje o platební kartě zadáváte přímo u něj a my je
  nikdy nedostaneme.
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

U dodavatele Brevo a u platebního partnera zatím ověřujeme, zda a na základě
jakých záruk mohou být údaje zpracovávány mimo Evropský hospodářský prostor.
`[[OVĚŘIT: DPA a předání mimo EHP]]`

## 6. Jak dlouho údaje uchováváme

| Údaje | Doba uložení |
|---|---|
| Účet, portfolia a všechna data v aplikaci | po dobu existence účtu; po vaší žádosti o smazání viz níže |
| Zálohy databáze | zálohy sloužící k obnovení databáze uchovávají smazaná data nejvýše 7 dní, poté jsou nenávratně přepsána |
| Provozní záznamy (logy) | 30 dní; neobsahují obsah portfolia ani hesla |
| Záznamy o přihlašovacích relacích | 30 dní po vypršení nebo odhlášení |
| Záznam o přijetí podmínek | po dobu existence účtu, smaže se spolu s ním `[[OVĚŘIT: mazání záznamů, jejichž e-mail nebyl nikdy ověřen]]` |
| Čítače omezení počtu požadavků (klíčovaný otisk, ne samotná IP adresa) | do uplynutí příslušného časového okna (řádově minuty); prošlé záznamy se mažou každou hodinu |
| Záznamy o využití funkcí (rezervace limitů tarifu) | 90 dní po dokončení nebo uvolnění rezervace; nejpozději se smazáním účtu |
| Záznamy o doručení upozornění (např. do Discordu) | odeslané nebo definitivně neúspěšné záznamy 90 dní; nejpozději se smazáním účtu |
| Záznamy o odeslaných upozorněních na dividendy (aby se upozornění neposlalo dvakrát) | 400 dní; nejpozději se smazáním účtu |
| Dočasná data importu z Trading 212 (surové záznamy obchodů a dividend potřebné k dokončení a kontrole importu) | 14 dní po dokončení, selhání nebo zrušení synchronizace; starší podklady ke kontrole 90 dní; poslední podklad ke kontrole u každého připojení zůstává, dokud existuje účet; nejpozději se smazáním účtu |
| Transakční e-maily (Brevo) | my kopie odeslaných e-mailů neukládáme; doba uchování záznamů o doručení u Brevo `[[OVĚŘIT: doba uchování u Brevo]]` |
| Bezpečnostní záznamy (audit log) | po dobu existence účtu, smažou se spolu s ním |
| Požadavky na brokery (názvy brokerů, které nás požádáte podporovat) | po dobu existence účtu, smažou se spolu s ním |
| Záznamy o zkušebním období: otisky e-mailu a údajů o brokerovi | 12 měsíců; zůstávají i po smazání účtu, aby stejná osoba nemohla zkušební období opakovat `[[PRÁVNÍK: výmaz podle čl. 17 vs. uchování otisku po smazání]]` |
| Záznam o zkušebním období: otisk IP adresy | 30 dní |
| Záznam o zkušebním období pracovního prostoru (začátek, konec, důvod, značka odepření) | smaže se spolu s účtem |
| Komunikace s podporou | 1 rok od vyřízení |
| Doklady o platbách | uchovává Platební partner; my údaje o předplatném po dobu, kterou vyžadují daňové předpisy `[[PRÁVNÍK: doplnit lhůtu]]` `[[OVĚŘIT: aplikace dnes při smazání účtu maže i záznamy o předplatném; zda a jaké daňové záznamy vedeme mimo aplikaci]]` |
| Analytická data (se souhlasem) | nejvýše 1 rok |

**Smazání účtu:** Účet smažete v Nastavení → Data a soukromí. Z
bezpečnostních důvodů vás nejprve požádáme o nové přihlášení a po upozornění
o potvrzení smazání. Smazání proběhne okamžitě a nelze je vrátit zpět; všechna
data účtu jsou ihned odstraněna z databáze a ze záloh zmizí nejpozději po
uplynutí doby uvedené výše.

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
  170 00 Praha 7, `https://uoou.gov.cz`, nebo u dozorového úřadu v jiném
  členském státě EU – podle čl. 77 GDPR u úřadu v zemi vašeho obvyklého
  bydliště, místa výkonu zaměstnání nebo místa údajného porušení.

**Právo vznést námitku.** Proti zpracování, které provádíme na základě
oprávněného zájmu (zabezpečení, ochrana právních nároků, výše uvedené
záznamy proti zneužití zkušebního období), můžete kdykoli
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

Při vytvoření nového účtu běží ve vašem prohlížeči kontrola proti robotům
Cloudflare Turnstile (skript a rám Cloudflare, `challenges.cloudflare.com`) a
jednorázový výsledek ověřujeme u Cloudflare, kterému předáváme vaši IP adresu.
Portfyl si k tomu nic neukládá. `[[PRÁVNÍK: spadá kontrola zařízení v
Turnstile pod výjimku „nezbytně nutné“ podle ePrivacy?]]`

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

## Related

- Architecture: [[Account deletion and data lifecycle]] · [[Secrets and security]] · [[Portfyl]]
- Code: [[data_retention]] · [[workspace_export]] · [[account_deletion]]
- Docs: [[legal/privacy-policy-en]] · [[compliance/data-processing-inventory]]
