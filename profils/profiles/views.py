##views.py
"""Pages des profils professionnels.

Comme dans `questionnaires/views.py`, les templates ne portent aucune logique
metier. La page de profil est rendue **cote serveur** a partir de la charge
utile deja expurgee par `serializers.public_profile` : elle est donc lisible
sans JavaScript, et une section masquee est absente du HTML, pas seulement
cachee en CSS.

Les pages d'edition et de recherche, elles, sont interactives et dialoguent
avec l'API apres le premier rendu.
"""

from django.http      import Http404
from django.shortcuts import redirect, render

from . import constants as c
from . import permissions, serializers, services
from .api        import _viewer
from .search     import ProfileQuery
from .visibility import can_view_profile


def _login_required(request):
    return None if request.user.is_authenticated else redirect("/login/")


def profile_page(request, username):
    """Page publique d'un profil : `/profile/<username>/`."""
    profile = services.profile_by_username(username)
    if profile is None or not can_view_profile(request.user, profile):
        # meme reponse dans les deux cas : ne pas reveler qu'un profil existe
        raise Http404

    viewer  = _viewer(request, profile)
    payload = serializers.public_profile(profile, viewer)

    from profils.messaging.rules import can_start as can_message

    return render(request, "profiles/profile.html", {
        "p":          payload,
        "profile":    profile,
        "is_owner":   permissions.owns(request.user, profile),
        "preview":    request.GET.get("preview") or "",
        "levels":     dict(c.SKILL_LEVELS),
        "degrees":    dict(c.DEGREE_LEVELS),
        "contracts":  dict(c.CONTRACT_TYPES),
        "work_modes": dict(c.WORK_MODES),
        "link_kinds": dict(c.LINK_KINDS),
        "cover_colors": c.COVER_COLORS,
        "capabilities": permissions.capabilities(request.user),
        # section 4 : un recruteur peut contacter ce candidat s'il a publie
        # une video -- l'import est local pour que `profiles` reste
        # chargeable sans `messaging` la ou ce bouton n'a pas de sens
        # (l'API, par exemple).
        "can_message": can_message(request.user, profile.user),
    })


def search_page(request):
    """Page de recherche de profils : `/profiles/`.

    Les criteres passes dans l'URL sont valides ici aussi, pour que la page
    puisse etre partagee avec ses filtres et retrouvee telle quelle. Les
    identifiants de competences ne suffisent pas a reconstruire les jetons
    affiches : `initial_skills` porte leur nom, resolu une seule fois ici.
    """
    from .http import BadRequest
    from .models import Language, Skill

    try:
        query = ProfileQuery.from_params(request.GET)
    except BadRequest:
        # un lien partage avec un filtre mal forme retombe sur une recherche
        # vide plutot que sur une page cassee ; toute autre exception, elle,
        # doit continuer a remonter au lieu d'etre avalee en silence.
        query = ProfileQuery()

    skills = Skill.objects.in_bulk(query.skill_ids)
    initial_skills = [
        {"id": skill_id, "name": skills[skill_id].name}
        for skill_id in query.skill_ids if skill_id in skills
    ]
    languages = Language.objects.in_bulk(query.language_ids)
    initial_language_codes = [
        languages[language_id].code
        for language_id in query.language_ids if language_id in languages
    ]

    return render(request, "profiles/search.html", {
        "meta":            serializers.meta(),
        "initial_query":   query.as_dict(),
        "initial_skills":  initial_skills,
        "initial_language_codes": initial_language_codes,
        "capabilities":    permissions.capabilities(request.user),
    })


def editor_page(request):
    """Interface d'edition de mon profil : `/profiles/edit/` (section 22)."""
    if response := _login_required(request):
        return response

    profile = services.get_profile(request.user)
    return render(request, "profiles/editor.html", {
        "meta":     serializers.meta(),
        "profile":  profile,
        "username": profile.username,
        "sections": c.PROFILE_SECTIONS,
        "capabilities": permissions.capabilities(request.user),
    })


def admin_videos_page(request):
    """Console de moderation video : `/profiles/admin/videos/`.

    Purement une coquille : la page se peuple elle-meme en appelant les
    routes `/api/profiles/admin/videos/...` deja existantes, comme le reste
    des pages interactives du module. Meme garde que `questionnaires.manage`
    -- 404 plutot que 403, pour ne pas laisser deviner que la page existe.
    """
    if response := _login_required(request):
        return response
    if not permissions.has_perm(request.user, c.PERM_MODERATE):
        raise Http404
    return render(request, "profiles/admin_videos.html", {
        "capabilities": permissions.capabilities(request.user),
    })


def my_profile_redirect(request):
    """`/profile/` renvoie l'utilisateur vers sa propre page.

    Le profil est cree ici s'il n'existe pas encore : un utilisateur qui vient
    de s'inscrire et n'a jamais rien enregistre ne doit pas atterrir sur un 404
    en cliquant sur "Mon profil".
    """
    if response := _login_required(request):
        return response
    services.get_profile(request.user)
    return redirect(f"/profile/{request.user.username}/")
