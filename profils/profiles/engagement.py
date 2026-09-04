"""Vues et reactions du feed video (`ProfileVideo`).

Le feed est desormais servi par `ProfileVideo` (une seule pile video, moderee).
Ce module porte les deux ecritures que le feed declenche cote spectateur :

  * `register_view` : enregistre qu'un spectateur a vu une video, une seule
    fois par (spectateur, video), et tient a jour `ProfileVideo.view_count` ;
  * `set_reaction` : pose / retire / remplace le like-dislike d'un
    utilisateur, tient a jour `ProfileVideo.like_count`, et notifie le
    proprietaire d'une nouvelle reaction (section 5).

Aucune de ces ecritures ne touche au statut de moderation : une video doit
deja etre visible du spectateur (verifie par l'appelant via
`visibility.can_view_video`) pour arriver ici.
"""

from django.db import IntegrityError, transaction
from django.db.models import F

from profils.notifications import services as notifications
from profils.notifications import types as notification_types

from .models import ProfileVideo, ProfileVideoReaction, ProfileVideoView

_LIKE    = ProfileVideoReaction.LIKE
_DISLIKE = ProfileVideoReaction.DISLIKE

_NOTIFICATION_FOR_REACTION = {
    _LIKE:    notification_types.VIDEO_LIKED,
    _DISLIKE: notification_types.VIDEO_DISLIKED,
}

def _recount_likes(video: ProfileVideo) -> int:
    likes = video.reactions.filter(reaction = _LIKE).count()
    ProfileVideo.objects.filter(pk = video.pk).update(like_count = likes)
    return likes

@transaction.atomic
def register_view(video: ProfileVideo, *, user = None, session_key: str = "") -> bool:
    """Enregistre une vue. Renvoie True si c'est une vue nouvelle.

    Idempotent : le meme spectateur peut recharger la page sans regonfler le
    compteur. Un visiteur anonyme sans session identifiable est compte mais
    non dedoublonne -- le cout d'une session forcee pour un simple compteur de
    feed ne le vaut pas.
    """
    authed = user is not None and getattr(user, "is_authenticated", False)
    lookup = {"video": video}
    if authed:
        lookup["user"] = user
    elif session_key:
        lookup["user"] = None
        lookup["session_key"] = session_key
    else:
        ProfileVideoView.objects.create(video = video)
        ProfileVideo.objects.filter(pk = video.pk).update(view_count = F("view_count") + 1)
        return True

    try:
        with transaction.atomic():
            _, created = ProfileVideoView.objects.get_or_create(**lookup)
    except IntegrityError:
        created = False
    if created:
        ProfileVideo.objects.filter(pk = video.pk).update(view_count = F("view_count") + 1)
    return created

@transaction.atomic
def set_reaction(video: ProfileVideo, user, reaction: str) -> dict:
    """Pose, retire ou remplace la reaction de `user` sur `video`.

    Regle identique a l'ancien feed (`mainapp.react`) : re-cliquer le meme
    bouton retire la reaction, cliquer l'autre la remplace. Notifie le
    proprietaire uniquement pour une reaction *nouvelle* (jamais un retrait,
    jamais sa propre video).
    """
    if reaction not in (_LIKE, _DISLIKE):
        raise ValueError(f"reaction inconnue: {reaction!r}")

    existing = video.reactions.filter(user = user).first()
    removed  = False
    is_new   = False

    if existing is None:
        ProfileVideoReaction.objects.create(video = video, user = user, reaction = reaction)
        is_new = True
    elif existing.reaction == reaction:
        existing.delete()
        removed = True
    else:
        existing.reaction = reaction
        existing.save(update_fields = ["reaction"])
        is_new = True

    likes = _recount_likes(video)

    if is_new and video.profile.user_id != user.id:
        notifications.notify(
            video.profile.user, _NOTIFICATION_FOR_REACTION[reaction], target = video,
            url = "/profiles/me/video/", title = video.title,
        )

    return {
        "reaction": None if removed else reaction,
        "likes":    likes,
        "dislikes": video.reactions.filter(reaction = _DISLIKE).count(),
    }
