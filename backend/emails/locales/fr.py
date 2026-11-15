"""French e-mail copy (vous, "e-mail" as in the app dictionary)."""

from emails.catalog import EmailContent, EmailKind, Locale

LOCALE = Locale(
    messages={
        EmailKind.VERIFY_EMAIL: EmailContent(
            subject="Confirmez votre e-mail pour Portfyl",
            preheader="Un clic et votre compte est prêt.",
            heading="Confirmez votre e-mail",
            paragraphs=(
                "Bienvenue sur Portfyl ! Confirmez **{email}** "
                "pour terminer la création de votre compte.",
            ),
            button="Confirmer l'e-mail",
            note="Si vous n'avez pas créé de compte Portfyl, "
            "vous pouvez ignorer cet e-mail.",
            footer_reason="address",
        ),
        EmailKind.PASSWORD_RESET: EmailContent(
            subject="Réinitialisez votre mot de passe Portfyl",
            preheader="Choisissez un nouveau mot de passe. Le lien est valable 1 heure.",
            heading="Réinitialiser votre mot de passe",
            paragraphs=(
                "Nous avons reçu une demande de réinitialisation du mot de passe "
                "de **{email}**. Choisissez-en un nouveau avec le bouton ci-dessous. "
                "Le lien est valable 1 heure.",
            ),
            button="Choisissez un nouveau mot de passe",
            note="Si vous n'êtes pas à l'origine de cette demande, vous pouvez "
            "ignorer cet e-mail. Votre mot de passe reste inchangé.",
            footer_reason="address",
        ),
    },
    footer_reasons={
        "account": "Vous recevez cet e-mail parce qu'il concerne votre compte Portfyl.",
        "address": "Vous recevez cet e-mail parce que quelqu'un a saisi cette adresse sur Portfyl.",
    },
    footer_help="Besoin d'aide ? support@portfyl.com",
)
