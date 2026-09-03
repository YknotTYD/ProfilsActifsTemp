##rules.py
"""Regles d'ouverture d'une conversation (spec section 4).

"Prevoir une architecture extensible pour ajouter d'autres regles de
messagerie plus tard" : chaque regle est une fonction independante
`(sender, recipient) -> bool`, enregistree par decoration. `can_start`
autorise des qu'une regle le permet. Ajouter une regle plus tard --
"un recruteur peut aussi contacter un candidat qui a postule a son
offre", par exemple -- n'oblige a toucher ni celle-ci ni ses appelants.

Repondre dans une conversation deja ouverte n'est pas gouverne par ces
regles : c'est une question de participation (`Conversation.
has_participant`), pas d'ouverture, et les deux participants y ont
toujours droit une fois la conversation en cours.
"""

from profils.profiles import constants as pc
from profils.profiles.models import ProfileVideo
from profils.profiles.permissions import is_recruiter

_RULES = []


def rule(fn):
    _RULES.append(fn)
    return fn


def _has_a_published_video(user) -> bool:
    return ProfileVideo.objects.filter(
        profile__user = user, status = pc.VIDEO_PUBLISHED,
    ).exists()


@rule
def recruiter_to_candidate_with_video(sender, recipient) -> bool:
    """Seule regle active aujourd'hui : "un recruteur peut contacter un
    demandeur d'emploi ayant publie une video" (section 4). "Les autres
    types d'utilisateurs ne peuvent pas initier ce type de contact" est
    tenu simplement en n'ecrivant aucune autre regle.
    """
    return (
        sender.is_authenticated and is_recruiter(sender)
        and sender.id != recipient.id
        and _has_a_published_video(recipient)
    )


def can_start(sender, recipient) -> bool:
    if not sender or not sender.is_authenticated or recipient is None:
        return False
    return any(matches(sender, recipient) for matches in _RULES)
