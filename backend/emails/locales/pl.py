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
    },
    footer_reasons={
        "account": "Dostajesz ten e-mail, ponieważ dotyczy Twojego konta Portfyl.",
        "address": "Dostajesz ten e-mail, ponieważ ktoś wpisał ten adres w Portfylu.",
    },
    footer_help="Potrzebujesz pomocy? support@portfyl.com",
)
