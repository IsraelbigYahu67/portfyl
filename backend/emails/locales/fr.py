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
        EmailKind.PASSWORD_CHANGED: EmailContent(
            subject="Votre mot de passe Portfyl a été modifié",
            preheader="Si c'était vous, il n'y a rien d'autre à faire.",
            heading="Votre mot de passe a été modifié",
            paragraphs=(
                "Le mot de passe de **{email}** vient d'être modifié. Si c'était vous, il n'y a rien d'autre à faire.",
            ),
            facts=(("Quand", "{datetime}"),),
            button="Ce n'était pas moi",
            note="Le bouton vous permet de réinitialiser tout de suite le mot de passe. Si cela ne fonctionne pas, écrivez à support@portfyl.com.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETION_SCHEDULED: EmailContent(
            subject="Votre compte Portfyl sera supprimé le {date}",
            preheader="Vous pouvez changer d'avis d'ici là.",
            heading="La suppression du compte est programmée",
            paragraphs=(
                "Vous nous avez demandé de supprimer votre compte Portfyl et toutes ses données. Vous pouvez changer d'avis jusqu'à la date ci-dessous.",
            ),
            facts=(("Compte", "{email}"), ("Suppression le", "{date}")),
            button="Conserver mon compte",
            note="Si vous n'êtes pas à l'origine de cette demande, annulez-la avec le bouton et changez votre mot de passe.",
            footer_reason="account",
        ),
        EmailKind.ACCOUNT_DELETED: EmailContent(
            subject="Votre compte Portfyl a été supprimé",
            preheader="Le dernier e-mail concernant ce compte.",
            heading="Votre compte est supprimé",
            paragraphs=(
                "Nous avons supprimé le compte **{email}** et ses données, comme vous l'avez demandé. C'est le dernier e-mail que nous vous envoyons à ce sujet.",
                "Vous pouvez revenir et en créer un nouveau quand vous voulez.",
            ),
            note="Une question ? Écrivez à support@portfyl.com.",
            footer_reason="account",
        ),
    },
    footer_reasons={
        "account": "Vous recevez cet e-mail parce qu'il concerne votre compte Portfyl.",
        "address": "Vous recevez cet e-mail parce que quelqu'un a saisi cette adresse sur Portfyl.",
    },
    footer_help="Besoin d'aide ? support@portfyl.com",
    months=(
        "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ),
    date_pattern="{day} {month} {year}",
    datetime_pattern="{date}, {time} UTC",
)
