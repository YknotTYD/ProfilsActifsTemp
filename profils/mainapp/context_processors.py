"""Contexte de la barre de navigation, identique sur toutes les pages.

Avant, chaque vue decidait quels liens la barre pouvait montrer en passant (ou
en oubliant) `can_manage`, `capabilities`, `can_message`... : la barre changeait
donc d'une page a l'autre, et un administrateur ne voyait ses entrees
d'administration que sur certaines pages. Tout est calcule ici une fois, pour
que `partials/_navbar.html` n'ait qu'une seule source.
"""

from .models import Role

_ROLE_LABELS = {"Admin": "Admin", "Recruiter": "Recruteur", "JobSeeker": "Candidat"}

def navigation(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav": {"authenticated": False}}

    from profils.profiles.permissions import has_perm, is_platform_admin, is_recruiter
    from profils.profiles import constants as pc
    from profils.questionnaires.permissions import can_manage

    role = Role.objects.filter(user = user).values_list("role", flat = True).first()

    return {"nav": {
        "authenticated":            True,
        "username":                 user.username,
        "role":                     role or "",
        "role_label":               _ROLE_LABELS.get(role, role or ""),
        "is_admin":                 is_platform_admin(user),
        "is_staff":                 user.is_staff,
        "is_recruiter":             is_recruiter(user),
        "can_moderate_videos":      has_perm(user, pc.PERM_MODERATE),
        "can_manage_questionnaires": can_manage(user),
    }}
