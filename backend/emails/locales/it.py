"""Italian e-mail copy (tu, "e-mail" as in the app dictionary)."""

from emails.catalog import EmailContent, EmailKind, Locale

LOCALE = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Conferma la tua e-mail per Portfyl",
            preheader="Basta un clic e il tuo account è pronto.",
            heading="Conferma la tua e-mail",
            paragraphs=(
                "Ti diamo il benvenuto su Portfyl! Conferma **{email}** "
                "per completare la configurazione del tuo account.",
            ),
            button="Conferma e-mail",
            note="Se non hai creato un account Portfyl, puoi ignorare questa e-mail.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Reimposta la tua password di Portfyl",
            preheader="Scegli una nuova password. Il link è valido per 1 ora.",
            heading="Reimposta la password",
            paragraphs=(
                "Abbiamo ricevuto una richiesta di reimpostazione della password "
                "per **{email}**. Scegline una nuova con il pulsante qui sotto. "
                "Il link è valido per 1 ora.",
            ),
            button="Scegli una nuova password",
            note="Se non l'hai richiesto, puoi ignorare questa e-mail. "
            "La tua password resta invariata.",
            footer_reason="address",
        ),
    },
    footer_reasons={
        "account": "Ricevi questa e-mail perché riguarda il tuo account Portfyl.",
        "address": "Ricevi questa e-mail perché qualcuno ha inserito questo indirizzo su Portfyl.",
    },
    footer_help="Hai bisogno di aiuto? support@portfyl.com",
)
