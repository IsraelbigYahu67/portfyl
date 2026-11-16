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
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="Ihr Portfyl-Passwort wurde geändert",
            preheader="Wenn Sie das waren, müssen Sie nichts weiter tun.",
            heading="Ihr Passwort wurde geändert",
            paragraphs=(
                "Das Passwort für **{email}** wurde gerade geändert. Wenn Sie das waren, müssen Sie nichts weiter tun.",
            ),
            facts=(("Wann", "{datetime}"),),
            button="Das war ich nicht",
            note="Mit der Schaltfläche können Sie das Passwort sofort zurücksetzen. Falls das nicht klappt, schreiben Sie an support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="Ihr Portfyl-Konto wird am {date} gelöscht",
            preheader="Bis dahin können Sie es sich anders überlegen.",
            heading="Die Kontolöschung ist geplant",
            paragraphs=(
                "Sie haben uns gebeten, Ihr Portfyl-Konto und alle Daten zu löschen. Bis zum unten genannten Datum können Sie es sich anders überlegen.",
            ),
            facts=(("Konto", "{email}"), ("Wir löschen es am", "{date}")),
            button="Konto behalten",
            note="Wenn Sie das nicht angefordert haben, brechen Sie die Löschung mit der Schaltfläche ab und ändern Sie Ihr Passwort.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="Ihr Portfyl-Konto wurde gelöscht",
            preheader="Die letzte E-Mail zu diesem Konto.",
            heading="Ihr Konto ist gelöscht",
            paragraphs=(
                "Wir haben das Konto **{email}** und seine Daten auf Ihren Wunsch gelöscht. Das ist die letzte E-Mail, die wir dazu senden.",
                "Sie können jederzeit zurückkommen und ein neues Konto anlegen.",
            ),
            note="Fragen dazu? Schreiben Sie an support@portfyl.com.",
            footer_reason="account",
        ),
    },
    footer_reasons={
        "account": "Sie erhalten diese E-Mail, weil sie Ihr Portfyl-Konto betrifft.",
        "address": "Sie erhalten diese E-Mail, weil jemand diese Adresse bei Portfyl eingegeben hat.",
    },
    footer_help="Brauchen Sie Hilfe? support@portfyl.com",
    months=(
        "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember",
    ),
    date_pattern="{day}. {month} {year}",
    datetime_pattern="{date}, {time} UTC",
)
