"""Parcours : experiences, formations, certifications, projets.

Ces quatre sections ont la meme forme : une entree datee, rattachee a un
profil, qui reference des competences du referentiel via une table
d'association. Rien n'est stocke en texte libre de ce qui doit rester
recherchable.
"""

from django.core.exceptions import ValidationError
from django.db              import models
from django.utils           import timezone

from .. import constants as c
from .skill import SkillLink

class DatedEntry(models.Model):
    """Entree datee d'un parcours, avec periode eventuellement en cours."""

    start_date = models.DateField()
    end_date   = models.DateField(null = True, blank = True)
    is_current = models.BooleanField(default = False)
    order      = models.PositiveIntegerField(default = 0)
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)

    class Meta:
        abstract = True
        ordering = ("-is_current", "-start_date", "order")

    def clean(self):
        if self.is_current:
            self.end_date = None
        elif self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError("la date de fin precede la date de debut")

    def save(self, *args, **kwargs):
        self.clean()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "end_date"}
        super().save(*args, **kwargs)

    def period(self) -> tuple:
        """Couple (debut, fin) exploitable, la fin valant aujourd'hui si en cours."""
        end = self.end_date or timezone.localdate()
        return self.start_date, max(end, self.start_date)

    @property
    def duration_months(self) -> int:
        start, end = self.period()
        return max(0, (end.year - start.year) * 12 + (end.month - start.month))

class WorkExperience(DatedEntry):

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE, related_name = "experiences",
    )
    title       = models.CharField(max_length = 160)
    company     = models.CharField(max_length = 160)
    description = models.TextField(blank = True, default = "")

    location_city    = models.CharField(max_length = 120, blank = True, default = "")
    location_country = models.CharField(max_length = 2, blank = True, default = "")
    contract_type    = models.CharField(
        max_length = 20, choices = c.CONTRACT_TYPES, blank = True, default = ""
    )

    class Meta(DatedEntry.Meta):
        indexes = (
            models.Index(fields = ["profile", "-start_date"]),
            models.Index(fields = ["company"]),
        )

    def __str__(self):
        return f"WorkExperience<{self.profile_id}:{self.title}>"

class WorkExperienceSkill(SkillLink):

    experience = models.ForeignKey(
        WorkExperience, on_delete = models.CASCADE, related_name = "skill_links",
    )

    class Meta(SkillLink.Meta):
        constraints = (
            models.UniqueConstraint(
                fields = ("experience", "skill"), name = "unique_skill_per_experience"
            ),
        )
        indexes = (models.Index(fields = ["skill"]),)

class Education(DatedEntry):

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE, related_name = "education",
    )
    institution    = models.CharField(max_length = 160)
    degree         = models.CharField(max_length = 160, blank = True, default = "")
    degree_level   = models.CharField(
        max_length = 20, choices = c.DEGREE_LEVELS, blank = True, default = ""
    )
    field_of_study = models.CharField(max_length = 160, blank = True, default = "")
    description    = models.TextField(blank = True, default = "")

    diploma_url = models.URLField(max_length = 1024, blank = True, default = "")
    diploma_verified = models.BooleanField(default = False)

    class Meta(DatedEntry.Meta):
        verbose_name_plural = "education"
        indexes = (
            models.Index(fields = ["profile", "-start_date"]),
            models.Index(fields = ["degree_level"]),
            models.Index(fields = ["institution"]),
        )

    def __str__(self):
        return f"Education<{self.profile_id}:{self.institution}>"

class EducationSkill(SkillLink):

    education = models.ForeignKey(
        Education, on_delete = models.CASCADE, related_name = "skill_links",
    )

    class Meta(SkillLink.Meta):
        constraints = (
            models.UniqueConstraint(
                fields = ("education", "skill"), name = "unique_skill_per_education"
            ),
        )
        indexes = (models.Index(fields = ["skill"]),)

class Certification(models.Model):

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE, related_name = "certifications",
    )
    name   = models.CharField(max_length = 160)
    issuer = models.CharField(max_length = 160, blank = True, default = "")

    issued_on  = models.DateField(null = True, blank = True)
    expires_on = models.DateField(null = True, blank = True)

    credential_id    = models.CharField(max_length = 160, blank = True, default = "")
    verification_url = models.URLField(max_length = 1024, blank = True, default = "")

    order      = models.PositiveIntegerField(default = 0)
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)

    class Meta:
        ordering = ("-issued_on", "order", "id")
        indexes  = (
            models.Index(fields = ["profile", "-issued_on"]),
            models.Index(fields = ["issuer"]),
        )

    def __str__(self):
        return f"Certification<{self.profile_id}:{self.name}>"

    def clean(self):
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            raise ValidationError("la date d'expiration precede la date d'obtention")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_on and self.expires_on < timezone.localdate())

class CertificationSkill(SkillLink):

    certification = models.ForeignKey(
        Certification, on_delete = models.CASCADE, related_name = "skill_links",
    )

    class Meta(SkillLink.Meta):
        constraints = (
            models.UniqueConstraint(
                fields = ("certification", "skill"), name = "unique_skill_per_certification"
            ),
        )
        indexes = (models.Index(fields = ["skill"]),)

class Project(models.Model):

    profile = models.ForeignKey(
        "profiles.ProfessionalProfile", on_delete = models.CASCADE, related_name = "projects",
    )
    title       = models.CharField(max_length = 160)
    description = models.TextField(blank = True, default = "")
    role        = models.CharField(max_length = 160, blank = True, default = "")
    url         = models.URLField(max_length = 1024, blank = True, default = "")

    started_on = models.DateField(null = True, blank = True)
    ended_on   = models.DateField(null = True, blank = True)

    video = models.ForeignKey(
        "profiles.ProfileVideo", on_delete = models.SET_NULL,
        null = True, blank = True, related_name = "projects",
    )

    order      = models.PositiveIntegerField(default = 0)
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)

    class Meta:
        ordering = ("order", "-started_on", "id")
        indexes  = (models.Index(fields = ["profile", "order"]),)

    def __str__(self):
        return f"Project<{self.profile_id}:{self.title}>"

    def clean(self):
        if self.started_on and self.ended_on and self.ended_on < self.started_on:
            raise ValidationError("la date de fin precede la date de debut")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

class ProjectSkill(SkillLink):

    project = models.ForeignKey(
        Project, on_delete = models.CASCADE, related_name = "skill_links",
    )

    class Meta(SkillLink.Meta):
        constraints = (
            models.UniqueConstraint(
                fields = ("project", "skill"), name = "unique_skill_per_project"
            ),
        )
        indexes = (models.Index(fields = ["skill"]),)
