"""Czech e-mail copy (the reviewed text from the design spec, formal address)."""

from emails.catalog import EmailContent, EmailKind, Locale

LOCALE = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Potvrďte svůj e-mail pro Portfyl",
            preheader="Stačí jedno kliknutí a účet je připravený.",
            heading="Potvrďte svůj e-mail",
            paragraphs=(
                "Vítejte v Portfylu! Potvrďte adresu **{email}** a dokončete tím založení účtu.",
            ),
            button="Potvrdit e-mail",
            note="Pokud jste si účet v Portfylu nezakládali, tento e-mail můžete ignorovat.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Obnovení hesla k Portfylu",
            preheader="Nastavte si nové heslo. Odkaz platí 1 hodinu.",
            heading="Obnovte si heslo",
            paragraphs=(
                "Dostali jsme žádost o obnovení hesla k účtu **{email}**. "
                "Nové heslo si nastavíte tlačítkem níže. Odkaz platí 1 hodinu.",
            ),
            button="Nastavit nové heslo",
            note="Pokud jste o obnovení nežádali, tento e-mail můžete ignorovat. "
            "Vaše heslo zůstává stejné.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="Heslo k účtu Portfyl bylo změněno",
            preheader="Pokud jste to byli vy, nemusíte nic dělat.",
            heading="Heslo bylo změněno",
            paragraphs=(
                "Heslo k účtu **{email}** bylo právě změněno. Pokud jste to byli vy, nemusíte nic dělat.",
            ),
            facts=(("Kdy", "{datetime}"),),
            button="To jsem nebyl/a já",
            note="Tlačítkem si heslo hned obnovíte. Kdyby to nešlo, napište nám na support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="Váš účet Portfyl bude smazán {date}",
            preheader="Do té doby si to můžete rozmyslet.",
            heading="Smazání účtu je naplánováno",
            paragraphs=(
                "Požádali jste o smazání účtu Portfyl včetně všech dat. Do uvedeného data si to můžete rozmyslet.",
            ),
            facts=(("Účet", "{email}"), ("Smažeme ho", "{date}")),
            button="Ponechat účet",
            note="Pokud jste o smazání nežádali, zrušte ho tlačítkem a změňte si heslo.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="Váš účet Portfyl byl smazán",
            preheader="Poslední e-mail k tomuto účtu.",
            heading="Účet je smazaný",
            paragraphs=(
                "Účet **{email}** i jeho data jsme na vaši žádost smazali. Je to poslední e-mail, který vám k němu posíláme.",
                "Kdykoli se můžete vrátit a založit si nový.",
            ),
            note="Máte k tomu otázku? Napište nám na support@portfyl.com.",
            footer_reason="account",
        ),
    },
    footer_reasons={
        "account": "Tento e-mail jste dostali, protože se týká vašeho účtu Portfyl.",
        "address": "Tento e-mail jste dostali, protože někdo zadal tuto adresu v Portfylu.",
    },
    footer_help="Potřebujete pomoc? support@portfyl.com",
    months=(
        "ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince",
    ),
    date_pattern="{day}. {month} {year}",
    datetime_pattern="{date}, {time} UTC",
)
