##permissions.py
"""Roles et propriete des ressources.

Le pont vers le modele `Role` de `mainapp` existe deja dans
`questionnaires.permissions.user_roles` : il agrege `Role`, les groupes Django
et les drapeaux `is_superuser` / `is_staff`. On le reutilise plutot que d'en
ecrire un second, qui divergerait au premier changement de nomenclature.

Regle de base de tout ce module : une ecriture n'est autorisee que sur ses
propres donnees professionnelles. Le frontend n'est jamais consulte.
"""

from django.core.exceptions import PermissionDenied

from profils.questionnaires.permissions import user_roles

from . import constants as c

ADMIN_ROLE     = "admin"
RECRUITER_ROLE = "recruiter"


class ProfileAccessDenied(PermissionDenied):
    """Refus d'acces, avec un motif exploitable par l'API."""

    def __init__(self, reason: str, code: str = "access_denied", status: int = 403):
        super().__init__(reason)
        self.reason = reason
        self.code   = code
        self.status = status


def is_platform_admin(user) -> bool:
    """Statut d'administrateur, memorise sur l'objet utilisateur.

    `user_roles` interroge la base (groupes Django + `mainapp.Role`) a chaque
    appel. `is_platform_admin` est lui-meme appele par `has_perm`, et
    `can_see_private` appelle `has_perm` deux fois : sans memorisation, servir
    une page de resultats de recherche relancerait ces deux requetes une fois
    par ligne de resultat au lieu d'une fois pour toute la reponse.

    L'attribut vit sur l'instance `User` elle-meme, comme le fait deja Django
    pour son propre cache de permissions (`_perm_cache`) : une instance ne
    survit jamais au-dela de la requete qui l'a chargee, donc rien n'est
    jamais perime d'une requete a l'autre.
    """
    if not user or not user.is_authenticated:
        return False
    cached = getattr(user, "_profiles_is_admin_cache", None)
    if cached is None:
        cached = user.is_superuser or ADMIN_ROLE in user_roles(user)
        try:
            user._profiles_is_admin_cache = cached
        except AttributeError:      # pragma: no cover — objet utilisateur immuable
            pass
    return cached


def is_recruiter(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return RECRUITER_ROLE in user_roles(user)


def has_perm(user, perm: str) -> bool:
    """Verifie une permission applicative."""
    if not user or not user.is_authenticated:
        return False
    if is_platform_admin(user):
        return True
    return user.has_perm(perm)


def can_see_private(user) -> bool:
    """Droit de consulter un profil que son proprietaire a rendu prive.

    Volontairement etroit : l'administration de la plateforme et la moderation,
    rien d'autre. Etre recruteur ne donne aucun acces particulier.
    """
    return has_perm(user, c.PERM_VIEW_PRIVATE) or has_perm(user, c.PERM_MODERATE)


def owns(user, profile) -> bool:
    return bool(
        user and user.is_authenticated and profile is not None
        and profile.user_id == user.id
    )


def can_edit_profile(user, profile) -> bool:
    return owns(user, profile) or has_perm(user, c.PERM_MODERATE)


def assert_can_edit(user, profile):
    """Verrou d'ecriture. Ne renvoie rien en cas de succes.

    C'est le seul point par lequel passent les ecritures de l'API : un
    utilisateur ne peut pas modifier les donnees professionnelles d'un autre.
    """
    if not user or not user.is_authenticated:
        raise ProfileAccessDenied("authentification requise", "unauthenticated", 401)
    if not can_edit_profile(user, profile):
        raise ProfileAccessDenied(
            "ce profil ne vous appartient pas", "not_owner", 403,
        )


def assert_owns_child(user, profile, child, label: str = "ressource"):
    """Verifie a la fois la propriete du profil et le rattachement de l'objet.

    Sans le second controle, un proprietaire legitime pourrait modifier
    l'experience d'un autre en devinant son identifiant : la route porte
    `/profiles/me/...`, mais l'identifiant, lui, vient du client.
    """
    assert_can_edit(user, profile)
    if child is None or child.profile_id != profile.pk:
        raise ProfileAccessDenied(f"{label} introuvable", "not_found", 404)


def capabilities(user) -> dict:
    """Capacites de l'utilisateur, pour piloter l'affichage de l'interface."""
    return {
        "authenticated":  bool(user and user.is_authenticated),
        "admin":          is_platform_admin(user),
        "recruiter":      is_recruiter(user),
        "manage_skills":  has_perm(user, c.PERM_MANAGE_SKILLS),
        "view_private":   can_see_private(user),
        "moderate":       has_perm(user, c.PERM_MODERATE),
    }
