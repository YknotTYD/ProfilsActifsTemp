##models/video.py
"""Modele video (sections 15 a 19).

Cette version n'implemente **ni upload, ni feed**. Ce qui est en place est la
structure de donnees et les regles d'acces, pour qu'un feed vertical puisse
etre branche plus tard sans reprendre le schema :

    recherche -> profils correspondants -> videos de ces profils -> feed

Le nom `Video` est deja pris par `mainapp.Video` (le feed de demonstration par
URL). On prend donc `ProfileVideo`, comme le prevoit la clause d'adaptation aux
noms existants.

La specification distingue `Video` et `UserVideo` ; une video appartenant
toujours a exactement un profil, la relation est portee par une cle etrangere
plutot que par une table d'association qui n'aurait jamais plus d'une ligne.
"""

from django.db    import models
from django.utils import timezone

from .. import constants as c
from .skill import SkillLink


class ProfileVideo(models.Model):
    """Video courte rattachee a un profil professionnel."""

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE, related_name = "videos",
    )

    title       = models.CharField(max_length = 160)
    description = models.TextField(blank = True, default = "")

    #: en attendant un stockage de fichiers, comme le reste du projet
    file_url      = models.CharField(max_length = 1024, blank = True, default = "")
    thumbnail_url = models.CharField(max_length = 1024, blank = True, default = "")
    duration_seconds = models.PositiveIntegerField(null = True, blank = True)

    status = models.CharField(
        max_length = 16, choices = c.VIDEO_STATUSES, default = c.VIDEO_DRAFT
    )
    visibility = models.CharField(
        max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC
    )

    tags = models.JSONField(default = list, blank = True)

    created_at   = models.DateTimeField(auto_now_add = True)
    updated_at   = models.DateTimeField(auto_now = True)
    published_at = models.DateTimeField(null = True, blank = True)

    # -- statistiques, alimentees plus tard par le feed --------------------- #
    view_count = models.PositiveIntegerField(default = 0)
    like_count = models.PositiveIntegerField(default = 0)
    share_count = models.PositiveIntegerField(default = 0)

    class Meta:
        ordering = ("-published_at", "-created_at")
        indexes  = (
            models.Index(fields = ["profile", "status"]),
            models.Index(fields = ["status", "-published_at"]),
            models.Index(fields = ["visibility"]),
        )

    def __str__(self):
        return f"ProfileVideo<{self.profile_id}:{self.title}>"

    def save(self, *args, **kwargs):
        # la date de publication decoule du statut ; la laisser au client
        # ouvrirait la porte a une video "publiee hier" apparue ce matin.
        if self.status == c.VIDEO_PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "published_at"}
        super().save(*args, **kwargs)

    @property
    def is_published(self) -> bool:
        return self.status in c.VISIBLE_VIDEO_STATUSES

    def skill_names(self) -> list[str]:
        return [link.skill.name for link in self.skill_links.all()]


class ProfileVideoSkill(SkillLink):
    """Competence mise en avant par une video (section 17).

    Une video peut porter plusieurs competences :

        "Je developpe une API Rust" -> Rust, REST API, PostgreSQL

    L'index sur `skill` est ce qui permettra a la future recherche video
    (section 19) de partir d'une competence pour remonter aux videos.
    """

    video = models.ForeignKey(
        ProfileVideo, on_delete = models.CASCADE, related_name = "skill_links",
    )

    class Meta(SkillLink.Meta):
        constraints = (
            models.UniqueConstraint(
                fields = ("video", "skill"), name = "unique_skill_per_video"
            ),
        )
        indexes = (models.Index(fields = ["skill"]),)
