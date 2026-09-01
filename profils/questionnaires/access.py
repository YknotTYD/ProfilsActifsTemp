##access.py
"""Evaluation des regles d'acces et de visibilite.

Les regles sont stockees en forme normale disjonctive : AND a l'interieur d'un
groupe, OR entre les groupes. L'evaluation est integralement cote serveur et
concerne trois questions distinctes (section 23) :

    * visibilite     : l'utilisateur voit-il que le questionnaire existe ?
    * accessibilite  : peut-il reellement le commencer ?
    * resultats      : que peut-il consulter apres avoir repondu ?
"""

from collections import defaultdict
from datetime    import timedelta

from django.utils import timezone

from . import constants as c
from .models      import UserBadge
from .permissions import is_questionnaire_admin, user_roles


class AccessDenied(Exception):
    """Refus d'acces, avec un motif exploitable par l'API."""

    def __init__(self, reason: str, code: str = "access_denied", status: int = 403):
        super().__init__(reason)
        self.reason = reason
        self.code   = code
        self.status = status


def _rule_matches(rule, user, roles: set[str], badge_ids: set[int]) -> bool:
    if rule.rule_type == c.RULE_EVERYONE:
        matched = True
    elif rule.rule_type == c.RULE_USER:
        matched = rule.target_user_id == user.id
    elif rule.rule_type == c.RULE_ROLE:
        matched = rule.role.lower() in roles
    elif rule.rule_type == c.RULE_BADGE:
        matched = rule.badge_id in badge_ids
    else:                                               # pragma: no cover
        matched = False
    return not matched if rule.negate else matched


def evaluate_rules(questionnaire, user, kind: str) -> bool:
    """Applique le jeu de regles `kind` a `user`.

    Sans aucune regle du type demande, l'acces est ouvert a tout utilisateur
    authentifie ; la visibilite retombe alors sur l'accessibilite.
    """
    if not user or not user.is_authenticated:
        return False

    rules = [r for r in questionnaire.access_rules.all() if r.kind == kind]
    if not rules:
        if kind == c.RULE_KIND_VISIBILITY:
            return evaluate_rules(questionnaire, user, c.RULE_KIND_ACCESS)
        return True

    roles     = user_roles(user)
    badge_ids = set(UserBadge.objects.filter(user = user).values_list("badge_id", flat = True))

    groups = defaultdict(list)
    for rule in rules:
        groups[rule.group_index].append(rule)

    return any(
        all(_rule_matches(rule, user, roles, badge_ids) for rule in group)
        for group in groups.values()
    )


def can_see(questionnaire, user) -> bool:
    """L'utilisateur sait-il que ce questionnaire existe ?"""
    if is_questionnaire_admin(user):
        return True
    if questionnaire.status in (c.STATUS_DRAFT, c.STATUS_ARCHIVED):
        return False
    if questionnaire.status == c.STATUS_TEST:
        return evaluate_rules(questionnaire, user, c.RULE_KIND_ACCESS)
    return evaluate_rules(questionnaire, user, c.RULE_KIND_VISIBILITY)


def assert_can_start(questionnaire, user, *, test: bool = False):
    """Verifie tout ce qui conditionne le demarrage d'une tentative.

    Leve `AccessDenied` avec un motif precis ; ne renvoie rien en cas de succes.
    """
    from . import constants as k

    if not user or not user.is_authenticated:
        raise AccessDenied("authentification requise", "unauthenticated", 401)

    admin = is_questionnaire_admin(user)

    if test:
        from .permissions import has_perm

        if not (admin or has_perm(user, k.PERM_TEST)):
            raise AccessDenied("mode test reserve aux testeurs autorises", "test_forbidden")
    else:
        if questionnaire.status == k.STATUS_INVALIDATED:
            raise AccessDenied("questionnaire invalide", "questionnaire_invalidated", 409)
        if questionnaire.status == k.STATUS_DISABLED:
            raise AccessDenied("questionnaire desactive", "questionnaire_disabled", 409)
        if questionnaire.status == k.STATUS_ARCHIVED:
            raise AccessDenied("questionnaire archive", "questionnaire_archived", 409)
        if questionnaire.status in (k.STATUS_DRAFT, k.STATUS_TEST):
            raise AccessDenied("questionnaire non publie", "questionnaire_not_published", 409)

        if not questionnaire.is_within_availability():
            raise AccessDenied(
                "questionnaire hors de sa periode de disponibilite",
                "outside_availability", 409,
            )

        if not evaluate_rules(questionnaire, user, k.RULE_KIND_ACCESS):
            raise AccessDenied("acces refuse par les regles du questionnaire", "rules_denied")


def assert_version_usable(version, *, test: bool = False):
    """Verifie qu'une version peut encore recevoir des reponses."""
    if version is None:
        raise AccessDenied("aucune version utilisable", "no_version", 409)
    if version.status == c.STATUS_INVALIDATED:
        raise AccessDenied("version invalidee", "version_invalidated", 409)
    if not version.accepts_answers:
        raise AccessDenied(f"version indisponible (statut {version.status})", "version_closed", 409)
    if not test and version.status != c.STATUS_PUBLISHED:
        raise AccessDenied("version non publiee", "version_not_published", 409)
    if test and version.status not in (c.STATUS_TEST, c.STATUS_PUBLISHED, c.STATUS_DRAFT):
        raise AccessDenied("version non testable", "version_not_testable", 409)
    if not version.is_valid_now():
        raise AccessDenied("version hors de sa periode de validite", "version_expired", 409)


def visible_questionnaires(user, queryset = None):
    """Questionnaires que `user` a le droit de voir."""
    from .models import Questionnaire

    queryset = queryset if queryset is not None else Questionnaire.objects.all()
    queryset = queryset.prefetch_related("access_rules")
    return [q for q in queryset if can_see(q, user)]


def result_visibility(questionnaire, user) -> dict:
    """Ce que l'utilisateur a le droit de voir dans un resultat."""
    settings = questionnaire.visibility_settings
    if is_questionnaire_admin(user):
        return {key: True for key in settings}
    return settings


def attempt_deadline(questionnaire, started_at = None):
    """Echeance d'une tentative, en combinant duree max et delai d'expiration."""
    started_at = started_at or timezone.now()
    candidates = []
    if questionnaire.time_limit_seconds:
        candidates.append(started_at + timedelta(seconds = questionnaire.time_limit_seconds))
    if questionnaire.attempt_expiry_seconds:
        candidates.append(started_at + timedelta(seconds = questionnaire.attempt_expiry_seconds))
    if questionnaire.available_until:
        candidates.append(questionnaire.available_until)
    return min(candidates) if candidates else None
