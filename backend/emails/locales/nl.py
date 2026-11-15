"""Dutch e-mail copy (informal "je" as in the app dictionary, "e-mail")."""

from emails.catalog import EmailContent, EmailKind, Locale

LOCALE = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Bevestig je e-mail voor Portfyl",
            preheader="Eén klik en je account is klaar.",
            heading="Bevestig je e-mail",
            paragraphs=(
                "Welkom bij Portfyl! Bevestig **{email}** "
                "om het instellen van je account af te ronden.",
            ),
            button="E-mail bevestigen",
            note="Heb je geen Portfyl-account aangemaakt? "
            "Dan kun je deze e-mail negeren.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Stel je Portfyl-wachtwoord opnieuw in",
            preheader="Kies een nieuw wachtwoord. De link werkt 1 uur.",
            heading="Wachtwoord opnieuw instellen",
            paragraphs=(
                "We hebben een verzoek ontvangen om het wachtwoord van **{email}** "
                "opnieuw in te stellen. Kies een nieuw wachtwoord met de knop "
                "hieronder. De link werkt 1 uur.",
            ),
            button="Kies een nieuw wachtwoord",
            note="Heb je dit niet aangevraagd? Dan kun je deze e-mail negeren. "
            "Je wachtwoord blijft hetzelfde.",
            footer_reason="address",
        ),
    },
    footer_reasons={
        "account": "Je ontvangt deze e-mail omdat deze over je Portfyl-account gaat.",
        "address": "Je ontvangt deze e-mail omdat iemand dit adres heeft ingevoerd bij Portfyl.",
    },
    footer_help="Hulp nodig? support@portfyl.com",
)
