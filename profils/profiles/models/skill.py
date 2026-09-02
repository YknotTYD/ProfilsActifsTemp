##models/skill.py

from django.db import models

from .. import constants as c
from ..skills import normalize_skill_name


class Skill(models.Model):
    """Competence du referentiel (section 3).

    `slug` est la cle normalisee produite par `skills.normalize_skill_name` :
    c'est elle qui porte l'unicite, pas le libelle. `Java`, `java` et `JAVA`
    donnent la meme cle et donc la meme ligne.
    """

    slug     = models.SlugField(max_length = 80, unique = True)
    name     = models.CharField(max_length = 80)
    category = models.CharField(
        max_length = 20, choices = c.SKILL_CATEGORIES, default = c.SKILL_CATEGORY_OTHER
    )
    description = models.TextField(blank = True, default = "")
    created_at  = models.DateTimeField(auto_now_add = True)

    class Meta:
        ordering = ("name",)
        indexes  = (
            models.Index(fields = ["category"]),
            models.Index(fields = ["name"]),
        )

    def __str__(self):
        return f"Skill<{self.slug}>"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = normalize_skill_name(self.name)
        super().save(*args, **kwargs)


class SkillAlias(models.Model):
    """Orthographe supplementaire pointant vers une competence.

    Sert aux cas que la normalisation ne peut pas rapprocher toute seule :
    `NodeJS` et `Node.js` donnent deux cles distinctes, un alias les reunit.
    """

    skill      = models.ForeignKey(Skill, on_delete = models.CASCADE, related_name = "aliases")
    normalized = models.SlugField(max_length = 80, unique = True)
    label      = models.CharField(max_length = 80, blank = True, default = "")

    class Meta:
        ordering = ("normalized",)

    def __str__(self):
        return f"SkillAlias<{self.normalized} -> {self.skill_id}>"


class UserSkill(models.Model):
    """Competence declaree par un profil, avec son niveau (section 3).

    `level_rank` double `level` : la comparaison `niveau minimum` doit se faire
    en SQL sur un entier indexe. Les deux sont tenus coherents par `save`, le
    rang n'est jamais renseigne a la main.
    """

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE, related_name = "skills",
    )
    skill = models.ForeignKey(Skill, on_delete = models.PROTECT, related_name = "holders")

    level      = models.CharField(
        max_length = 24, choices = c.SKILL_LEVELS, default = c.LEVEL_BEGINNER
    )
    level_rank = models.PositiveSmallIntegerField(default = 0, editable = False)

    years_experience = models.PositiveSmallIntegerField(null = True, blank = True)
    order            = models.PositiveIntegerField(default = 0)
    added_at         = models.DateTimeField(auto_now_add = True)
    updated_at       = models.DateTimeField(auto_now = True)

    # -- future preuve / certification (section 3) -------------------------- #
    evidence_url = models.URLField(max_length = 1024, blank = True, default = "")
    evidence_certification = models.ForeignKey(
        "profiles.Certification", on_delete = models.SET_NULL,
        null = True, blank = True, related_name = "proven_skills",
    )

    class Meta:
        ordering    = ("order", "-level_rank", "skill__name")
        constraints = (
            models.UniqueConstraint(
                fields = ("profile", "skill"), name = "unique_skill_per_profile"
            ),
        )
        indexes = (
            # l'index de la recherche par competence et niveau minimum
            models.Index(fields = ["skill", "level_rank"]),
            models.Index(fields = ["skill", "years_experience"]),
            models.Index(fields = ["profile", "order"]),
        )

    def __str__(self):
        return f"UserSkill<{self.profile_id}:{self.skill_id} {self.level}>"

    def save(self, *args, **kwargs):
        self.level_rank = c.skill_level_rank(self.level)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "level_rank"}
        super().save(*args, **kwargs)

    @property
    def level_label(self) -> str:
        return dict(c.SKILL_LEVELS).get(self.level, self.level)


class SkillLink(models.Model):
    """Base des tables d'association <section professionnelle> / competence.

    Experiences, formations, certifications, projets et videos referencent tous
    le meme referentiel `Skill`, de la meme facon. La classe abstraite evite
    d'ecrire cinq fois la meme chose et garantit que la relation a la meme
    forme partout, ce dont depend la future recherche video (section 19).
    """

    skill = models.ForeignKey(Skill, on_delete = models.CASCADE, related_name = "+")
    order = models.PositiveIntegerField(default = 0)

    class Meta:
        abstract = True
        ordering = ("order", "id")
