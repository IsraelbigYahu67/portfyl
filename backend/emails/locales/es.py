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
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="Se ha cambiado tu contraseña de Portfyl",
            preheader="Si fuiste tú, no tienes que hacer nada más.",
            heading="Se ha cambiado tu contraseña",
            paragraphs=(
                "La contraseña de **{email}** se acaba de cambiar. Si fuiste tú, no tienes que hacer nada más.",
            ),
            facts=(("Cuándo", "{datetime}"),),
            button="No fui yo",
            note="Con el botón puedes restablecer la contraseña al instante. Si no funciona, escribe a support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="Tu cuenta de Portfyl se eliminará el {date}",
            preheader="Hasta entonces puedes cambiar de opinión.",
            heading="La eliminación de la cuenta está programada",
            paragraphs=(
                "Nos pediste eliminar tu cuenta de Portfyl y todos sus datos. Puedes cambiar de opinión hasta la fecha indicada abajo.",
            ),
            facts=(("Cuenta", "{email}"), ("La eliminamos el", "{date}")),
            button="Conservar mi cuenta",
            note="Si no lo has solicitado tú, cancélala con el botón y cambia tu contraseña.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="Tu cuenta de Portfyl se ha eliminado",
            preheader="El último e-mail sobre esta cuenta.",
            heading="Tu cuenta está eliminada",
            paragraphs=(
                "Hemos eliminado la cuenta **{email}** y sus datos, como pediste. Es el último e-mail que te enviamos sobre ella.",
                "Puedes volver y crear una nueva cuando quieras.",
            ),
            note="¿Dudas sobre esto? Escribe a support@portfyl.com.",
            footer_reason="account",
        ),
    },
    footer_reasons={
        "account": "Recibes este e-mail porque trata sobre tu cuenta de Portfyl.",
        "address": "Recibes este e-mail porque alguien ha introducido esta dirección en Portfyl.",
    },
    footer_help="¿Necesitas ayuda? support@portfyl.com",
    months=(
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ),
    date_pattern="{day} de {month} de {year}",
    datetime_pattern="{date}, {time} UTC",
)
