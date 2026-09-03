##services.py
"""Ecritures et lectures de notifications.

Point d'entree unique pour en creer une : `notify()`. Les autres apps
(profiles, messaging demain) l'appellent sans jamais toucher directement au
modele -- c'est ce qui permet d'ajouter un canal (email, push) plus tard
dans cette seule fonction, sans modifier ses appelants (spec section 8,
"notifications email / push").
"""

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from . import types
from .models import Notification


def notify(recipient, type_code: str, *, target = None, url: str = "", **payload) -> Notification:
    """Cree une notification pour `recipient`.

    `recipient is None` ou identique a l'auteur de l'evenement (on ne se
    notifie pas soi-meme) est un no-op silencieux -- l'appelant n'a pas a
    verifier ce cas a chaque site d'appel.
    """
    if recipient is None or not getattr(recipient, "is_authenticated", True):
        return None
    if not types.is_known(type_code):
        raise ValueError(f"type de notification inconnu : {type_code!r}")

    kwargs = dict(recipient = recipient, type = type_code, payload = payload, url = url)
    if target is not None:
        kwargs["target_content_type"] = ContentType.objects.get_for_model(target)
        kwargs["target_id"] = target.pk

    return Notification.objects.create(**kwargs)


def unread_count(user) -> int:
    if not user or not user.is_authenticated:
        return 0
    return Notification.objects.filter(recipient = user, read_at__isnull = True).count()


def mark_read(notification: Notification):
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields = ["read_at"])


def mark_all_read(user):
    Notification.objects.filter(recipient = user, read_at__isnull = True).update(
        read_at = timezone.now(),
    )
