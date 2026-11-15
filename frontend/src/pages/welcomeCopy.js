export const LANGUAGE_KEY = "portfyl_landing_language";
// Each language has its own URL (lib/routes.js LANDING_PATHS). `suggestion`
// and `dismiss` are shown, in that language, to a visitor whose preferred
// language differs from the page they landed on.
export const LANGUAGES = [
  { code: "cs", label: "CZ", name: "Čeština", action: "Pokračovat česky", suggestion: "Tato stránka je dostupná i v češtině.", dismiss: "Zavřít" },
  { code: "en", label: "EN", name: "English", action: "Continue in English", suggestion: "This page is also available in English.", dismiss: "Dismiss" },
  { code: "de", label: "DE", name: "Deutsch", action: "Auf Deutsch fortfahren", suggestion: "Diese Seite gibt es auch auf Deutsch.", dismiss: "Schließen" },
];

// Shape of one language (all three must stay in step):
//   features[]   { title, text, images: [LANDING_IMAGES key...], alts: [alt per image] }.
//                A feature whose first picture exists is shown as a row with its
//                screenshots, the others as a short text column.
//   steps[]      { title, text }, dataFacts[] strings.
//   questions[]  { q, a, aOpen?, signupOnly? }. `aOpen` replaces `a` and
//                `signupOnly` hides the question, unless signup is open
//                (VITE_PUBLIC_SIGNUP), because the trial exists only then.
// Never mention Tax Report, Screener, Options or Polymarket here (plan
// 2026-11-15, Global Constraints), nor the US brokers dropped on 2026-11-15.
export const COPY = {
  cs: {
    title: "Portfyl — Všechny akcie a ETF v jednom přehledu", skip: "Přejít na obsah", home: "Portfyl, úvod", navigation: "Hlavní navigace",
    menu: "Menu", menuNavigation: "Navigace v telefonu", language: "Jazyk stránky",
    nav: ["Funkce", "Brokeři", "Ceník", "Časté otázky"], login: "Přihlásit se",
    status: ["Uzavřená beta.", "Demo je otevřené všem."],
    heading: "Všechny akcie a ETF v jednom přehledu.",
    lead: "Portfyl načte obchody od vašeho brokera a spočítá výkonnost, rozložení a dividendy celého portfolia. Bez tabulek v Excelu.",
    trialCta: "Vyzkoušet 10 dní zdarma", trialCtaShort: "Vyzkoušet zdarma", trialNote: "10 dní plánu Pro zdarma. Bez platební karty.",
    demoCta: "Vyzkoušet živé demo", demoCtaShort: "Vyzkoušet demo", demoLink: "Prohlédnout demo", demoNote: "Bez registrace. Běží na ukázkových datech.",
    heroAlt: "Screenshot Portfylu: vývoj výkonnosti ukázkového portfolia",
    caption: "Skutečná obrazovka aplikace s ukázkovým portfoliem. Obrázky ukazují anglické rozhraní.",
    brokers: { api: "Napojení přes API", file: "Import ze souboru", custom: "vlastní CSV" },
    brokerCheck: {
      title: "Nevidíte svého brokera?", placeholder: "Např. XTB, Trading 212…",
      supported: "{name} podporujeme. Svoje data nahrajete hned po registraci.", signup: "Založit účet zdarma", demo: "Prohlédnout demo",
      betaNote: "Portfyl je teď v uzavřené betě. Demo si ale můžete projít hned.",
      unsupported: "{name} zatím neumíme načíst. Podívejte se aspoň na ukázkové portfolio.",
    },
    featuresHeading: "Co v Portfylu uvidíte",
    features: [
      {
        title: "Rozložení podle pozic, sektorů a měn",
        text: "U každé pozice vidíte její váhu a hodnotu. Hned poznáte, jestli vám jedna akcie nebo jeden sektor netvoří příliš velkou část portfolia.",
        images: ["allocation", "sectors", "phoneAllocation", "phoneDashboard"],
        alts: ["Screenshot Portfylu: rozložení pozic ukázkového portfolia", "Screenshot Portfylu: rozložení portfolia podle sektorů a měn", "Screenshot Portfylu v telefonu: rozložení pozic", "Screenshot Portfylu v telefonu: přehled portfolia"],
      },
      {
        title: "Detail každé akcie",
        text: "Cena, P/E, zisk na akcii, dividendový výnos a roční rozpětí vedle sebe. Ocenění počítáme z pětiletého průměru P/E, ne z jednoho dne.",
        images: ["stock", "valuation"],
        alts: ["Screenshot Portfylu: detail akcie s cenou a klíčovými ukazateli", "Screenshot Portfylu: vývoj P/E za pět let s průměrnou čárou"],
      },
      {
        title: "Výkonnost proti indexům",
        text: "Porovnejte svůj výsledek s S&P 500, NASDAQ 100 nebo STOXX 50 za týden, rok i celou historii.",
        images: ["analytics"],
        alts: ["Screenshot Portfylu: výkonnost portfolia proti indexům"],
      },
      {
        title: "Dividendy měsíc po měsíci",
        text: "Kolik přišlo, od koho a jak příjem roste. Částky jsou v čisté výši, po srážce u zdroje.",
        images: ["dividends"],
        alts: ["Screenshot Portfylu: dividendy po měsících"],
      },
      {
        title: "Více portfolií, jedna měna",
        text: "Účty u různých brokerů vedle sebe. Vše přepočtené do měny, kterou si zvolíte.",
        images: [],
        alts: [],
      },
    ],
    howHeading: "Jak dostanete svá data dovnitř",
    steps: [
      { title: "Vyberte brokera", text: "Trading 212, IBKR a eToro připojíte klíčem API. U ostatních nahrajete export, který si stáhnete z jejich webu.", image: "onboardingBrokers", alt: "Screenshot Portfylu: výběr brokera" },
      { title: "Zkontrolujte náhled", text: "Před uložením ukážeme, co se chystá přidat, a označíme obchody, které už v portfoliu máte.", image: "importPreview", alt: "Screenshot Portfylu: náhled importu s označenými duplicitami" },
      { title: "Potvrďte", text: "Přehled je hotový během chvíle. Import můžete do 24 hodin vrátit zpět.", image: null, alt: "" },
    ],
    factsHeading: "Co se děje s vašimi daty",
    dataFacts: [
      "Portfyl data od brokera jen čte. Obchodovat ani převádět peníze neumí.",
      "Klíče k brokerům ukládáme šifrovaně.",
      "Vaše portfolio vidíte jen vy. Účet i data můžete kdykoli smazat.",
    ],
    pricing: {
      heading: "Ceník", note: "Platí se měsíčně, ceny jsou včetně DPH. Zrušit můžete kdykoli.",
      trial: "Každý nový účet dostane 10 dní plánu Pro zdarma. Bez platební karty.", perMonth: "/ měsíc",
      plans: [
        { name: "Free", features: ["1 portfolio", "Neomezeně pozic a transakcí", "3 upozornění", "Import ze souborů"] },
        { name: "Investor", features: ["5 portfolií", "2 napojení na brokery", "Kompletní analytika", "Synchronizace jednou denně"] },
        { name: "Pro", features: ["15 portfolií", "5 napojení na brokery", "Vlastní srovnávací indexy", "Synchronizace každých 6 hodin"] },
      ],
    },
    faqHeading: "Časté otázky",
    questions: [
      {
        q: "Můžu si Portfyl vyzkoušet už teď?",
        a: "Ano. Živé demo běží na ukázkovém portfoliu a nepotřebujete k němu účet. Registrace jsou zatím jen na pozvánku.",
        aOpen: "Ano. Živé demo běží na ukázkovém portfoliu a nepotřebujete k němu účet. Vlastní účet si založíte zdarma a prvních 10 dní máte plán Pro.",
      },
      { q: "Umí Portfyl za mě obchodovat?", a: "Ne. Portfyl data od brokera pouze čte a zobrazuje. Nákupy a prodeje děláte dál u svého brokera." },
      { q: "Co když můj broker v seznamu není?", a: "Transakce můžete nahrát ve vlastním souboru CSV. Další brokery průběžně přidáváme." },
      { q: "Je Portfyl investiční poradenství?", a: "Ne. Portfyl ukazuje vaše vlastní data a veřejné údaje o firmách. Rozhodnutí zůstávají na vás." },
      { q: "Co se stane po 10 dnech?", a: "Účet přejde na plán Free. Data zůstanou, jen nad limit Free budou pouze ke čtení.", signupOnly: true },
    ],
    closing: "Podívejte se, jak vypadá portfolio v Portfylu.",
    footer: { tagline: "Přehled investičního portfolia pro akcie a ETF.", product: "Produkt", legal: "Právní", contact: "Kontakt", demo: "Živé demo" },
    legal: [["terms", "Obchodní podmínky"], ["privacy", "Ochrana osobních údajů"]], legalLanguage: "cs", legalNavigation: "Právní dokumenty",
  },
  en: {
    title: "Portfyl — All your stocks and ETFs in one view", skip: "Skip to content", home: "Portfyl, home", navigation: "Main navigation",
    menu: "Menu", menuNavigation: "Phone navigation", language: "Page language",
    nav: ["Features", "Brokers", "Pricing", "FAQ"], login: "Log in",
    status: ["Closed beta.", "The demo is open to everyone."],
    heading: "All your stocks and ETFs in one view.",
    lead: "Portfyl reads the trades from your broker and calculates performance, allocation and dividends for the whole portfolio. No spreadsheets.",
    trialCta: "Try it free for 10 days", trialCtaShort: "Try it free", trialNote: "10 days of the Pro plan for free. No card needed.",
    demoCta: "Try the live demo", demoCtaShort: "Try the demo", demoLink: "See the demo", demoNote: "No sign-up. Runs on sample data.",
    heroAlt: "Portfyl screenshot: performance of a sample portfolio",
    caption: "A real screen from the app with a sample portfolio. The pictures show the English interface.",
    brokers: { api: "Connected through the API", file: "Import from a file", custom: "your own CSV" },
    brokerCheck: {
      title: "Don't see your broker?", placeholder: "e.g. XTB, Trading 212…",
      supported: "{name} is supported. You can bring your data right after signing up.", signup: "Create a free account", demo: "Open the demo",
      betaNote: "Portfyl is in private beta right now, but you can explore the demo straight away.",
      unsupported: "We can't read {name} yet. Take a look at the sample portfolio instead.",
    },
    featuresHeading: "What you will see in Portfyl",
    features: [
      {
        title: "Allocation by position, sector and currency",
        text: "For each position you see its weight and value. You can tell at once if one stock or one sector makes up too much of your portfolio.",
        images: ["allocation", "sectors", "phoneAllocation", "phoneDashboard"],
        alts: ["Portfyl screenshot: allocation of a sample portfolio by position", "Portfyl screenshot: portfolio breakdown by sector and currency", "Portfyl screenshot on a phone: allocation by position", "Portfyl screenshot on a phone: portfolio overview"],
      },
      {
        title: "Detail of every stock",
        text: "Price, P/E, earnings per share, dividend yield and the yearly range side by side. We value a stock against its five-year average P/E, not a single day.",
        images: ["stock", "valuation"],
        alts: ["Portfyl screenshot: stock detail with price and key figures", "Portfyl screenshot: five-year P/E history with the average line"],
      },
      {
        title: "Performance against indexes",
        text: "Compare your result with the S&P 500, NASDAQ 100 or STOXX 50 over a week, a year or the whole history.",
        images: ["analytics"],
        alts: ["Portfyl screenshot: portfolio performance against indexes"],
      },
      {
        title: "Dividends month by month",
        text: "How much came in, from whom, and how your income is growing. Amounts are shown net, after withholding at source.",
        images: ["dividends"],
        alts: ["Portfyl screenshot: dividends by month"],
      },
      {
        title: "Several portfolios, one currency",
        text: "Accounts at different brokers side by side. Everything converted into the currency you choose.",
        images: [],
        alts: [],
      },
    ],
    howHeading: "How your data gets in",
    steps: [
      { title: "Choose your broker", text: "Trading 212, IBKR and eToro connect with an API key. For the others you upload an export that you download from their website.", image: "onboardingBrokers", alt: "Portfyl screenshot: choosing a broker" },
      { title: "Check the preview", text: "Before saving, we show what is about to be added and mark the trades you already have in the portfolio.", image: "importPreview", alt: "Portfyl screenshot: import preview with duplicates marked" },
      { title: "Confirm", text: "Your overview is ready in a moment. You can undo the import within 24 hours.", image: null, alt: "" },
    ],
    factsHeading: "What happens to your data",
    dataFacts: [
      "Portfyl only reads the data from your broker. It cannot trade or move money.",
      "We store the keys to your brokers encrypted.",
      "Only you can see your portfolio. You can delete your account and data at any time.",
    ],
    pricing: {
      heading: "Pricing", note: "You pay monthly, prices include VAT. You can cancel at any time.",
      trial: "Every new account gets 10 days of the Pro plan for free. No card needed.", perMonth: "/ month",
      plans: [
        { name: "Free", features: ["1 portfolio", "Unlimited positions and transactions", "3 alerts", "Import from files"] },
        { name: "Investor", features: ["5 portfolios", "2 broker connections", "Complete analytics", "Sync once a day"] },
        { name: "Pro", features: ["15 portfolios", "5 broker connections", "Custom benchmark indexes", "Sync every 6 hours"] },
      ],
    },
    faqHeading: "Frequently asked questions",
    questions: [
      {
        q: "Can I try Portfyl right now?",
        a: "Yes. The live demo runs on a sample portfolio and needs no account. Sign-ups are invite-only for now.",
        aOpen: "Yes. The live demo runs on a sample portfolio and needs no account. You can create your own account for free and have the Pro plan for the first 10 days.",
      },
      { q: "Can Portfyl trade for me?", a: "No. Portfyl only reads and shows the data from your broker. You still buy and sell at your broker." },
      { q: "What if my broker is not on the list?", a: "You can upload your transactions in your own CSV file. We keep adding more brokers." },
      { q: "Is Portfyl investment advice?", a: "No. Portfyl shows your own data and public company figures. The decisions stay with you." },
      { q: "What happens after 10 days?", a: "The account moves to the Free plan. Your data stays, only what is over the Free limit becomes read-only.", signupOnly: true },
    ],
    closing: "See what a portfolio looks like in Portfyl.",
    footer: { tagline: "Portfolio overview for stocks and ETFs.", product: "Product", legal: "Legal", contact: "Contact", demo: "Live demo" },
    legal: [["terms", "Terms of Service"], ["privacy", "Privacy Policy"]], legalLanguage: "en", legalNavigation: "Legal documents",
  },
  de: {
    title: "Portfyl — Alle Aktien und ETFs in einer Übersicht", skip: "Zum Inhalt springen", home: "Portfyl, Startseite", navigation: "Hauptnavigation",
    menu: "Menü", menuNavigation: "Navigation im Telefon", language: "Sprache der Seite",
    nav: ["Funktionen", "Broker", "Preise", "Häufige Fragen"], login: "Anmelden",
    status: ["Geschlossene Beta.", "Die Demo steht allen offen."],
    heading: "Alle Aktien und ETFs in einer Übersicht.",
    lead: "Portfyl liest die Trades von deinem Broker ein und berechnet Performance, Aufteilung und Dividenden für das ganze Portfolio. Ohne Excel-Tabellen.",
    trialCta: "10 Tage kostenlos testen", trialCtaShort: "Kostenlos testen", trialNote: "10 Tage Pro-Tarif gratis. Ohne Zahlungskarte.",
    demoCta: "Live-Demo ausprobieren", demoCtaShort: "Demo ausprobieren", demoLink: "Demo ansehen", demoNote: "Ohne Registrierung. Läuft mit Beispieldaten.",
    heroAlt: "Portfyl-Screenshot: Entwicklung eines Beispielportfolios",
    caption: "Ein echter Bildschirm der App mit einem Beispielportfolio. Die Bilder zeigen die englische Oberfläche.",
    brokers: { api: "Anbindung per API", file: "Import aus einer Datei", custom: "eigene CSV-Datei" },
    brokerCheck: {
      title: "Dein Broker fehlt?", placeholder: "z. B. XTB, Trading 212…",
      supported: "{name} wird unterstützt. Deine Daten importierst du direkt nach der Registrierung.", signup: "Kostenloses Konto erstellen", demo: "Demo öffnen",
      betaNote: "Portfyl ist gerade in einer geschlossenen Beta – die Demo kannst du aber sofort ansehen.",
      unsupported: "{name} können wir noch nicht einlesen. Sieh dir stattdessen das Beispielportfolio an.",
    },
    featuresHeading: "Das siehst du in Portfyl",
    features: [
      {
        title: "Aufteilung nach Positionen, Branchen und Währungen",
        text: "Bei jeder Position siehst du Gewicht und Wert. So erkennst du sofort, ob eine Aktie oder eine Branche einen zu großen Teil deines Portfolios ausmacht.",
        images: ["allocation", "sectors", "phoneAllocation", "phoneDashboard"],
        alts: ["Portfyl-Screenshot: Aufteilung eines Beispielportfolios nach Positionen", "Portfyl-Screenshot: Portfolio nach Branchen und Währungen", "Portfyl-Screenshot im Telefon: Aufteilung nach Positionen", "Portfyl-Screenshot im Telefon: Portfolio-Übersicht"],
      },
      {
        title: "Details zu jeder Aktie",
        text: "Kurs, KGV, Gewinn je Aktie, Dividendenrendite und Jahresspanne nebeneinander. Die Bewertung berechnen wir aus dem Fünfjahresdurchschnitt des KGV, nicht aus einem einzelnen Tag.",
        images: ["stock", "valuation"],
        alts: ["Portfyl-Screenshot: Aktiendetails mit Kurs und Kennzahlen", "Portfyl-Screenshot: KGV der letzten fünf Jahre mit Durchschnittslinie"],
      },
      {
        title: "Performance gegen Indizes",
        text: "Vergleiche dein Ergebnis mit dem S&P 500, NASDAQ 100 oder STOXX 50 über eine Woche, ein Jahr oder die ganze Historie.",
        images: ["analytics"],
        alts: ["Portfyl-Screenshot: Portfolio-Performance gegen Indizes"],
      },
      {
        title: "Dividenden Monat für Monat",
        text: "Wie viel eingegangen ist, von wem und wie dein Einkommen wächst. Die Beträge sind netto, nach dem Abzug an der Quelle.",
        images: ["dividends"],
        alts: ["Portfyl-Screenshot: Dividenden nach Monaten"],
      },
      {
        title: "Mehrere Portfolios, eine Währung",
        text: "Konten bei verschiedenen Brokern nebeneinander. Alles umgerechnet in die Währung deiner Wahl.",
        images: [],
        alts: [],
      },
    ],
    howHeading: "So kommen deine Daten hinein",
    steps: [
      { title: "Broker wählen", text: "Trading 212, IBKR und eToro verbindest du mit einem API-Schlüssel. Bei den anderen lädst du einen Export hoch, den du auf deren Website herunterlädst.", image: "onboardingBrokers", alt: "Portfyl-Screenshot: Broker auswählen" },
      { title: "Vorschau prüfen", text: "Vor dem Speichern zeigen wir, was hinzugefügt wird, und markieren Trades, die du schon im Portfolio hast.", image: "importPreview", alt: "Portfyl-Screenshot: Importvorschau mit markierten Duplikaten" },
      { title: "Bestätigen", text: "Deine Übersicht ist in wenigen Augenblicken fertig. Den Import kannst du innerhalb von 24 Stunden rückgängig machen.", image: null, alt: "" },
    ],
    factsHeading: "Was mit deinen Daten passiert",
    dataFacts: [
      "Portfyl liest die Daten deines Brokers nur. Handeln oder Geld überweisen kann es nicht.",
      "Die Schlüssel zu deinen Brokern speichern wir verschlüsselt.",
      "Dein Portfolio siehst nur du. Konto und Daten kannst du jederzeit löschen.",
    ],
    pricing: {
      heading: "Preise", note: "Du zahlst monatlich, die Preise enthalten die Mehrwertsteuer. Du kannst jederzeit kündigen.",
      trial: "Jedes neue Konto bekommt 10 Tage den Pro-Tarif gratis. Ohne Zahlungskarte.", perMonth: "/ Monat",
      plans: [
        { name: "Free", features: ["1 Portfolio", "Unbegrenzt Positionen und Transaktionen", "3 Benachrichtigungen", "Import aus Dateien"] },
        { name: "Investor", features: ["5 Portfolios", "2 Broker-Anbindungen", "Vollständige Analysen", "Synchronisierung einmal täglich"] },
        { name: "Pro", features: ["15 Portfolios", "5 Broker-Anbindungen", "Eigene Vergleichsindizes", "Synchronisierung alle 6 Stunden"] },
      ],
    },
    faqHeading: "Häufige Fragen",
    questions: [
      {
        q: "Kann ich Portfyl schon jetzt ausprobieren?",
        a: "Ja. Die Live-Demo läuft mit einem Beispielportfolio, ein Konto brauchst du dafür nicht. Registrierungen gibt es vorerst nur auf Einladung.",
        aOpen: "Ja. Die Live-Demo läuft mit einem Beispielportfolio, ein Konto brauchst du dafür nicht. Ein eigenes Konto legst du kostenlos an und hast die ersten 10 Tage den Pro-Tarif.",
      },
      { q: "Kann Portfyl für mich handeln?", a: "Nein. Portfyl liest die Daten deines Brokers nur und zeigt sie an. Kaufen und Verkaufen machst du weiterhin bei deinem Broker." },
      { q: "Was, wenn mein Broker nicht in der Liste steht?", a: "Du kannst deine Transaktionen in einer eigenen CSV-Datei hochladen. Weitere Broker fügen wir laufend hinzu." },
      { q: "Ist Portfyl eine Anlageberatung?", a: "Nein. Portfyl zeigt deine eigenen Daten und öffentliche Unternehmenszahlen. Die Entscheidungen bleiben bei dir." },
      { q: "Was passiert nach 10 Tagen?", a: "Das Konto wechselt in den Free-Tarif. Deine Daten bleiben erhalten, nur was über dem Free-Limit liegt, ist nur noch lesbar.", signupOnly: true },
    ],
    closing: "Sieh dir an, wie ein Portfolio in Portfyl aussieht.",
    footer: { tagline: "Portfolio-Übersicht für Aktien und ETFs.", product: "Produkt", legal: "Rechtliches", contact: "Kontakt", demo: "Live-Demo" },
    legal: [["terms", "Nutzungsbedingungen (EN)"], ["privacy", "Datenschutz (EN)"]], legalLanguage: "en", legalNavigation: "Rechtliches",
  },
};
