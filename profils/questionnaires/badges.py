##badges.py
"""Attribution des badges.

Le modele, les relations et l'API sont en place (section 21). L'interface
n'affiche rien pour l'instant : `award_for_result` est appele a la fin de
chaque tentative reelle et sait deja evaluer les criteres declaratifs les plus
courants. Les tentatives de mode TEST n'attribuent jamais de badge reel.

Ajouter un nouveau critere = ajouter une fonction decoree `@criterion("...")`.
"""

from . import constants as c
from .auditing import log
from .models   import Badge, QuestionnaireResult, UserBadge

_CRITERIA: dict[str, callable] = {}


def criterion(name: str):
    def decorator(func):
        _CRITERIA[name] = func
        return func

    return decorator


@criterion("questionnaire_passed")
def _passed(badge, user, result) -> bool:
    target = badge.criteria.get("questionnaire")
    if target is not None and int(target) != result.questionnaire_id:
        return False
    return result.passed


@criterion("min_percentage")
def _min_percentage(badge, user, result) -> bool:
    target = badge.criteria.get("questionnaire")
    if target is not None and int(target) != result.questionnaire_id:
        return False
    return float(result.percentage) >= float(badge.criteria.get("percentage", 100))


@criterion("questionnaires_passed")
def _all_passed(badge, user, result) -> bool:
    wanted = {int(i) for i in badge.criteria.get("questionnaires", [])}
    if not wanted:
        return False
    done = set(
        QuestionnaireResult.objects
        .filter(user = user, is_test = False, passed = True, questionnaire_id__in = wanted)
        .values_list("questionnaire_id", flat = True)
    )
    return wanted <= done


@criterion("attempts_count")
def _attempts_count(badge, user, result) -> bool:
    from .models import QuestionnaireAttempt

    queryset = QuestionnaireAttempt.objects.filter(user = user, is_test = False)
    target   = badge.criteria.get("questionnaire")
    if target is not None:
        queryset = queryset.filter(questionnaire_id = int(target))
    return queryset.count() >= int(badge.criteria.get("count", 1))


def evaluate_badge(badge, user, result) -> bool:
    handler = _CRITERIA.get((badge.criteria or {}).get("type"))
    return bool(handler and handler(badge, user, result))


def award_for_result(result) -> list[UserBadge]:
    """Attribue les badges declenches par un resultat reel.

    Ne fait rien pour une tentative de test : c'est la garantie que le mode TEST
    ne pollue ni les badges ni les statistiques.
    """
    if result.is_test:
        return []

    awarded = []
    held    = set(UserBadge.objects.filter(user = result.user).values_list("badge_id", flat = True))

    for badge in Badge.objects.filter(active = True).exclude(id__in = held):
        if not evaluate_badge(badge, result.user, result):
            continue
        user_badge, created = UserBadge.objects.get_or_create(
            user     = result.user,
            badge    = badge,
            defaults = {
                "source":        c.BADGE_SOURCE_RESULT,
                "source_result": result,
                "is_test":       False,
            },
        )
        if created:
            awarded.append(user_badge)
            log(None, c.AUDIT_BADGE_AWARD, user_badge,
                questionnaire = result.questionnaire,
                new = {"badge": badge.code, "user": result.user_id})

    return awarded


def user_badges(user) -> list[dict]:
    """Badges d'un utilisateur, format expose par l'API."""
    return [
        {
            "id":         held.id,
            "code":       held.badge.code,
            "name":       held.badge.name,
            "description": held.badge.description,
            "icon":       held.badge.icon,
            "level":      held.level,
            "awarded_at": held.awarded_at.isoformat(),
            "source":     held.source,
            "source_result": held.source_result_id,
        }
        for held in UserBadge.objects.filter(user = user).select_related("badge")
    ]
