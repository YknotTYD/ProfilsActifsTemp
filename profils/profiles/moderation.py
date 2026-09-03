##moderation.py
"""Machine a etats de la moderation video.

Point d'entree unique pour tout changement de statut d'une `ProfileVideo` :
une transition absente de `constants.VIDEO_TRANSITIONS` est refusee plutot
qu'executee sur la foi de l'appelant, et chaque changement ecrit son
`VideoModerationEvent` dans la meme transaction que la mise a jour -- ce que
demande la section "Historique de moderation" ("conserver pour chaque video
l'historique des actions... administrateur, date, ancien et nouveau statut,
raison").

Separation volontaire avec `permissions.py` : ce module ne decide jamais lui
meme si l'utilisateur courant a le droit d'agir sur cette video-la (c'est le
travail de `permissions.assert_owns_child` / `permissions.has_perm`, appele
par la vue avant d'arriver ici) ; il verifie seulement que le *type* d'acteur
annonce (`ACTOR_OWNER`, `ACTOR_ADMIN`, `ACTOR_SYSTEM`) a le droit de faire
*cette* transition-la. `user` sert uniquement a l'attribution dans
l'historique -- il peut manquer (`None`) pour un traitement automatique, ou
pour un appel interne qui ne feint pas d'avoir une identite (scripts, tests).
"""

from django.db    import transaction
from django.utils import timezone

from . import constants as c
from .http import BadRequest
from .models.video import ProfileVideo, VideoModerationEvent
from .permissions import ProfileAccessDenied


class ForbiddenTransition(ProfileAccessDenied):
    """La transition existe, mais pas pour ce type d'acteur -- un refus
    d'acces (403), pas une requete malformee : c'est exactement la meme
    famille d'erreur que `permissions.assert_can_edit`.
    """

    def __init__(self, from_status: str, to_status: str, actor: str):
        super().__init__(
            f"'{actor}' ne peut pas faire passer une video de '{from_status}' a '{to_status}'",
            "forbidden_transition", 403,
        )


class InvalidTransition(BadRequest):
    """La transition n'existe pas du tout, quel que soit l'acteur."""

    def __init__(self, from_status: str, to_status: str):
        super().__init__(
            f"transition '{from_status}' -> '{to_status}' impossible", "invalid_transition",
        )


@transaction.atomic
def transition_video(video: ProfileVideo, to_status: str, *, actor: str,
                     user = None, reason: str = "") -> ProfileVideo:
    """Fait passer `video` a `to_status` et historise le changement.

    `actor` est le type d'acteur qui declenche l'appel (`constants.
    ACTOR_OWNER` / `ACTOR_ADMIN` / `ACTOR_SYSTEM`) -- deja etabli par
    l'appelant, pas redecouvert ici. `user` est qui, precisement, si on le
    sait ; `reason` est obligatoire pour les statuts de `constants.
    REASON_REQUIRED_STATUSES` (aujourd'hui, seulement `REJECTED`).
    """
    from_status = video.status

    if to_status == c.VIDEO_DELETED:
        allowed = c.DELETE_ACTORS
        if actor not in allowed:
            raise ForbiddenTransition(from_status, to_status, actor)
    else:
        allowed = c.VIDEO_TRANSITIONS.get((from_status, to_status))
        if allowed is None:
            raise InvalidTransition(from_status, to_status)
        if actor not in allowed:
            raise ForbiddenTransition(from_status, to_status, actor)

    reason = (reason or "").strip()
    if to_status in c.REASON_REQUIRED_STATUSES and not reason:
        raise BadRequest("un motif est obligatoire pour ce statut", "reason_required")

    video.status = to_status
    if to_status == c.VIDEO_REJECTED:
        video.rejection_reason = reason
    elif to_status != c.VIDEO_DELETED:
        # un motif de refus ne doit pas survivre a la sortie de l'etat refuse
        video.rejection_reason = ""

    if actor == c.ACTOR_ADMIN and to_status in (c.VIDEO_APPROVED, c.VIDEO_REJECTED):
        video.moderated_at = timezone.now()
        video.moderated_by = user

    video.save()

    VideoModerationEvent.objects.create(
        video      = video,
        actor      = user,
        source     = actor,
        old_status = from_status,
        new_status = to_status,
        reason     = reason,
    )
    return video
