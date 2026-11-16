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
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="A sua palavra-passe do Portfyl foi alterada",
            preheader="Se foi você, não precisa de fazer mais nada.",
            heading="A sua palavra-passe foi alterada",
            paragraphs=(
                "A palavra-passe de **{email}** acabou de ser alterada. Se foi você, não precisa de fazer mais nada.",
            ),
            facts=(("Quando", "{datetime}"),),
            button="Não fui eu",
            note="O botão permite repor a palavra-passe de imediato. Se não funcionar, escreva para support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="A sua conta Portfyl será eliminada a {date}",
            preheader="Até lá, pode mudar de ideias.",
            heading="A eliminação da conta está agendada",
            paragraphs=(
                "Pediu-nos para eliminar a sua conta Portfyl e todos os dados. Pode mudar de ideias até à data indicada abaixo.",
            ),
            facts=(("Conta", "{email}"), ("Data de eliminação", "{date}")),
            button="Manter a minha conta",
            note="Se não fez este pedido, cancele-o com o botão e altere a sua palavra-passe.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="A sua conta Portfyl foi eliminada",
            preheader="O último e-mail sobre esta conta.",
            heading="A sua conta foi eliminada",
            paragraphs=(
                "Eliminámos a conta **{email}** e os respetivos dados, como pediu. Este é o último e-mail que lhe enviamos sobre o assunto.",
                "Pode voltar e criar uma nova quando quiser.",
            ),
            note="Tem dúvidas sobre isto? Escreva para support@portfyl.com.",
            footer_reason="account",
        ),
    },
    footer_reasons={
        "account": "Recebeu este e-mail porque diz respeito à sua conta Portfyl.",
        "address": "Recebeu este e-mail porque alguém introduziu este endereço no Portfyl.",
    },
    footer_help="Precisa de ajuda? support@portfyl.com",
    months=(
        "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ),
    date_pattern="{day} de {month} de {year}",
    datetime_pattern="{date}, {time} UTC",
)
