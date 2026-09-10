##models/consultation.py
"""Journal de consultation d'un profil (droit d'acces, RGPD art. 15).

Une personne inscrite doit pouvoir savoir qui a regarde son profil et quand.
Ce modele existe pour repondre a cette question-la, et a aucune autre.

Ce qu'il enregistre, volontairement pauvre :

    * quel profil a ete consulte ;
    * quelle **organisation** l'a consulte -- jamais quelle personne physique ;
    * a quel instant.

Ce qu'il n'enregistre pas, tout aussi volontairement : aucune adresse IP,
aucune empreinte de navigateur, aucune geolocalisation, aucun identifiant du
compte recruteur. C'est un journal de transparence pour le candidat, pas un
fichier de surveillance des recruteurs.

L'organisation est **recopiee** au moment de la consultation plutot que liee
par cle etrangere : le candidat doit voir qui l'a consulte a cette date-la,
meme si le recruteur change d'organisation ou ferme son compte ensuite.

Les consultations anonymes ne sont pas enregistrees du tout (voir
`views.profile_page`). L'interface le dit explicitement, pour ne pas laisser
croire a un decompte exhaustif.
"""

from django.db import models


class ProfileConsultation(models.Model):
    """Une consultation d'un profil par un compte recruteur."""

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE,
        related_name = "consultations",
    )

    #: libelle de l'organisation, recopie a l'instant de la consultation.
    organisation = models.CharField(max_length = 160)

    created_at = models.DateTimeField(auto_now_add = True)

    class Meta:
        ordering = ("-created_at",)
        indexes  = (models.Index(fields = ["profile", "-created_at"]),)

    def __str__(self):
        return f"ProfileConsultation<{self.profile_id}:{self.organisation}>"
