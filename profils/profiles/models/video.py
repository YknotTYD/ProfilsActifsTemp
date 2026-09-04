"""Modele video (sections 15 a 19, et moderation).

Le nom `Video` est deja pris par `mainapp.Video` (le feed de demonstration par
URL). On prend donc `ProfileVideo`, comme le prevoit la clause d'adaptation aux
noms existants.

La specification distingue `Video` et `UserVideo` ; une video appartenant
toujours a exactement un profil, la relation est portee par une cle etrangere
plutot que par une table d'association qui n'aurait jamais plus d'une ligne.

La moderation (statuts `PENDING`/`APPROVED`/`REJECTED`, historique) est
documentee dans `constants.py` et appliquee par `moderation.py` : ce module ne
porte que les champs, aucune regle de transition.
"""

from django.conf  import settings
from django.db    import models
from django.db.models import Q
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

    source_type = models.CharField(
        max_length = 8, choices = c.VIDEO_SOURCES, default = c.VIDEO_SOURCE_LINK,
    )
    file_url      = models.CharField(max_length = 1024, blank = True, default = "")
    thumbnail_url = models.CharField(max_length = 1024, blank = True, default = "")
    duration_seconds = models.PositiveIntegerField(null = True, blank = True)

    file_blob         = models.BinaryField(null = True, blank = True, editable = False)
    file_content_type = models.CharField(max_length = 100, blank = True, default = "")
    file_size         = models.PositiveIntegerField(null = True, blank = True)

    is_presentation = models.BooleanField(default = False)
    replaces = models.ForeignKey(
        "self", null = True, blank = True, on_delete = models.SET_NULL,
        related_name = "replaced_by",
    )

    status = models.CharField(
        max_length = 16, choices = c.VIDEO_STATUSES, default = c.VIDEO_DRAFT
    )
    visibility = models.CharField(
        max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC
    )

    rejection_reason = models.TextField(blank = True, default = "")
    moderated_at = models.DateTimeField(null = True, blank = True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null = True, blank = True,
        on_delete = models.SET_NULL, related_name = "+",
    )

    tags = models.JSONField(default = list, blank = True)

    created_at   = models.DateTimeField(auto_now_add = True)
    updated_at   = models.DateTimeField(auto_now = True)
    published_at = models.DateTimeField(null = True, blank = True)

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
        constraints = (
            models.UniqueConstraint(
                fields    = ("profile",),
                condition = Q(is_presentation = True, status = c.VIDEO_PUBLISHED),
                name      = "one_published_presentation_per_profile",
            ),
        )

    def __str__(self):
        return f"ProfileVideo<{self.profile_id}:{self.title}>"

    def save(self, *args, **kwargs):
        if self.status == c.VIDEO_PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "published_at"}
        super().save(*args, **kwargs)

    @property
    def is_published(self) -> bool:
        return self.status in c.VISIBLE_VIDEO_STATUSES

    @property
    def requires_user_action(self) -> str | None:
        """Section 3 : "voir si une action utilisateur est necessaire".

        Une video validee n'est jamais publiee toute seule (section 2) : tant
        que le proprietaire n'a pas confirme, l'interface doit le dire.
        """
        if self.status == c.VIDEO_APPROVED:
            return "CONFIRM_PUBLICATION"
        return None

    def skill_names(self) -> list[str]:
        return [link.skill.name for link in self.skill_links.all()]

    @property
    def playback(self) -> dict:
        """Comment lire cette video : `{"mode": "iframe"|"file", "url": ...}`.

        Une seule source de verite pour le feed, la page de profil et la page
        de gestion -- toutes doivent afficher la meme video de la meme facon.
        """
        from ..feed import playback
        mode, url = playback(self.source_type, self.file_url)
        return {"mode": mode, "url": url}

class VideoModerationEvent(models.Model):
    """Historique de moderation d'une video (section "Historique de moderation").

    Ecrit exclusivement par `moderation.transition_video`, dans la meme
    transaction que le changement de statut qu'il decrit : l'historique ne
    peut donc jamais diverger de l'etat reellement en base. Aucune route
    d'ecriture ni de suppression n'existe pour ce modele -- il est
    consultable par les administrateurs, mais n'appartient a personne.
    """

    video = models.ForeignKey(
        ProfileVideo, on_delete = models.CASCADE, related_name = "moderation_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null = True, blank = True,
        on_delete = models.SET_NULL, related_name = "+",
    )
    source = models.CharField(max_length = 8, choices = c.MODERATION_ACTORS)

    old_status = models.CharField(max_length = 16, choices = c.VIDEO_STATUSES, blank = True, default = "")
    new_status = models.CharField(max_length = 16, choices = c.VIDEO_STATUSES)
    reason     = models.TextField(blank = True, default = "")

    created_at = models.DateTimeField(auto_now_add = True)
    archived_at = models.DateTimeField(null = True, blank = True)

    class Meta:
        ordering = ("-created_at",)
        indexes  = (
            models.Index(fields = ["video", "-created_at"]),
            models.Index(fields = ["new_status", "archived_at", "-created_at"]),
        )

    def __str__(self):
        return f"VideoModerationEvent<{self.video_id}:{self.old_status}->{self.new_status}>"

class ProfileVideoReaction(models.Model):
    """Reaction d'un utilisateur a une video de profil (feed video).

    L'ancien `mainapp.Reaction` est lie a `mainapp.VideoLink` ; le feed etant
    desormais servi par `ProfileVideo` (une seule pile video, moderee), les
    reactions le suivent ici. Une seule reaction par (video, utilisateur) :
    re-cliquer le meme bouton la retire, cliquer l'autre la remplace -- c'est
    la vue qui applique cette bascule, la contrainte garantit juste l'unicite.

    `ProfileVideo.like_count` est le compteur denormalise tenu a jour a chaque
    ecriture (affiche au proprietaire et a l'admin, section 6).
    """

    LIKE    = "like"
    DISLIKE = "dislike"
    REACTIONS = ((LIKE, "J'aime"), (DISLIKE, "Je n'aime pas"))

    video = models.ForeignKey(
        ProfileVideo, on_delete = models.CASCADE, related_name = "reactions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete = models.CASCADE, related_name = "+",
    )
    reaction   = models.CharField(max_length = 8, choices = REACTIONS)
    created_at = models.DateTimeField(auto_now_add = True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields = ("video", "user"), name = "one_reaction_per_video_per_user",
            ),
        )
        indexes = (models.Index(fields = ["video", "reaction"]),)

    def __str__(self):
        return f"ProfileVideoReaction<{self.video_id}:{self.user_id}:{self.reaction}>"

class ProfileVideoView(models.Model):
    """Une vue enregistree d'une video de profil (section 6 : statistiques).

    Une ligne par (spectateur, video) -- un rechargement de page ne regonfle
    pas le compteur. Le spectateur connecte est identifie par `user`, le
    visiteur anonyme par sa cle de session. `ProfileVideo.view_count` est le
    total denormalise, incremente uniquement quand une nouvelle ligne est
    reellement creee.
    """

    video = models.ForeignKey(
        ProfileVideo, on_delete = models.CASCADE, related_name = "views",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null = True, blank = True,
        on_delete = models.SET_NULL, related_name = "+",
    )
    session_key = models.CharField(max_length = 40, blank = True, default = "")
    created_at  = models.DateTimeField(auto_now_add = True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields = ("video", "user"),
                condition = Q(user__isnull = False),
                name = "one_view_per_video_per_user",
            ),
            models.UniqueConstraint(
                fields = ("video", "session_key"),
                condition = Q(user__isnull = True) & ~Q(session_key = ""),
                name = "one_view_per_video_per_session",
            ),
        )
        indexes = (models.Index(fields = ["video", "-created_at"]),)

    def __str__(self):
        return f"ProfileVideoView<{self.video_id}:{self.user_id or self.session_key}>"

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
