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
    },
    footer_reasons={
        "account": "Tento e-mail jste dostali, protože se týká vašeho účtu Portfyl.",
        "address": "Tento e-mail jste dostali, protože někdo zadal tuto adresu v Portfylu.",
    },
    footer_help="Potřebujete pomoc? support@portfyl.com",
)
