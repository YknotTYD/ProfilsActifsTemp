"""Conversation et message (spec section 4).

`context` est generique (content_type + object_id) : d'ou est partie la
conversation (une video, un profil...) sans colonne dediee par source
possible. Une seule conversation par paire d'utilisateurs -- `services.
start_conversation` retrouve l'existante plutot que d'en recreer une a
chaque nouveau bouton "Contacter" clique.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

class Conversation(models.Model):

    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete = models.CASCADE, related_name = "conversations_started",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete = models.CASCADE, related_name = "conversations_received",
    )

    context_content_type = models.ForeignKey(
        ContentType, null = True, blank = True, on_delete = models.SET_NULL,
    )
    context_id = models.PositiveIntegerField(null = True, blank = True)
    context = GenericForeignKey("context_content_type", "context_id")

    created_at = models.DateTimeField(auto_now_add = True)

    class Meta:
        ordering = ("-created_at",)
        constraints = (
            models.UniqueConstraint(
                fields = ("initiator", "recipient"), name = "unique_conversation_pair",
            ),
        )

    def __str__(self):
        return f"Conversation<{self.initiator_id}<->{self.recipient_id}>"

    def other_participant(self, user):
        return self.recipient if user.id == self.initiator_id else self.initiator

    def has_participant(self, user) -> bool:
        return bool(user and user.is_authenticated
                    and user.id in (self.initiator_id, self.recipient_id))

    @property
    def last_message(self):
        return self.messages.order_by("-created_at").first()

class Message(models.Model):

    conversation = models.ForeignKey(Conversation, on_delete = models.CASCADE, related_name = "messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete = models.CASCADE, related_name = "+")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add = True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"Message<{self.conversation_id}:{self.sender_id}>"
