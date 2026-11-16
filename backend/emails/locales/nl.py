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
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="Je Portfyl-wachtwoord is gewijzigd",
            preheader="Als jij dit was, hoef je niets meer te doen.",
            heading="Je wachtwoord is gewijzigd",
            paragraphs=(
                "Het wachtwoord van **{email}** is zojuist gewijzigd. Als jij dit was, hoef je niets meer te doen.",
            ),
            facts=(("Wanneer", "{datetime}"),),
            button="Dat was ik niet",
            note="Met de knop kun je je wachtwoord meteen opnieuw instellen. Lukt dat niet, schrijf dan naar support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="Je Portfyl-account wordt op {date} verwijderd",
            preheader="Tot dan kun je nog van gedachten veranderen.",
            heading="Verwijdering van je account is gepland",
            paragraphs=(
                "Je hebt ons gevraagd je Portfyl-account en alle gegevens te verwijderen. Tot de datum hieronder kun je nog van gedachten veranderen.",
            ),
            facts=(("Account", "{email}"), ("Wij verwijderen het op", "{date}")),
            button="Mijn account behouden",
            note="Heb je dit niet aangevraagd? Annuleer het dan met de knop en wijzig je wachtwoord.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="Je Portfyl-account is verwijderd",
            preheader="De laatste e-mail over dit account.",
            heading="Je account is verwijderd",
            paragraphs=(
                "We hebben het account **{email}** en de bijbehorende gegevens verwijderd, zoals je vroeg. Dit is de laatste e-mail die we hierover sturen.",
                "Je bent altijd welkom om terug te komen en een nieuw account aan te maken.",
            ),
            note="Vragen hierover? Schrijf naar support@portfyl.com.",
            footer_reason="account",
        ),
    },
    footer_reasons={
        "account": "Je ontvangt deze e-mail omdat deze over je Portfyl-account gaat.",
        "address": "Je ontvangt deze e-mail omdat iemand dit adres heeft ingevoerd bij Portfyl.",
    },
    footer_help="Hulp nodig? support@portfyl.com",
    months=(
        "januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december",
    ),
    date_pattern="{day} {month} {year}",
    datetime_pattern="{date}, {time} UTC",
)
