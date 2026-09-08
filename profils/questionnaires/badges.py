"""Attribution et presentation des badges de certification.

`award_for_result` est appele a la fin de chaque tentative reelle et evalue les
criteres declaratifs. Les tentatives de mode TEST n'attribuent jamais de badge.

Un badge de certification atteste des competences evaluees : il n'ouvre aucun
droit et n'autorise personne a exercer quoi que ce soit (cf. la commande
`normaliser_certification`).

Cote affichage, deux entrees :

  `user_badges`  -- ce qu'une personne a obtenu, format API ;
  `badge_shelf`  -- la collection complete, obtenus et restants, pour l'etagere
                    affichee sur un profil ;
  `rank_of`      -- le rang, qui choisit l'illustration.

Ajouter un nouveau critere = ajouter une fonction decoree `@criterion("...")`.
"""

from . import constants as c
from .auditing import log
from .models   import Badge, QuestionnaireResult, UserBadge

_CRITERIA: dict[str, callable] = {}

# Rangs, du plus commun au plus rare. L'illustration de chaque rang vit dans
# `static/badge/rank-<rang>-light.svg` (source : `public/badge/`).
RANKS = ("bronze", "silver", "gold", "platinum")

# A defaut de rang explicite, il se deduit du critere : ce qu'un badge demande
# dit deja ce qu'il vaut.
_RANK_BY_CRITERION = {
    "questionnaire_passed":  "bronze",
    "attempts_count":        "silver",
    "min_percentage":        "gold",
    "questionnaires_passed": "platinum",
}

def rank_of(badge) -> str:
    """Rang d'un badge : bronze, silver, gold ou platinum.

    `Badge.icon` sert de rang explicite -- c'est le seul champ libre du modele,
    et le renseigner depuis l'admin suffit a changer l'illustration sans
    migration. Une valeur inconnue est ignoree plutot que rendue : elle
    produirait une image manquante.
    """
    explicit = (badge.icon or "").strip().lower()
    if explicit in RANKS:
        return explicit
    return _RANK_BY_CRITERION.get((badge.criteria or {}).get("type"), "bronze")

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

def card(badge, held = None) -> dict:
    """Un badge tel que l'affiche l'interface, obtenu ou non.

    `held` absent = badge encore a decrocher : la carte porte les memes champs,
    `earned` a False, et aucune date. L'etagere peut ainsi rendre une case
    verrouillee sans avoir a connaitre deux formes de donnees.
    """
    return {
        "code":        badge.code,
        "name":        badge.name,
        "description": badge.description,
        "rank":        rank_of(badge),
        "earned":      held is not None,
        "level":       held.level if held else 0,
        "max_level":   badge.max_level,
        "awarded_at":  held.awarded_at.isoformat() if held else None,
    }

def user_badges(user) -> list[dict]:
    """Badges d'un utilisateur, format expose par l'API.

    `icon` reste le champ brut du modele -- c'est un contrat d'API deja publie ;
    `rank` en donne la lecture normalisee, celle que l'interface utilise.
    """
    return [
        {
            "id":         held.id,
            "code":       held.badge.code,
            "name":       held.badge.name,
            "description": held.badge.description,
            "icon":       held.badge.icon,
            "rank":       rank_of(held.badge),
            "level":      held.level,
            "awarded_at": held.awarded_at.isoformat(),
            "source":     held.source,
            "source_result": held.source_result_id,
        }
        for held in UserBadge.objects.filter(user = user).select_related("badge")
    ]

def badge_shelf(user, include_locked: bool = False) -> list[dict]:
    """Etagere de badges d'une personne.

    Par defaut, seuls les badges obtenus : c'est ce qu'un visiteur a besoin de
    voir. `include_locked` ajoute les badges actifs restants -- utile sur son
    propre profil, ou l'etagere sert aussi a montrer ce qui reste a decrocher.
    Les badges obtenus passent devant, les plus recents en tete.
    """
    held_by_badge = {
        held.badge_id: held
        for held in UserBadge.objects.filter(user = user).select_related("badge")
    }
    earned = sorted(
        (card(held.badge, held) for held in held_by_badge.values()),
        key = lambda entry: entry["awarded_at"], reverse = True,
    )
    if not include_locked:
        return earned

    locked = [
        card(badge)
        for badge in Badge.objects.filter(active = True).exclude(id__in = held_by_badge)
    ]
    return earned + locked
