##models/language.py

from django.db import models

from .. import constants as c


class Language(models.Model):
    """Langue du referentiel (section 8).

    Meme principe que `Skill` : une ligne par langue, referencee par code, pour
    que `Francais` et `francais` ne fassent pas deux entrees et que le filtre
    de recherche porte sur une cle stable.
    """

    code = models.CharField(
        max_length = 8, unique = True,
        help_text = "code ISO 639-1, par exemple fr"
    )
    name = models.CharField(max_length = 80)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"Language<{self.code}>"

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().lower()
        super().save(*args, **kwargs)


class UserLanguage(models.Model):
    """Langue declaree par un profil, au niveau CECRL.

    `level_rank` joue le meme role que sur `UserSkill` : filtrer sur
    "anglais B2 minimum" doit rester une comparaison d'entiers indexee.
    """

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE, related_name = "languages",
    )
    language = models.ForeignKey(Language, on_delete = models.PROTECT, related_name = "speakers")

    level      = models.CharField(max_length = 12, choices = c.LANGUAGE_LEVELS, default = c.CEFR_B1)
    level_rank = models.PositiveSmallIntegerField(default = 0, editable = False)
    order      = models.PositiveIntegerField(default = 0)

    class Meta:
        ordering    = ("order", "-level_rank", "language__name")
        constraints = (
            models.UniqueConstraint(
                fields = ("profile", "language"), name = "unique_language_per_profile"
            ),
        )
        indexes = (
            models.Index(fields = ["language", "level_rank"]),
            models.Index(fields = ["profile", "order"]),
        )

    def __str__(self):
        return f"UserLanguage<{self.profile_id}:{self.language_id} {self.level}>"

    def save(self, *args, **kwargs):
        self.level_rank = c.language_level_rank(self.level)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "level_rank"}
        super().save(*args, **kwargs)

    @property
    def level_label(self) -> str:
        return dict(c.LANGUAGE_LEVELS).get(self.level, self.level)
