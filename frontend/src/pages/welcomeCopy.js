export const LANGUAGE_KEY = "portfyl_landing_language";
// Each language has its own URL (lib/routes.js LANDING_PATHS). `suggestion`
// and `dismiss` are shown, in that language, to a visitor whose preferred
// language differs from the page they landed on.
export const LANGUAGES = [
  { code: "cs", label: "CZ", name: "Čeština", action: "Pokračovat česky", suggestion: "Tato stránka je dostupná i v češtině.", dismiss: "Zavřít" },
  { code: "en", label: "EN", name: "English", action: "Continue in English", suggestion: "This page is also available in English.", dismiss: "Dismiss" },
  { code: "de", label: "DE", name: "Deutsch", action: "Auf Deutsch fortfahren", suggestion: "Diese Seite gibt es auch auf Deutsch.", dismiss: "Schließen" },
];

export const COPY = {
  cs: {
    title: "Portfyl — Vaše investice. Konečně přehledně.", skip: "Přejít na obsah", home: "Portfyl — úvod", navigation: "Hlavní navigace", language: "Jazyk stránky",
    nav: ["Proč Portfyl", "Ukázky aplikace", "Otázky"], badge: "UKÁZKA", eyebrow: "MALÝ ODSTUP. VELKÝ PŘEHLED.",
    heading: ["Vaše investice.", "Konečně přehledně."], lead: ["Za každým číslem je kus vaší budoucnosti.", "Dejte svému portfoliu prostor, ve kterém mu budete rozumět."],
    cta: "Prohlédnout ukázky", demoCta: "Vyzkoušet živé demo", heroNote: "Přehled portfolia, analytika a dividendy na jednom místě.", window: "PORTFYL / VAŠE PORTFOLIO", previewBadge: "UKÁZKA APLIKACE",
    heroAlt: "Screenshot Portfylu: vývoj výkonnosti demo portfolia", float: ["Všechno do sebe zapadá.", "Vaše portfolio v jednom pohledu."], caption: "Skutečný screenshot aplikace s demo portfoliem.",
    ribbon: "PRO VAŠE INVESTIČNÍ KAŽDODENNO", assets: "Akcie & ETF", import: "Import CSV", moreBrokers: "+ 3 další",
    featuresKicker: "MÉNĚ HLEDÁNÍ. VÍCE SOUVISLOSTÍ.", featuresHeading: ["Víte, co vlastníte.", "A jak se tomu daří."], featuresLead: "Od prvního nákupu po portfolio budované roky. Portfyl propojuje čísla do přehledu, ke kterému se budete rádi vracet.",
    features: [
      ["Vývoj, který dává smysl", "Sledujte hodnotu portfolia a jeho výkonnost v čase. Porovnejte svůj vývoj s tržními benchmarky."],
      ["Celý obrázek vašeho portfolia", "Poznejte váhu jednotlivých pozic, sektorů i měn. Uvidíte, kde se vaše investice soustředí."],
      ["Dividendy pod kontrolou", "Mějte přehled o dividendových příjmech a jejich historii. Sledujte další rozměr svého portfolia."],
    ],
    showcaseKicker: "MALÁ OCHUTNÁVKA PORTFYLU", showcaseNote: "Navrženo pro přehled. Do posledního detailu.", selectPreview: "Vybrat ukázku aplikace", detailNote: "Jeden prostor. Více souvislostí.", imageCaption: "Screenshoty aplikace · Demo portfolio a tržní data · Rozhraní v angličtině",
    previews: [
      { label: "Složení portfolia", title: "Každá investice. V souvislostech.", description: "Podívejte se na váhu jednotlivých pozic. Přehledné rozložení ukáže, jaký podíl má každá investice ve vašem portfoliu.", alt: "Screenshot Portfylu s rozložením pozic demo portfolia" },
      { label: "Detail akcie", title: "Poznejte, co vlastníte.", description: "Cena akcie, ocenění a klíčové ukazatele společnosti přehledně vedle sebe. Více kontextu pro vaše vlastní rozhodování.", alt: "Screenshot detailu akcie Microsoft v Portfylu s cenou a oceněním" },
      { label: "Přehled portfolia", title: "Váš majetek. V jednom pohledu.", description: "Hodnota pozic, hotovost, celkový výsledek i dividendy. Hlavní čísla vašeho portfolia na jedné obrazovce.", alt: "Screenshot přehledu hodnoty demo portfolia v Portfylu" },
      { label: "Výkonnost", title: "Sledujte celý příběh.", description: "Prohlédněte si vývoj portfolia v čase. Přepínejte období a porovnávejte růst s tržními benchmarky.", alt: "Screenshot grafu výkonnosti demo portfolia v Portfylu" },
    ],
    faqKicker: "DOBRÉ VĚDĚT", faqHeading: ["Ještě něco", "vám vrtá hlavou?"],
    questions: [
      ["Co je Portfyl?", "Portfyl je aplikace pro přehled a analýzu investičního portfolia. Spojuje pozice, výkonnost, dividendy a informace o společnostech na jednom místě."],
      ["Pro koho je Portfyl určený?", "Pro individuální investory, kteří chtějí lépe rozumět svým akciím a ETF — ať už s investováním začínají, nebo spravují portfolio několik let."],
      ["Jaké brokery Portfyl podporuje?", "Portfyl načte data z Trading 212, Interactive Brokers a eToro přes API a z exportů Degiro, XTB, Charles Schwab a Fidelity. Transakce lze importovat i z CSV souborů."],
      ["Můžu si už Portfyl vyzkoušet?", "Ano. Živé demo je syntetické, nevyžaduje účet a ukazuje, jak Portfyl funguje bez vašich investičních dat."],
    ],
    closingKicker: "PŘIPRAVUJEME PRO VÁS", closingHeading: ["Více přehledu.", "Více klidu."], closingNote: "Nový pohled na vaše investice. Již brzy.", back: "Zpátky nahoru", footer: "Váš prostor pro investiční přehled.", legal: [["terms", "Obchodní podmínky"], ["privacy", "Ochrana osobních údajů"]], legalLanguage: "cs", legalNavigation: "Právní dokumenty",
    brokerCheck: {
      title: "Podporujeme vašeho brokera?", placeholder: "Např. XTB, Trading 212…",
      supported: "{name} podporujeme. Svoje data nahrajete hned po registraci.", signup: "Založit účet zdarma", demo: "Prohlédnout demo",
      betaNote: "Portfyl je teď v uzavřené betě. Demo si ale můžete projít hned.",
      unsupported: "{name} zatím neumíme načíst. Podívejte se aspoň na ukázkové portfolio.",
    },
  },
  en: {
    title: "Portfyl — Your investments. Finally clear.", skip: "Skip to content", home: "Portfyl — home", navigation: "Main navigation", language: "Page language",
    nav: ["Why Portfyl", "App previews", "Questions"], badge: "PREVIEW", eyebrow: "A STEP BACK. A CLEARER VIEW.",
    heading: ["Your investments.", "Finally clear."], lead: ["Behind every number is a piece of your future.", "Give your portfolio a space where it all makes sense."],
    cta: "Explore the previews", demoCta: "Try the live demo", heroNote: "Your portfolio, analytics and dividends in one place.", window: "PORTFYL / YOUR PORTFOLIO", previewBadge: "PRODUCT PREVIEW",
    heroAlt: "Portfyl screenshot showing demo portfolio performance", float: ["It all comes together.", "Your portfolio at a glance."], caption: "Real app screenshot with a demo portfolio.",
    ribbon: "FOR YOUR EVERYDAY INVESTING", assets: "Stocks & ETFs", import: "CSV import", moreBrokers: "+ 3 more",
    featuresKicker: "LESS SEARCHING. MORE CONTEXT.", featuresHeading: ["Know what you own.", "And how it is doing."], featuresLead: "From your first purchase to a portfolio built over years. Portfyl brings the numbers together in a view you will enjoy coming back to.",
    features: [
      ["Performance that makes sense", "Track your portfolio value and performance over time. Compare your progress with market benchmarks."],
      ["Your portfolio’s full picture", "Understand the weight of each holding, sector and currency. See where your investments are concentrated."],
      ["Stay on top of dividends", "Keep track of your dividend income and its history. Explore another dimension of your portfolio."],
    ],
    showcaseKicker: "A TASTE OF PORTFYL", showcaseNote: "Designed for clarity. Down to the last detail.", selectPreview: "Choose an app preview", detailNote: "One space. More context.", imageCaption: "App screenshots · Demo portfolio and market data · Interface in English",
    previews: [
      { label: "Portfolio allocation", title: "Every investment. In context.", description: "See the weight of each holding. A clear breakdown shows how much each investment contributes to your portfolio.", alt: "Portfyl screenshot showing demo portfolio allocation" },
      { label: "Stock details", title: "Get to know what you own.", description: "Share price, valuation and key company metrics, clearly presented side by side. More context for your own decisions.", alt: "Portfyl screenshot of Microsoft stock details and valuation" },
      { label: "Portfolio overview", title: "Your wealth. At a glance.", description: "Holdings, cash, total returns and dividends. Your portfolio's key numbers on one screen.", alt: "Portfyl screenshot showing demo portfolio value" },
      { label: "Performance", title: "Follow the whole story.", description: "Explore your portfolio's performance over time. Switch periods and compare growth with market benchmarks.", alt: "Portfyl screenshot showing the demo portfolio performance chart" },
    ],
    faqKicker: "GOOD TO KNOW", faqHeading: ["Anything else", "on your mind?"],
    questions: [
      ["What is Portfyl?", "Portfyl is an app for tracking and analysing your investment portfolio. It brings holdings, performance, dividends and company information together in one place."],
      ["Who is Portfyl for?", "Individual investors who want to better understand their stocks and ETFs, whether they are just starting out or have managed a portfolio for years."],
      ["Which brokers does Portfyl support?", "Portfyl syncs Trading 212, Interactive Brokers and eToro through their APIs and imports exports from Degiro, XTB, Charles Schwab and Fidelity. Transactions can also be imported from CSV files."],
      ["Can I try Portfyl yet?", "Yes. The live demo is synthetic, account-free, and shows how Portfyl works without using your investment data."],
    ],
    closingKicker: "ON THE WAY", closingHeading: ["More clarity.", "More peace of mind."], closingNote: "A fresh perspective on your investments. Coming soon.", back: "Back to top", footer: "Your space for a clearer investment picture.", legal: [["terms", "Terms of Service"], ["privacy", "Privacy Policy"]], legalLanguage: "en", legalNavigation: "Legal documents",
    brokerCheck: {
      title: "Is your broker supported?", placeholder: "e.g. XTB, Trading 212…",
      supported: "{name} is supported. You can bring your data right after signing up.", signup: "Create a free account", demo: "Open the demo",
      betaNote: "Portfyl is in private beta right now, but you can explore the demo straight away.",
      unsupported: "We can't read {name} yet. Take a look at the sample portfolio instead.",
    },
  },
  de: {
    title: "Portfyl — Deine Investments. Endlich übersichtlich.", skip: "Zum Inhalt springen", home: "Portfyl — Startseite", navigation: "Hauptnavigation", language: "Sprache der Seite",
    nav: ["Warum Portfyl", "Einblicke", "Fragen"], badge: "VORSCHAU", eyebrow: "ETWAS ABSTAND. MEHR ÜBERBLICK.",
    heading: ["Deine Investments.", "Endlich übersichtlich."], lead: ["Hinter jeder Zahl steckt ein Stück deiner Zukunft.", "Gib deinem Portfolio einen Ort, an dem du es besser verstehst."],
    cta: "Vorschau entdecken", demoCta: "Live-Demo ausprobieren", heroNote: "Dein Portfolio, Analysen und Dividenden an einem Ort.", window: "PORTFYL / DEIN PORTFOLIO", previewBadge: "APP-VORSCHAU",
    heroAlt: "Portfyl-Screenshot mit der Entwicklung eines Demo-Portfolios", float: ["Alles ergibt ein Gesamtbild.", "Dein Portfolio auf einen Blick."], caption: "Echter App-Screenshot mit einem Demo-Portfolio.",
    ribbon: "FÜR DEINEN INVESTMENTALLTAG", assets: "Aktien & ETFs", import: "CSV-Import", moreBrokers: "+ 3 weitere",
    featuresKicker: "WENIGER SUCHEN. MEHR VERSTEHEN.", featuresHeading: ["Wisse, was du besitzt.", "Und wie es sich entwickelt."], featuresLead: "Vom ersten Kauf bis zum über Jahre aufgebauten Portfolio. Portfyl verbindet die Zahlen zu einer Übersicht, zu der du gerne zurückkehrst.",
    features: [
      ["Entwicklung, die verständlich wird", "Verfolge den Wert und die Performance deines Portfolios im Zeitverlauf. Vergleiche deine Entwicklung mit Marktbenchmarks."],
      ["Dein Portfolio im Gesamtbild", "Erkenne die Gewichtung einzelner Positionen, Branchen und Währungen. Sieh, wo sich deine Investments konzentrieren."],
      ["Dividenden im Blick", "Behalte deine Dividendeneinnahmen und ihre Entwicklung im Blick. Entdecke eine weitere Seite deines Portfolios."],
    ],
    showcaseKicker: "EIN ERSTER EINBLICK IN PORTFYL", showcaseNote: "Für Klarheit gestaltet. Bis ins letzte Detail.", selectPreview: "App-Vorschau auswählen", detailNote: "Ein Ort. Mehr Zusammenhänge.", imageCaption: "App-Screenshots · Demo-Portfolio und Marktdaten · Oberfläche auf Englisch",
    previews: [
      { label: "Portfolioaufteilung", title: "Jedes Investment. Im Zusammenhang.", description: "Erkenne die Gewichtung jeder Position. Eine klare Aufteilung zeigt, welchen Anteil jedes Investment an deinem Portfolio hat.", alt: "Portfyl-Screenshot mit der Aufteilung des Demo-Portfolios" },
      { label: "Aktiendetails", title: "Lerne kennen, was du besitzt.", description: "Aktienkurs, Bewertung und wichtige Unternehmenskennzahlen übersichtlich nebeneinander. Mehr Kontext für deine eigenen Entscheidungen.", alt: "Portfyl-Screenshot der Microsoft-Aktie mit Kurs und Bewertung" },
      { label: "Portfolioübersicht", title: "Dein Vermögen. Auf einen Blick.", description: "Positionen, Bargeld, Gesamtergebnis und Dividenden. Die wichtigsten Zahlen deines Portfolios auf einer Seite.", alt: "Portfyl-Screenshot mit dem Wert des Demo-Portfolios" },
      { label: "Performance", title: "Verfolge die ganze Entwicklung.", description: "Entdecke die Entwicklung deines Portfolios im Zeitverlauf. Wechsle den Zeitraum und vergleiche das Wachstum mit Marktbenchmarks.", alt: "Portfyl-Screenshot des Performance-Diagramms des Demo-Portfolios" },
    ],
    faqKicker: "GUT ZU WISSEN", faqHeading: ["Noch Fragen", "im Kopf?"],
    questions: [
      ["Was ist Portfyl?", "Portfyl ist eine App zur Übersicht und Analyse deines Investmentportfolios. Sie vereint Positionen, Performance, Dividenden und Unternehmensinformationen an einem Ort."],
      ["Für wen ist Portfyl gedacht?", "Für Privatanleger, die ihre Aktien und ETFs besser verstehen möchten — ganz gleich, ob sie gerade anfangen oder schon seit Jahren ein Portfolio verwalten."],
      ["Welche Broker unterstützt Portfyl?", "Portfyl synchronisiert Trading 212, Interactive Brokers und eToro über deren API und importiert Exporte von Degiro, XTB, Charles Schwab und Fidelity. Außerdem lassen sich Transaktionen aus CSV-Dateien importieren."],
      ["Kann ich Portfyl schon ausprobieren?", "Ja. Die Live-Demo ist synthetisch, ohne Konto nutzbar und zeigt Portfyl ohne deine eigenen Investmentdaten."],
    ],
    closingKicker: "WIR BEREITEN ALLES FÜR DICH VOR", closingHeading: ["Mehr Überblick.", "Mehr Gelassenheit."], closingNote: "Ein neuer Blick auf deine Investments. Demnächst.", back: "Nach oben", footer: "Dein Ort für den Überblick über deine Investments.", legal: [["terms", "Nutzungsbedingungen (EN)"], ["privacy", "Datenschutz (EN)"]], legalLanguage: "en", legalNavigation: "Rechtliches",
    brokerCheck: {
      title: "Wird dein Broker unterstützt?", placeholder: "z. B. XTB, Trading 212…",
      supported: "{name} wird unterstützt. Deine Daten importierst du direkt nach der Registrierung.", signup: "Kostenloses Konto erstellen", demo: "Demo öffnen",
      betaNote: "Portfyl ist gerade in einer geschlossenen Beta – die Demo kannst du aber sofort ansehen.",
      unsupported: "{name} können wir noch nicht einlesen. Sieh dir stattdessen das Beispielportfolio an.",
    },
  },
};
