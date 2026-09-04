"""Modele de notification (spec section 5).

Une seule table sert tous les types : la cible est generique
(`content_type` + `object_id`) plutot qu'une colonne par type de source
possible ("video_id", "message_id", "profile_id"...), qui grossirait a
chaque nouveau type de notification. `type` est un `CharField` libre,
verifie contre `types.py` a l'ecriture (`services.notify`) -- jamais par un
`choices=` fige dans une migration.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

class Notification(models.Model):

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete = models.CASCADE, related_name = "notifications",
    )
    type = models.CharField(max_length = 32)

    target_content_type = models.ForeignKey(
        ContentType, null = True, blank = True, on_delete = models.CASCADE,
    )
    target_id = models.PositiveIntegerField(null = True, blank = True)
    target = GenericForeignKey("target_content_type", "target_id")

    payload = models.JSONField(default = dict, blank = True)
    url = models.CharField(max_length = 1024, blank = True, default = "")

    read_at = models.DateTimeField(null = True, blank = True)
    created_at = models.DateTimeField(auto_now_add = True)

    class Meta:
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields = ["recipient", "read_at", "-created_at"]),
        )

    def __str__(self):
        return f"Notification<{self.recipient_id}:{self.type}>"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
