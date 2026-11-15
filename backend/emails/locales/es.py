"""Spanish e-mail copy (tú, "e-mail" as in the app dictionary)."""

from emails.catalog import EmailContent, EmailKind, Locale

LOCALE = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Confirma tu e-mail para Portfyl",
            preheader="Un clic y tu cuenta estará lista.",
            heading="Confirma tu e-mail",
            paragraphs=(
                "¡Te damos la bienvenida a Portfyl! Confirma **{email}** "
                "para terminar de configurar tu cuenta.",
            ),
            button="Confirmar e-mail",
            note="Si no has creado una cuenta de Portfyl, puedes ignorar este e-mail.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Restablece tu contraseña de Portfyl",
            preheader="Elige una nueva contraseña. El enlace funciona durante 1 hora.",
            heading="Restablece tu contraseña",
            paragraphs=(
                "Hemos recibido una solicitud para restablecer la contraseña de "
                "**{email}**. Elige una nueva con el botón de abajo. "
                "El enlace funciona durante 1 hora.",
            ),
            button="Elige una nueva contraseña",
            note="Si no lo has solicitado, puedes ignorar este e-mail. "
            "Tu contraseña seguirá siendo la misma.",
            footer_reason="address",
        ),
    },
    footer_reasons={
        "account": "Recibes este e-mail porque trata sobre tu cuenta de Portfyl.",
        "address": "Recibes este e-mail porque alguien ha introducido esta dirección en Portfyl.",
    },
    footer_help="¿Necesitas ayuda? support@portfyl.com",
)
