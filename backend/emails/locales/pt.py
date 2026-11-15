"""Portuguese e-mail copy (formal address, European spelling as in the app dictionary)."""

from emails.catalog import EmailContent, EmailKind, Locale

LOCALE = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Confirme o seu e-mail para o Portfyl",
            preheader="Basta um clique e a sua conta fica pronta.",
            heading="Confirme o seu e-mail",
            paragraphs=(
                "Damos-lhe as boas-vindas ao Portfyl! Confirme **{email}** "
                "para concluir a configuração da sua conta.",
            ),
            button="Confirmar e-mail",
            note="Se não criou uma conta no Portfyl, pode ignorar este e-mail.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Reponha a sua palavra-passe do Portfyl",
            preheader="Escolha uma nova palavra-passe. A ligação funciona durante 1 hora.",
            heading="Repor a palavra-passe",
            paragraphs=(
                "Recebemos um pedido para repor a palavra-passe de **{email}**. "
                "Escolha uma nova com o botão abaixo. "
                "A ligação funciona durante 1 hora.",
            ),
            button="Escolha uma nova palavra-passe",
            note="Se não fez este pedido, pode ignorar este e-mail. "
            "A sua palavra-passe mantém-se igual.",
            footer_reason="address",
        ),
    },
    footer_reasons={
        "account": "Recebeu este e-mail porque diz respeito à sua conta Portfyl.",
        "address": "Recebeu este e-mail porque alguém introduziu este endereço no Portfyl.",
    },
    footer_help="Precisa de ajuda? support@portfyl.com",
)
