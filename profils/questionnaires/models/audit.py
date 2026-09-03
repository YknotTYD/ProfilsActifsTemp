##models/audit.py

from django.contrib.auth.models import User
from django.db                   import models

from .. import constants as c


class AuditLog(models.Model):
    """Journal des actions importantes.

    Volontairement sans `contenttypes` : un couple (object_type, object_id)
    textuel suffit, se lit facilement et ne cree pas de dependance de suppression.
    """

    actor  = models.ForeignKey(
        User, on_delete = models.SET_NULL, null = True, blank = True,
        related_name = "questionnaire_audit_entries"
    )
    action = models.CharField(max_length = 24, choices = c.AUDIT_ACTIONS)

    object_type = models.CharField(max_length = 40)
    object_id   = models.CharField(max_length = 40)

    questionnaire = models.ForeignKey(
        "questionnaires.Questionnaire", on_delete = models.SET_NULL,
        null = True, blank = True, related_name = "audit_entries"
    )

    old_value = models.JSONField(null = True, blank = True)
    new_value = models.JSONField(null = True, blank = True)
    metadata  = models.JSONField(default = dict, blank = True)

    created_at = models.DateTimeField(auto_now_add = True)

    class Meta:
        ordering = ("-created_at",)
        indexes  = (
            models.Index(fields = ["questionnaire", "-created_at"]),
            models.Index(fields = ["object_type", "object_id"]),
            models.Index(fields = ["action"]),
        )

    def __str__(self):
        return f"Audit<{self.action} {self.object_type}#{self.object_id}>"
