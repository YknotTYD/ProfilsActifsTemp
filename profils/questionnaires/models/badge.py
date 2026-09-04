
from django.contrib.auth.models import User
from django.db                   import models

from .. import constants as c

class Badge(models.Model):
    """Badge attribuable.

    Le modele et l'API sont en place ; l'attribution automatique et l'affichage
    seront branches plus tard (section 21). `criteria` decrit la condition
    d'obtention sous une forme deja exploitable :

        {"type": "questionnaire_passed", "questionnaire": 12}
        {"type": "min_percentage", "questionnaire": 12, "percentage": 80}
        {"type": "questionnaires_passed", "questionnaires": [1, 2, 3]}
        {"type": "attempts_count", "questionnaire": 12, "count": 5}
        {"type": "custom", "handler": "mon_module.ma_regle"}
    """

    code        = models.SlugField(max_length = 64, unique = True)
    name        = models.CharField(max_length = 120)
    description = models.TextField(blank = True, default = "")
    icon        = models.CharField(max_length = 64, blank = True, default = "")

    criteria   = models.JSONField(default = dict, blank = True)
    max_level  = models.PositiveIntegerField(default = 1)
    active     = models.BooleanField(default = True)
    created_at = models.DateTimeField(auto_now_add = True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return f"Badge<{self.code}>"

class UserBadge(models.Model):
    """Badge detenu par un utilisateur.

    Un badge obtenu en mode TEST n'est jamais cree : `is_test` existe pour
    d'eventuelles simulations d'administration, mais l'attribution reelle
    ignore les tentatives de test.
    """

    user  = models.ForeignKey(User, on_delete = models.CASCADE, related_name = "badges")
    badge = models.ForeignKey(Badge, on_delete = models.CASCADE, related_name = "holders")

    level      = models.PositiveIntegerField(default = 1)
    awarded_at = models.DateTimeField(auto_now_add = True)
    source     = models.CharField(max_length = 24, choices = c.BADGE_SOURCES, default = c.BADGE_SOURCE_SYSTEM)
    source_result = models.ForeignKey(
        "questionnaires.QuestionnaireResult", on_delete = models.SET_NULL,
        null = True, blank = True, related_name = "awarded_badges"
    )
    is_test  = models.BooleanField(default = False)
    metadata = models.JSONField(default = dict, blank = True)

    class Meta:
        ordering    = ("-awarded_at",)
        constraints = (
            models.UniqueConstraint(fields = ("user", "badge"), name = "unique_badge_per_user"),
        )
        indexes = (models.Index(fields = ["user", "badge"]),)

    def __str__(self):
        return f"UserBadge<u{self.user_id} {self.badge_id}>"
