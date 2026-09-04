##models/video.py

"""
Modele video (sections 15 a 19, et moderation).

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
    #: URL de lecture -- celle fournie par l'utilisateur pour une video par
    #: lien. Le nom est conserve tel quel (plutot que "external_url") pour ne
    #: pas casser le feed, la recherche et les 193 tests qui le lisent deja.
    file_url      = models.CharField(max_length = 1024, blank = True, default = "")
    thumbnail_url = models.CharField(max_length = 1024, blank = True, default = "")
    duration_seconds = models.PositiveIntegerField(null = True, blank = True)

    #: reserve a l'upload par fichier (en cours de construction ailleurs) :
    #: stockage en blob brut, decide plus simple a operer qu'un volume de
    #: fichiers pour ce projet. Ni lu ni ecrit tant que `source_type` ne vaut
    #: pas `FILE`.
    file_blob         = models.BinaryField(null = True, blank = True, editable = False)
    file_content_type = models.CharField(max_length = 100, blank = True, default = "")
    file_size         = models.PositiveIntegerField(null = True, blank = True)

    #: video de presentation du profil (section 2). Une seule peut etre a la
    #: fois publiee pour un meme profil : voir la contrainte plus bas.
    is_presentation = models.BooleanField(default = False)
    #: renseigne le temps d'un remplacement : la video que celle-ci doit
    #: retirer une fois que l'utilisateur aura confirme (voir `services.
    #: publish_presentation_video`). L'ancienne reste en ligne jusque-la.
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

    #: motif de refus (section 1) : visible du proprietaire, jamais du public.
    #: efface des que la video quitte l'etat refusee -- un ancien motif ne
    #: doit pas survivre a une nouvelle soumission.
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
        constraints = (
            # la garantie "une seule presentation active par profil" (section
            # 2) est tenue ici, pas en Python : un index partiel refuse la
            # deuxieme ligne au niveau base, y compris entre deux requetes
            # concurrentes, la ou une verification applicative arriverait
            # toujours une transaction trop tard.
            models.UniqueConstraint(
                fields    = ("profile",),
                condition = Q(is_presentation = True, status = c.VIDEO_PUBLISHED),
                name      = "one_published_presentation_per_profile",
            ),
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
        mode, url = playback(self.source_type, self.file_url, video_id=self.id)
        return {"mode": mode, "url": url}

class VideoModerationEvent(models.Model):
    """
    Historique de moderation d'une video (section "Historique de moderation").

    Ecrit exclusivement par `moderation.transition_video`, dans la meme
    transaction que le changement de statut qu'il decrit : l'historique ne
    peut donc jamais diverger de l'etat reellement en base. Aucune route
    d'ecriture ni de suppression n'existe pour ce modele -- il est
    consultable par les administrateurs, mais n'appartient a personne.
    """

    video = models.ForeignKey(
        ProfileVideo, on_delete = models.CASCADE, related_name = "moderation_events",
    )
    #: identite de l'auteur quand il y en a une (proprietaire ou admin) ; nulle
    #: pour une transition automatique, ou pour un appel interne sans acteur
    #: identifie (scripts, tests).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null = True, blank = True,
        on_delete = models.SET_NULL, related_name = "+",
    )
    #: type d'acteur, meme quand `actor` est nul -- c'est ce champ, pas
    #: `actor`, qui repond a "qui a fait quoi" pour un traitement automatique.
    source = models.CharField(max_length = 8, choices = c.MODERATION_ACTORS)

    old_status = models.CharField(max_length = 16, choices = c.VIDEO_STATUSES, blank = True, default = "")
    new_status = models.CharField(max_length = 16, choices = c.VIDEO_STATUSES)
    reason     = models.TextField(blank = True, default = "")

    created_at = models.DateTimeField(auto_now_add = True)
    #: renseigne quand l'evenement sort de la fenetre d'historique "vivant"
    #: (par defaut 7 jours, voir `constants.REJECTION_HISTORY_DAYS`). La ligne
    #: n'est jamais supprimee -- elle bascule juste dans l'onglet "archives"
    #: de la console de moderation. Pose par `archive_moderation_history` ou,
    #: paresseusement, a la lecture de la liste des refus.
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
