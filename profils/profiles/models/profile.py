
from django.contrib.auth.models import User
from django.core.exceptions      import ValidationError
from django.db                   import models

from .. import constants as c

class ProfessionalProfile(models.Model):
    """Profil professionnel d'un utilisateur.

    Le profil porte ce qui se filtre et se trie en recherche ; tout ce qui est
    une liste (competences, experiences, formations...) vit dans une table
    dediee. Deux champs sont volontairement denormalises parce qu'ils sont
    interroges a chaque recherche et qu'ils se recalculent a l'ecriture, pas a
    la lecture :

      * `total_experience_months`, somme des experiences (section 14) ;
      * `visibility`, qui evite une jointure sur le filtre le plus selectif.

    Le nom et le prenom restent sur `auth.User` : les dupliquer ici ferait
    deux sources de verite pour la meme information.
    """

    user = models.OneToOneField(
        User, on_delete = models.CASCADE, related_name = "professional_profile"
    )

    headline = models.CharField(
        max_length = 160, blank = True, default = "",
        help_text = "titre professionnel, par exemple 'Developpeur backend Java'"
    )
    summary  = models.TextField(blank = True, default = "")

    photo_url = models.CharField(max_length = 1024, blank = True, default = "")
    cover_url = models.CharField(max_length = 1024, blank = True, default = "")

    cover_color = models.CharField(
        max_length = 20, choices = c.COVER_COLORS, blank = True, default = c.DEFAULT_COVER_COLOR,
    )

    location_city    = models.CharField(max_length = 120, blank = True, default = "")
    location_region  = models.CharField(max_length = 120, blank = True, default = "")
    location_country = models.CharField(
        max_length = 2, blank = True, default = "",
        help_text = "code pays ISO 3166-1 alpha-2, par exemple FR"
    )

    professional_field = models.CharField(
        max_length = 24, choices = c.PROFESSIONAL_FIELDS, blank = True, default = ""
    )

    availability_status = models.CharField(
        max_length = 24, choices = c.AVAILABILITY_STATUSES,
        default = c.AVAILABILITY_NOT_LOOKING,
    )
    available_from = models.DateField(null = True, blank = True)

    open_to_remote = models.BooleanField(default = False)
    open_to_hybrid = models.BooleanField(default = False)
    open_to_onsite = models.BooleanField(default = False)

    willing_to_relocate = models.BooleanField(default = False)
    mobility_radius_km  = models.PositiveIntegerField(null = True, blank = True)
    mobility_note       = models.CharField(max_length = 240, blank = True, default = "")

    visibility = models.CharField(
        max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_REGISTERED_USERS,
    )

    total_experience_months = models.PositiveIntegerField(default = 0)

    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)

    class Meta:
        ordering    = ("-updated_at",)
        permissions = (
            ("manage_skill_catalog",  "Peut gerer le referentiel de competences"),
            ("view_private_profile",  "Peut consulter un profil prive"),
            ("moderate_profile",      "Peut moderer un profil"),
        )
        indexes = (
            models.Index(fields = ["visibility", "availability_status"]),
            models.Index(fields = ["professional_field"]),
            models.Index(fields = ["location_country", "location_city"]),
            models.Index(fields = ["total_experience_months"]),
            models.Index(fields = ["updated_at"]),
        )

    def __str__(self):
        return f"ProfessionalProfile<{self.user.username}>"

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating:
            ProfileVisibility.objects.get_or_create(profile = self)
            ProfileSearchSettings.objects.get_or_create(profile = self)

    @classmethod
    def for_user(cls, user) -> "ProfessionalProfile":
        """Profil de `user`, cree a la volee la premiere fois."""
        profile, _ = cls.objects.get_or_create(user = user)
        return profile

    @property
    def username(self) -> str:
        return self.user.username

    @property
    def full_name(self) -> str:
        name = f"{self.user.first_name} {self.user.last_name}".strip()
        return name or self.user.username

    @property
    def initials(self) -> str:
        return "".join(part[0] for part in self.full_name.split()[:2]).upper() or "?"

    @property
    def location_label(self) -> str:
        parts = [self.location_city, self.location_region, self.location_country]
        return ", ".join(part for part in parts if part)

    @property
    def total_experience_years(self) -> float:
        return round(self.total_experience_months / 12, 1)

    @property
    def is_available(self) -> bool:
        return self.availability_status in c.AVAILABLE_STATUSES

    @property
    def work_modes(self) -> list[str]:
        return [
            mode for mode, field in c.WORK_MODE_FIELDS.items() if getattr(self, field)
        ]

    def contract_type_codes(self) -> list[str]:
        return [row.contract_type for row in self.contract_types.all()]

    def visibility_settings(self) -> "ProfileVisibility":
        settings = getattr(self, "visibility_config", None)
        return settings if settings is not None else ProfileVisibility(profile = self)

    def search_settings(self) -> "ProfileSearchSettings":
        settings = getattr(self, "search_config", None)
        return settings if settings is not None else ProfileSearchSettings(profile = self)

    @property
    def searchable(self) -> bool:
        return self.search_settings().searchable

    def recompute_experience(self, *, save: bool = True) -> int:
        """Recalcule la duree totale d'experience a partir des experiences.

        Les periodes qui se chevauchent ne sont comptees qu'une fois : deux
        postes menes de front sur la meme annee ne valent pas deux annees
        d'experience.
        """
        periods = sorted(
            (row.period() for row in self.experiences.all()),
            key = lambda period: period[0],
        )

        months, current = 0, None
        for start, end in periods:
            if current is None or start > current[1]:
                if current is not None:
                    months += _months_between(*current)
                current = [start, end]
            elif end > current[1]:
                current[1] = end
        if current is not None:
            months += _months_between(*current)

        if months != self.total_experience_months:
            self.total_experience_months = months
            if save:
                self.save(update_fields = ["total_experience_months", "updated_at"])
        return months

def _months_between(start, end) -> int:
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))

class ProfileVisibility(models.Model):
    """Visibilite section par section (section 11).

    La visibilite effective d'une section est **la plus restrictive** des deux :
    regler la section sur PUBLIC ne la sort pas d'un profil PRIVATE. C'est
    `visibility.section_audience` qui applique cette regle, une seule fois,
    cote serveur.
    """

    profile = models.OneToOneField(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE,
        related_name = "visibility_config",
    )

    skills_visibility         = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC)
    experiences_visibility    = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC)
    education_visibility      = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC)
    certifications_visibility = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC)
    languages_visibility      = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC)
    projects_visibility       = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC)
    availability_visibility   = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_REGISTERED_USERS)
    videos_visibility         = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC)
    links_visibility          = models.CharField(max_length = 20, choices = c.VISIBILITIES, default = c.VISIBILITY_PUBLIC)

    def __str__(self):
        return f"ProfileVisibility<{self.profile_id}>"

    def of(self, section: str) -> str:
        """Visibilite declaree pour une section, sans arbitrage."""
        field = c.SECTION_VISIBILITY_FIELDS.get(section)
        if field is None:
            raise ValidationError(f"section inconnue: {section!r}")
        return getattr(self, field)

    def as_dict(self) -> dict:
        return {section: self.of(section) for section, _ in c.PROFILE_SECTIONS}

class ProfileSearchSettings(models.Model):
    """Reglages de recherche, independants de la visibilite (section 11).

    `searchable` n'a qu'une seule source de verite : cette ligne. La recherche
    joint cette table plutot que de recopier le drapeau sur le profil, ce qui
    garantit qu'un profil ne peut pas etre trouvable ici et non trouvable la.
    Un profil peut etre PUBLIC et refuser d'apparaitre dans les resultats.
    """

    profile = models.OneToOneField(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE,
        related_name = "search_config",
    )

    searchable = models.BooleanField(
        default = True, help_text = "apparaitre dans les resultats de recherche"
    )
    appear_in_video_feed = models.BooleanField(
        default = True, help_text = "reserve au futur feed video (section 18)"
    )
    show_availability_in_results = models.BooleanField(default = True)
    contactable_by_recruiters    = models.BooleanField(default = True)

    class Meta:
        indexes = (models.Index(fields = ["searchable"]),)

    def __str__(self):
        return f"ProfileSearchSettings<{self.profile_id} searchable={self.searchable}>"

class ProfileContractType(models.Model):
    """Type de contrat recherche (section 10).

    Une ligne par contrat plutot qu'une liste JSON : c'est ce qui rend le
    filtre `contract=CDI` indexable et joignable.
    """

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE,
        related_name = "contract_types",
    )
    contract_type = models.CharField(max_length = 20, choices = c.CONTRACT_TYPES)

    class Meta:
        ordering    = ("contract_type",)
        constraints = (
            models.UniqueConstraint(
                fields = ("profile", "contract_type"), name = "unique_contract_per_profile"
            ),
        )
        indexes = (models.Index(fields = ["contract_type"]),)

    def __str__(self):
        return f"ProfileContractType<{self.profile_id}:{self.contract_type}>"

class ProfileLink(models.Model):
    """Portfolio et liens professionnels (section 2)."""

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE, related_name = "links",
    )
    kind  = models.CharField(max_length = 20, choices = c.LINK_KINDS, default = c.LINK_OTHER)
    label = models.CharField(max_length = 120, blank = True, default = "")
    url   = models.URLField(max_length = 1024)
    order = models.PositiveIntegerField(default = 0)

    class Meta:
        ordering = ("order", "id")
        indexes  = (models.Index(fields = ["profile", "order"]),)

    def __str__(self):
        return f"ProfileLink<{self.profile_id}:{self.kind}>"
