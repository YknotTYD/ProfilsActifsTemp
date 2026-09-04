"""Ecritures metier de la messagerie. Les vues ne font que traduire en HTTP."""

from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction

from profils.notifications import services as notifications
from profils.notifications import types as notification_types

from . import rules
from .http import BadRequest, MessagingAccessDenied
from .models import Conversation, Message

def get_conversation_between(a, b) -> Conversation | None:
    return Conversation.objects.filter(
        models.Q(initiator = a, recipient = b) | models.Q(initiator = b, recipient = a),
    ).first()

def conversations_for(user):
    return Conversation.objects.filter(
        models.Q(initiator = user) | models.Q(recipient = user),
    ).select_related("initiator", "recipient")

@transaction.atomic
def start_conversation(sender, recipient, *, context = None) -> Conversation:
    """Demarre une conversation, ou retrouve celle qui existe deja entre
    les deux memes utilisateurs -- cliquer "Contacter" une deuxieme fois
    ne doit pas ouvrir un deuxieme fil (section 4).
    """
    if sender.id == recipient.id:
        raise BadRequest("impossible de s'envoyer un message a soi-meme", "self_conversation")

    existing = get_conversation_between(sender, recipient)
    if existing is not None:
        return existing

    if not rules.can_start(sender, recipient):
        raise MessagingAccessDenied(
            "vous ne pouvez pas contacter cet utilisateur", "forbidden_contact", 403,
        )

    conversation = Conversation(initiator = sender, recipient = recipient)
    if context is not None:
        conversation.context_content_type = ContentType.objects.get_for_model(context)
        conversation.context_id = context.pk
    conversation.save()
    return conversation

def send_message(conversation: Conversation, sender, body: str) -> Message:
    if not conversation.has_participant(sender):
        raise MessagingAccessDenied(
            "vous ne participez pas a cette conversation", "not_participant", 403,
        )
    body = (body or "").strip()
    if not body:
        raise BadRequest("le message ne peut pas etre vide", "empty_message")

    message = Message.objects.create(conversation = conversation, sender = sender, body = body[:4000])

    other = conversation.other_participant(sender)
    notifications.notify(
        other, notification_types.NEW_MESSAGE, target = conversation,
        url = f"/messages/{conversation.pk}/",
        sender = sender.username, preview = message.body[:120],
    )
    return message
