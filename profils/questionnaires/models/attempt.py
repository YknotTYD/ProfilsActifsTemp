
from django.contrib.auth.models import User
from django.db                   import models
from django.utils                import timezone

from .. import constants as c
from .questionnaire import Question, QuestionOption, Questionnaire, QuestionnaireVersion

class QuestionnaireAttempt(models.Model):
    """Passage d'un questionnaire par un utilisateur.

    Une tentative est liee a la version exacte utilisee au demarrage : une
    modification ulterieure du questionnaire ne peut donc jamais alterer
    retroactivement ce que l'utilisateur avait devant lui ni son resultat.
    """

    user          = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "questionnaire_attempts")
    questionnaire = models.ForeignKey(Questionnaire, on_delete = models.CASCADE, related_name = "attempts")
    version       = models.ForeignKey(QuestionnaireVersion, on_delete = models.PROTECT, related_name = "attempts")

    status  = models.CharField(max_length = 12, choices = c.ATTEMPT_STATUSES, default = c.ATTEMPT_IN_PROGRESS)
    is_test = models.BooleanField(
        default = False,
        help_text = "tentative de mode TEST : exclue des statistiques et des badges reels"
    )
    attempt_number = models.PositiveIntegerField(default = 1)

    started_at       = models.DateTimeField(auto_now_add = True)
    last_activity_at = models.DateTimeField(auto_now = True)
    completed_at     = models.DateTimeField(null = True, blank = True)
    expires_at       = models.DateTimeField(null = True, blank = True)

    answered_count  = models.PositiveIntegerField(default = 0)
    visible_count   = models.PositiveIntegerField(default = 0)
    progress_percent = models.DecimalField(max_digits = 5, decimal_places = 2, default = 0)
    current_question = models.ForeignKey(
        Question, on_delete = models.SET_NULL, null = True, blank = True, related_name = "+"
    )

    score      = models.DecimalField(max_digits = 10, decimal_places = 3, null = True, blank = True)
    max_score  = models.DecimalField(max_digits = 10, decimal_places = 3, null = True, blank = True)
    percentage = models.DecimalField(max_digits = 6, decimal_places = 2, null = True, blank = True)
    passed     = models.BooleanField(null = True, blank = True)

    carried_from = models.ForeignKey(
        "self", on_delete = models.SET_NULL, null = True, blank = True,
        related_name = "carried_to"
    )

    revision = models.PositiveIntegerField(default = 0)
    metadata = models.JSONField(default = dict, blank = True)

    class Meta:
        ordering    = ("-started_at",)
        constraints = (
            models.UniqueConstraint(
                fields    = ("user", "questionnaire", "is_test"),
                condition = models.Q(status = c.ATTEMPT_IN_PROGRESS),
                name      = "one_attempt_in_progress_per_user_questionnaire",
            ),
        )
        indexes = (
            models.Index(fields = ["user", "questionnaire", "status"]),
            models.Index(fields = ["questionnaire", "is_test", "status"]),
            models.Index(fields = ["version", "status"]),
        )

    def __str__(self):
        return f"Attempt<{self.pk} u{self.user_id} q{self.questionnaire_id} v{self.version_id}>"

    @property
    def is_open(self) -> bool:
        return self.status == c.ATTEMPT_IN_PROGRESS

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() > self.expires_at)

    def touch(self, **fields):
        """Ecriture atomique + increment de revision."""
        self.revision += 1
        fields.setdefault("update_fields", None)
        update_fields = fields.pop("update_fields")
        if update_fields is not None:
            update_fields = list(update_fields) + ["revision", "last_activity_at"]
        self.save(update_fields = update_fields)

class UserAnswer(models.Model):
    """Reponse d'un utilisateur a une question, dans une tentative donnee.

    `value` contient la valeur canonique produite par le handler de type, et
    `snapshot` conserve ce que l'utilisateur avait sous les yeux (enonce, options,
    configuration) pour pouvoir rejouer la tentative meme des annees plus tard.
    """

    attempt  = models.ForeignKey(QuestionnaireAttempt, on_delete = models.CASCADE, related_name = "answers")
    question = models.ForeignKey(Question, on_delete = models.PROTECT, related_name = "answers")
    question_stable_key = models.CharField(max_length = 32, db_index = True)

    value    = models.JSONField(null = True, blank = True)
    snapshot = models.JSONField(default = dict, blank = True)

    is_correct    = models.BooleanField(null = True, blank = True)
    score         = models.DecimalField(max_digits = 8, decimal_places = 3, null = True, blank = True)
    score_details = models.JSONField(default = dict, blank = True)

    locked      = models.BooleanField(default = False)
    carried     = models.BooleanField(default = False)
    answered_at = models.DateTimeField(auto_now_add = True)
    updated_at  = models.DateTimeField(auto_now = True)

    revision        = models.PositiveIntegerField(default = 1)
    client_sequence = models.BigIntegerField(default = 0)
    idempotency_key = models.CharField(max_length = 64, blank = True, default = "")

    class Meta:
        ordering    = ("question__order", "id")
        constraints = (
            models.UniqueConstraint(
                fields = ("attempt", "question"), name = "one_answer_per_question_per_attempt"
            ),
        )
        indexes = (
            models.Index(fields = ["attempt", "question"]),
            models.Index(fields = ["question_stable_key"]),
            models.Index(fields = ["idempotency_key"]),
        )

    def __str__(self):
        return f"Answer<a{self.attempt_id} q{self.question_id}>"

class UserAnswerSelection(models.Model):
    """Option retenue par une reponse.

    Redondant avec `UserAnswer.value` a dessein : cette table rend possibles
    les statistiques par option (reponses les plus frequentes, questions les
    plus echouees) sans avoir a lire du JSON.
    """

    answer = models.ForeignKey(UserAnswer, on_delete = models.CASCADE, related_name = "selections")
    option = models.ForeignKey(QuestionOption, on_delete = models.PROTECT, related_name = "selections")
    option_stable_key = models.CharField(max_length = 32, db_index = True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields = ("answer", "option"), name = "unique_selection_per_answer"),
        )
        indexes = (models.Index(fields = ["option"]),)

    def __str__(self):
        return f"Selection<a{self.answer_id} o{self.option_id}>"

class QuestionnaireResult(models.Model):
    """Resultat fige d'une tentative terminee.

    Une ligne par tentative terminee, jamais ecrasee : l'historique des scores
    d'un utilisateur est conserve integralement.
    """

    attempt       = models.OneToOneField(QuestionnaireAttempt, on_delete = models.CASCADE, related_name = "result")
    user          = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "questionnaire_results")
    questionnaire = models.ForeignKey(Questionnaire, on_delete = models.CASCADE, related_name = "results")
    version       = models.ForeignKey(QuestionnaireVersion, on_delete = models.PROTECT, related_name = "results")

    score      = models.DecimalField(max_digits = 10, decimal_places = 3)
    max_score  = models.DecimalField(max_digits = 10, decimal_places = 3)
    percentage = models.DecimalField(max_digits = 6, decimal_places = 2)
    passed     = models.BooleanField()
    level      = models.CharField(max_length = 64, blank = True, default = "")

    is_test     = models.BooleanField(default = False)
    computed_at = models.DateTimeField(auto_now_add = True)
    duration_seconds = models.PositiveIntegerField(null = True, blank = True)

    details = models.JSONField(default = dict, blank = True)

    class Meta:
        ordering = ("-computed_at",)
        indexes  = (
            models.Index(fields = ["user", "questionnaire"]),
            models.Index(fields = ["questionnaire", "is_test"]),
            models.Index(fields = ["version"]),
        )

    def __str__(self):
        return f"Result<u{self.user_id} q{self.questionnaire_id} {self.percentage}%>"
