"""Polish e-mail copy (informal "ty" as in the app dictionary, "e-mail")."""

from emails.catalog import EmailContent, EmailKind, Locale

LOCALE = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Potwierdź swój e-mail w Portfylu",
            preheader="Jedno kliknięcie i Twoje konto jest gotowe.",
            heading="Potwierdź swój e-mail",
            paragraphs=(
                "Witaj w Portfylu! Potwierdź adres **{email}**, "
                "aby dokończyć zakładanie konta.",
            ),
            button="Potwierdź e-mail",
            note="Jeśli konto w Portfylu nie zostało założone przez Ciebie, "
            "możesz zignorować ten e-mail.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Zresetuj hasło do konta Portfyl",
            preheader="Wybierz nowe hasło. Link działa przez 1 godzinę.",
            heading="Zresetuj hasło",
            paragraphs=(
                "Otrzymaliśmy prośbę o zresetowanie hasła do konta **{email}**. "
                "Wybierz nowe za pomocą przycisku poniżej. "
                "Link działa przez 1 godzinę.",
            ),
            button="Wybierz nowe hasło",
            note="Jeśli to nie była Twoja prośba, możesz zignorować ten e-mail. "
            "Twoje hasło pozostaje bez zmian.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="Hasło do konta Portfyl zostało zmienione",
            preheader="Jeśli to Ty, nie musisz nic więcej robić.",
            heading="Hasło zostało zmienione",
            paragraphs=(
                "Hasło do konta **{email}** zostało właśnie zmienione. Jeśli to Ty, nie musisz nic więcej robić.",
            ),
            facts=(("Kiedy", "{datetime}"),),
            button="To nie ja",
            note="Przyciskiem od razu zresetujesz hasło. Jeśli to nie zadziała, napisz do nas na support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="Twoje konto Portfyl zostanie usunięte {date}",
            preheader="Do tego czasu możesz zmienić zdanie.",
            heading="Usunięcie konta jest zaplanowane",
            paragraphs=(
                "Dostaliśmy prośbę o usunięcie Twojego konta Portfyl wraz ze wszystkimi danymi. Do podanej niżej daty możesz zmienić zdanie.",
            ),
            facts=(("Konto", "{email}"), ("Usuniemy je", "{date}")),
            button="Zachowaj moje konto",
            note="Jeśli to nie Twoja prośba, anuluj usunięcie przyciskiem i zmień hasło.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="Twoje konto Portfyl zostało usunięte",
            preheader="Ostatni e-mail dotyczący tego konta.",
            heading="Konto zostało usunięte",
            paragraphs=(
                "Usunęliśmy konto **{email}** i jego dane, zgodnie z Twoją prośbą. To ostatni e-mail, który w tej sprawie wysyłamy.",
                "W każdej chwili możesz wrócić i założyć nowe konto.",
            ),
            note="Masz pytania? Napisz do nas na support@portfyl.com.",
            footer_reason="account",
        ),
    },
    footer_reasons={
        "account": "Dostajesz ten e-mail, ponieważ dotyczy Twojego konta Portfyl.",
        "address": "Dostajesz ten e-mail, ponieważ ktoś wpisał ten adres w Portfylu.",
    },
    footer_help="Potrzebujesz pomocy? support@portfyl.com",
    months=(
        "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
    ),
    date_pattern="{day} {month} {year}",
    datetime_pattern="{date}, {time} UTC",
)
