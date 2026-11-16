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
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="La tua password di Portfyl è stata modificata",
            preheader="Se l'hai fatto tu, non devi fare altro.",
            heading="La tua password è stata modificata",
            paragraphs=(
                "La password di **{email}** è stata appena modificata. Se l'hai fatto tu, non devi fare altro.",
            ),
            facts=(("Quando", "{datetime}"),),
            button="Non l'ho fatto io",
            note="Con il pulsante puoi reimpostare subito la password. Se non funziona, scrivi a support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="Il tuo account Portfyl verrà eliminato il {date}",
            preheader="Fino ad allora puoi cambiare idea.",
            heading="L'eliminazione dell'account è programmata",
            paragraphs=(
                "Ci hai chiesto di eliminare il tuo account Portfyl e tutti i suoi dati. Puoi cambiare idea fino alla data indicata qui sotto.",
            ),
            facts=(("Account", "{email}"), ("Lo eliminiamo il", "{date}")),
            button="Mantieni il mio account",
            note="Se non l'hai richiesto tu, annulla con il pulsante e cambia la tua password.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="Il tuo account Portfyl è stato eliminato",
            preheader="L'ultima e-mail su questo account.",
            heading="Il tuo account è stato eliminato",
            paragraphs=(
                "Abbiamo eliminato l'account **{email}** e i suoi dati, come hai chiesto. È l'ultima e-mail che ti inviamo a riguardo.",
                "Puoi tornare e crearne uno nuovo quando vuoi.",
            ),
            note="Domande? Scrivi a support@portfyl.com.",
            footer_reason="account",
        ),
    },
    footer_reasons={
        "account": "Ricevi questa e-mail perché riguarda il tuo account Portfyl.",
        "address": "Ricevi questa e-mail perché qualcuno ha inserito questo indirizzo su Portfyl.",
    },
    footer_help="Hai bisogno di aiuto? support@portfyl.com",
    months=(
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    ),
    date_pattern="{day} {month} {year}",
    datetime_pattern="{date}, {time} UTC",
)
