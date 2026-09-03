##api.py
"""API du centre de notifications.

Couche de transport uniquement, dans le meme esprit que `profiles/api.py` :
`services.py` fait le travail, `api.py` traduit en JSON. Les primitives
(`api`, `ok`, `fail`) viennent de `questionnaires/http.py`, comme le fait
deja `profiles/http.py`, pour ne pas repeter un troisieme format d'erreur.
"""

from profils.questionnaires.http import api, fail, ok

from . import serializers, services
from .models import Notification


@api(("GET",))
def list_notifications(request):
    rows = (
        Notification.objects.filter(recipient = request.user)
            .select_related("target_content_type")[:50]
    )
    return ok({
        "notifications": [serializers.notification(n) for n in rows],
        "unread_count":  services.unread_count(request.user),
    })


@api(("GET",))
def unread_count(request):
    return ok({"count": services.unread_count(request.user)})


@api(("POST",))
def mark_read(request, pk):
    notification = Notification.objects.filter(pk = pk, recipient = request.user).first()
    if notification is None:
        return fail("notification introuvable", "not_found", 404)
    services.mark_read(notification)
    return ok()


@api(("POST",))
def mark_all_read(request):
    services.mark_all_read(request.user)
    return ok()
