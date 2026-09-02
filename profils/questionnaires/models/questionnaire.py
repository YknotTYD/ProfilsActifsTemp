##models/questionnaire.py

import uuid

from django.contrib.auth.models import User
from django.core.exceptions      import ValidationError
from django.db                   import models
from django.utils                import timezone

from .. import constants as c
from ..question_types import get_type, type_choices


def new_stable_key() -> str:
    """Identifiant stable, conserve d'une version a l'autre."""
    return uuid.uuid4().hex


class Questionnaire(models.Model):
    """Identite durable d'un questionnaire.

    Porte ce qui evolue legitimement dans le temps (statut, regles d'acces,
    regles de tentative, fenetre de disponibilite). Tout ce qui doit rester
    reproductible pour une tentative passee vit sur `QuestionnaireVersion`.
    """

    slug        = models.SlugField(max_length = 120, unique = True)
    title       = models.CharField(max_length = 255)
    description = models.TextField(blank = True, default = "")
    status      = models.CharField(
        max_length = 12, choices = c.QUESTIONNAIRE_STATUSES, default = c.STATUS_DRAFT
    )

    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)
    created_by = models.ForeignKey(
        User, on_delete = models.SET_NULL, null = True, blank = True,
        related_name = "created_questionnaires"
    )

    current_version = models.ForeignKey(
        "questionnaires.QuestionnaireVersion", on_delete = models.SET_NULL,
        null = True, blank = True, related_name = "+"
    )

    # -- fenetre de disponibilite (section 17) ------------------------------ #
    available_from  = models.DateTimeField(null = True, blank = True)
    available_until = models.DateTimeField(null = True, blank = True)

    # -- regles de tentative (section 15) ----------------------------------- #
    max_attempts           = models.PositiveIntegerField(
        null = True, blank = True,
        help_text = "None = tentatives illimitees"
    )
    cooldown_seconds       = models.PositiveIntegerField(default = 0)
    time_limit_seconds     = models.PositiveIntegerField(
        null = True, blank = True,
        help_text = "duree maximale d'une tentative une fois commencee"
    )
    attempt_expiry_seconds = models.PositiveIntegerField(
        null = True, blank = True,
        help_text = "delai au-dela duquel une tentative inachevee expire"
    )
    allow_retry_after_pass = models.BooleanField(default = False)
    allow_retry_after_fail = models.BooleanField(default = True)
    keep_previous_attempts = models.BooleanField(default = True)
    carry_over_answers     = models.BooleanField(
        default = True,
        help_text = "reporter les reponses des participants lors d'une nouvelle version"
    )

    # -- regles de modification des reponses (section 16) ------------------- #
    answer_edit_mode = models.CharField(
        max_length = 20, choices = c.ANSWER_EDIT_MODES, default = c.ANSWERS_UNTIL_FINISH
    )
    navigation_mode  = models.CharField(
        max_length = 10, choices = c.NAVIGATION_MODES, default = c.NAVIGATION_FREE
    )
    allow_back       = models.BooleanField(default = True)

    # -- visibilite des resultats (section 23) ------------------------------ #
    result_visibility = models.JSONField(default = dict, blank = True)

    class Meta:
        ordering    = ("-updated_at",)
        permissions = (
            ("publish_questionnaire",    "Peut publier un questionnaire"),
            ("archive_questionnaire",    "Peut archiver un questionnaire"),
            ("invalidate_questionnaire", "Peut invalider un questionnaire"),
            ("test_questionnaire",       "Peut tester un questionnaire"),
            ("manage_versions",          "Peut gerer les versions"),
            ("manage_access",            "Peut gerer les regles d'acces"),
            ("view_attempts",            "Peut consulter les tentatives"),
            ("view_results",             "Peut consulter les resultats"),
            ("view_statistics",          "Peut consulter les statistiques"),
            ("manage_badges",            "Peut gerer les badges"),
        )
        indexes = (
            models.Index(fields = ["status"]),
            models.Index(fields = ["available_from", "available_until"]),
        )

    def __str__(self):
        return f"Questionnaire<{self.pk}:{self.title}>"

    # ------------------------------------------------------------------ #

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._build_slug()
        if not self.result_visibility:
            self.result_visibility = dict(c.DEFAULT_RESULT_VISIBILITY)
        super().save(*args, **kwargs)

    def _build_slug(self) -> str:
        from django.utils.text import slugify

        base = slugify(self.title)[:100] or "questionnaire"
        slug, index = base, 2
        while Questionnaire.objects.filter(slug = slug).exclude(pk = self.pk).exists():
            slug = f"{base}-{index}"
            index += 1
        return slug

    @property
    def visibility_settings(self) -> dict:
        return {**c.DEFAULT_RESULT_VISIBILITY, **(self.result_visibility or {})}

    def is_within_availability(self, now = None) -> bool:
        now = now or timezone.now()
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return True

    def latest_version(self):
        return self.versions.order_by("-version_number").first()

    def draft_version(self):
        return self.versions.filter(status = c.STATUS_DRAFT).order_by("-version_number").first()

    def runnable_version(self, *, test: bool):
        """Version a utiliser pour demarrer une tentative."""
        if test:
            return (
                self.versions.filter(status = c.STATUS_TEST).order_by("-version_number").first()
                or self.current_version
                or self.latest_version()
            )
        if self.current_version and self.current_version.status == c.STATUS_PUBLISHED:
            return self.current_version
        return self.versions.filter(status = c.STATUS_PUBLISHED).order_by("-version_number").first()


class QuestionnaireVersion(models.Model):
    """Contenu immuable d'un questionnaire a un instant donne.

    Une version quitte l'etat DRAFT des qu'elle est mise en test ou publiee ;
    elle n'est alors plus jamais modifiable. Modifier revient toujours a creer
    une nouvelle version a partir de celle-ci.
    """

    questionnaire  = models.ForeignKey(
        Questionnaire, on_delete = models.CASCADE, related_name = "versions"
    )
    version_number = models.PositiveIntegerField()
    status         = models.CharField(
        max_length = 12, choices = c.VERSION_STATUSES, default = c.STATUS_DRAFT
    )

    title       = models.CharField(max_length = 255)
    description = models.TextField(blank = True, default = "")

    scoring_config = models.JSONField(default = dict, blank = True)

    valid_from  = models.DateTimeField(null = True, blank = True)
    valid_until = models.DateTimeField(null = True, blank = True)

    created_at = models.DateTimeField(auto_now_add = True)
    created_by = models.ForeignKey(
        User, on_delete = models.SET_NULL, null = True, blank = True,
        related_name = "created_questionnaire_versions"
    )
    derived_from = models.ForeignKey(
        "self", on_delete = models.SET_NULL, null = True, blank = True,
        related_name = "derivatives"
    )

    published_at   = models.DateTimeField(null = True, blank = True)
    published_by   = models.ForeignKey(
        User, on_delete = models.SET_NULL, null = True, blank = True,
        related_name = "published_questionnaire_versions"
    )
    invalidated_at = models.DateTimeField(null = True, blank = True)
    invalidated_by = models.ForeignKey(
        User, on_delete = models.SET_NULL, null = True, blank = True,
        related_name = "invalidated_questionnaire_versions"
    )
    invalidation_reason = models.TextField(blank = True, default = "")

    class Meta:
        ordering    = ("questionnaire", "-version_number")
        constraints = (
            models.UniqueConstraint(
                fields = ("questionnaire", "version_number"),
                name   = "unique_version_number_per_questionnaire",
            ),
        )
        indexes = (models.Index(fields = ["status"]),)

    def __str__(self):
        return f"{self.questionnaire_id}#v{self.version_number}"

    def save(self, *args, **kwargs):
        if not self.scoring_config:
            self.scoring_config = dict(c.DEFAULT_VERSION_SCORING)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------ #

    @property
    def is_editable(self) -> bool:
        """Une version n'est modifiable qu'en brouillon et sans tentative."""
        if self.status != c.STATUS_DRAFT:
            return False
        return not self.attempts.exists()

    @property
    def accepts_answers(self) -> bool:
        """Peut-on demarrer une tentative sur cette version ?"""
        return self.status not in c.CLOSED_VERSION_STATUSES

    @property
    def allows_continuation(self) -> bool:
        """Une tentative deja ouverte peut-elle encore etre completee ?

        Une version archivee l'a generalement ete parce qu'une version plus
        recente a ete publiee : ceux qui etaient en train de repondre doivent
        pouvoir terminer. Seules une desactivation ou une invalidation, qui sont
        des decisions deliberees, ferment la porte.
        """
        return self.status not in (c.STATUS_DISABLED, c.STATUS_INVALIDATED)

    @property
    def scoring(self) -> dict:
        return {**c.DEFAULT_VERSION_SCORING, **(self.scoring_config or {})}

    def is_valid_now(self, now = None) -> bool:
        now = now or timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    def assert_editable(self):
        if not self.is_editable:
            raise ValidationError(
                f"la version {self.version_number} n'est plus modifiable "
                f"(statut {self.status}); creez une nouvelle version"
            )


class Question(models.Model):
    """Question appartenant a une version.

    `stable_key` est l'identite fonctionnelle de la question : elle est
    reconduite lors de la creation d'une nouvelle version, ce qui permet de
    comparer deux versions et de referencer une question dans une condition
    sans dependre de la position ni de la cle primaire.
    """

    version    = models.ForeignKey(
        QuestionnaireVersion, on_delete = models.CASCADE, related_name = "questions"
    )
    stable_key = models.CharField(max_length = 32, default = new_stable_key, editable = False)

    order       = models.PositiveIntegerField(default = 0)
    text        = models.TextField()
    description = models.TextField(blank = True, default = "")
    explanation = models.TextField(
        blank = True, default = "",
        help_text = "affichee dans les resultats si la visibilite l'autorise"
    )

    type     = models.CharField(max_length = 32, choices = type_choices)
    required = models.BooleanField(default = True)

    config          = models.JSONField(default = dict, blank = True)
    expected_config = models.JSONField(default = dict, blank = True)
    scoring_config  = models.JSONField(default = dict, blank = True)
    condition       = models.JSONField(null = True, blank = True)

    class Meta:
        ordering    = ("order", "id")
        constraints = (
            models.UniqueConstraint(
                fields = ("version", "stable_key"), name = "unique_question_key_per_version"
            ),
        )
        indexes = (models.Index(fields = ["stable_key"]),)

    def __str__(self):
        return f"Q{self.pk}<{self.type}>"

    @property
    def handler(self):
        return get_type(self.type)

    @property
    def scoring(self) -> dict:
        return {**c.DEFAULT_QUESTION_SCORING, **(self.scoring_config or {})}

    @property
    def is_graded(self) -> bool:
        return self.handler.has_expected(self)

    def max_score(self):
        from decimal import Decimal

        scoring = self.scoring
        return Decimal(str(scoring["weight"])) * Decimal(str(scoring["correct_score"]))


class QuestionOption(models.Model):
    """Reponse proposee, identifiee de facon stable.

    Le texte peut evoluer d'une version a l'autre sans casser l'historique :
    les reponses utilisateur referencent l'identifiant, jamais le libelle.
    """

    question   = models.ForeignKey(Question, on_delete = models.CASCADE, related_name = "options")
    stable_key = models.CharField(max_length = 32, default = new_stable_key, editable = False)

    order       = models.PositiveIntegerField(default = 0)
    text        = models.CharField(max_length = 500)
    description = models.CharField(max_length = 500, blank = True, default = "")
    value       = models.CharField(
        max_length = 100, blank = True, default = "",
        help_text = "valeur portee par l'option (echelle, notation...)"
    )

    is_correct = models.BooleanField(default = False)
    score      = models.DecimalField(
        max_digits = 8, decimal_places = 3, null = True, blank = True,
        help_text = "score specifique a cette option (optionnel)"
    )

    class Meta:
        ordering    = ("order", "id")
        constraints = (
            models.UniqueConstraint(
                fields = ("question", "stable_key"), name = "unique_option_key_per_question"
            ),
        )

    def __str__(self):
        return f"O{self.pk}<{self.text}>"


class QuestionnaireAccessRule(models.Model):
    """Regle d'acces ou de visibilite, en forme normale disjonctive.

    Les regles d'un meme `group_index` sont combinees par AND, et les groupes
    entre eux par OR. Cela couvre toute combinaison AND/OR tout en restant
    interrogeable en base (contrairement a un arbre JSON).

        groupe 0 : ROLE=PREMIUM AND BADGE=BASIC_COMPLETED
        groupe 1 : ROLE=ADMIN
        => (PREMIUM ET BASIC_COMPLETED) OU ADMIN
    """

    questionnaire = models.ForeignKey(
        Questionnaire, on_delete = models.CASCADE, related_name = "access_rules"
    )
    kind        = models.CharField(max_length = 12, choices = c.RULE_KINDS, default = c.RULE_KIND_ACCESS)
    group_index = models.PositiveIntegerField(default = 0)
    rule_type   = models.CharField(max_length = 12, choices = c.RULE_TYPES)
    negate      = models.BooleanField(default = False)

    target_user = models.ForeignKey(
        User, on_delete = models.CASCADE, null = True, blank = True,
        related_name = "questionnaire_access_rules"
    )
    role        = models.CharField(max_length = 32, blank = True, default = "")
    badge       = models.ForeignKey(
        "questionnaires.Badge", on_delete = models.CASCADE, null = True, blank = True,
        related_name = "access_rules"
    )

    created_at = models.DateTimeField(auto_now_add = True)

    class Meta:
        ordering = ("kind", "group_index", "id")
        indexes  = (models.Index(fields = ["questionnaire", "kind", "group_index"]),)

    def __str__(self):
        return f"{self.kind}[{self.group_index}] {'NOT ' if self.negate else ''}{self.rule_type}"

    def clean(self):
        if self.rule_type == c.RULE_USER and not self.target_user_id:
            raise ValidationError("une regle USER exige un utilisateur")
        if self.rule_type == c.RULE_ROLE and not self.role:
            raise ValidationError("une regle ROLE exige un role")
        if self.rule_type == c.RULE_BADGE and not self.badge_id:
            raise ValidationError("une regle BADGE exige un badge")

    def describe(self) -> str:
        prefix = "NON " if self.negate else ""
        if self.rule_type == c.RULE_EVERYONE:
            return f"{prefix}tout le monde"
        if self.rule_type == c.RULE_USER:
            return f"{prefix}utilisateur = {self.target_user}"
        if self.rule_type == c.RULE_ROLE:
            return f"{prefix}role = {self.role}"
        return f"{prefix}badge = {self.badge.code if self.badge else '?'}"
