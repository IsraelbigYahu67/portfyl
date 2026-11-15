"""German e-mail copy (formal address, "E-Mail" as in the app dictionary)."""

from emails.catalog import EmailContent, EmailKind, Locale

LOCALE = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Bestätigen Sie Ihre E-Mail für Portfyl",
            preheader="Ein Klick, und Ihr Konto ist startklar.",
            heading="Bestätigen Sie Ihre E-Mail",
            paragraphs=(
                "Willkommen bei Portfyl! Bestätigen Sie **{email}**, "
                "um die Einrichtung Ihres Kontos abzuschließen.",
            ),
            button="E-Mail bestätigen",
            note="Wenn Sie kein Portfyl-Konto erstellt haben, "
            "können Sie diese E-Mail ignorieren.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Setzen Sie Ihr Portfyl-Passwort zurück",
            preheader="Wählen Sie ein neues Passwort. Der Link gilt 1 Stunde.",
            heading="Passwort zurücksetzen",
            paragraphs=(
                "Wir haben eine Anfrage erhalten, das Passwort für **{email}** "
                "zurückzusetzen. Wählen Sie mit der Schaltfläche unten ein neues. "
                "Der Link gilt 1 Stunde.",
            ),
            button="Neues Passwort wählen",
            note="Wenn Sie das nicht angefordert haben, können Sie diese E-Mail "
            "ignorieren. Ihr Passwort bleibt unverändert.",
            footer_reason="address",
        ),
    },
    footer_reasons={
        "account": "Sie erhalten diese E-Mail, weil sie Ihr Portfyl-Konto betrifft.",
        "address": "Sie erhalten diese E-Mail, weil jemand diese Adresse bei Portfyl eingegeben hat.",
    },
    footer_help="Brauchen Sie Hilfe? support@portfyl.com",
)
