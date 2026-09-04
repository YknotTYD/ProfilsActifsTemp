"""Permissions d'administration.

Repose sur le systeme de permissions Django (permissions personnalisees
declarees sur `Questionnaire.Meta`) tout en reconnaissant le modele `Role` deja
present dans `mainapp` : un utilisateur portant le role `Admin` dispose des
memes droits qu'un superutilisateur sur les questionnaires.

Toutes les verifications passent par ce module, jamais par le frontend.
"""

from functools import wraps

from django.http import JsonResponse

from . import constants as c

ADMIN_ROLE = "admin"

def user_roles(user) -> set[str]:
    """Roles d'un utilisateur, en minuscules.

    Agrege le modele `Role` de `mainapp`, les groupes Django et les drapeaux
    `is_superuser` / `is_staff`.
    """
    if not user or not user.is_authenticated:
        return set()

    roles = {name.lower() for name in user.groups.values_list("name", flat = True)}

    try:
        from profils.mainapp.models import Role
    except Exception:
        Role = None
    if Role is not None:
        roles |= {
            str(role).lower()
            for role in Role.objects.filter(user = user).values_list("role", flat = True)
        }

    if user.is_superuser or user.is_staff:
        roles.add(ADMIN_ROLE)
    return roles

def is_questionnaire_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or ADMIN_ROLE in user_roles(user)

def has_perm(user, perm: str) -> bool:
    """Verifie une permission applicative."""
    if not user or not user.is_authenticated:
        return False
    if is_questionnaire_admin(user):
        return True
    return user.has_perm(perm)

def can_manage(user) -> bool:
    """Acces general a l'espace d'administration des questionnaires."""
    return any(
        has_perm(user, perm)
        for perm in (c.PERM_CREATE, c.PERM_UPDATE, c.PERM_VIEW, c.PERM_VIEW_ATTEMPTS)
    )

def require_perm(perm: str):
    """Decorateur de vue JSON exigeant une permission."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "authentification requise"}, status = 401)
            if not has_perm(request.user, perm):
                return JsonResponse({"error": "permission refusee", "required": perm}, status = 403)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator

def admin_capabilities(user) -> dict:
    """Capacites de l'utilisateur, pour piloter l'affichage de l'interface."""
    return {
        "create":     has_perm(user, c.PERM_CREATE),
        "update":     has_perm(user, c.PERM_UPDATE),
        "delete":     has_perm(user, c.PERM_DELETE),
        "publish":    has_perm(user, c.PERM_PUBLISH),
        "archive":    has_perm(user, c.PERM_ARCHIVE),
        "invalidate": has_perm(user, c.PERM_INVALIDATE),
        "test":       has_perm(user, c.PERM_TEST),
        "versions":   has_perm(user, c.PERM_MANAGE_VERSIONS),
        "access":     has_perm(user, c.PERM_MANAGE_ACCESS),
        "attempts":   has_perm(user, c.PERM_VIEW_ATTEMPTS),
        "results":    has_perm(user, c.PERM_VIEW_RESULTS),
        "statistics": has_perm(user, c.PERM_VIEW_STATS),
        "badges":     has_perm(user, c.PERM_MANAGE_BADGES),
    }
