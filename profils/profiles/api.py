##api.py
"""API des profils professionnels.

Couche de transport uniquement : la validation est dans `services`, les
decisions d'acces dans `permissions` et `visibility`, la recherche dans
`search`. Aucune vue ne decide seule de ce qu'elle a le droit de renvoyer.

Les routes `/me/` operent toujours sur le profil de l'utilisateur connecte,
jamais sur un identifiant fourni par le client. Quand un identifiant est
inevitable (celui d'une experience, par exemple), `assert_owns_child` verifie
qu'il appartient bien au profil avant toute ecriture.
"""

from django.db.models import Q

from . import constants as c
from . import engagement, moderation, permissions, serializers, services
from .http import BadRequest, api, body, fail, ok
from .models import (
    Certification, Education, Language, ProfileVideo, Project, Skill, UserLanguage,
    VideoModerationEvent, WorkExperience,
)
from .search import ProfileQuery, search as run_search
from .skills import resolve_skill
from .visibility import (
    PreviewViewer, assert_can_view, audience_of, can_view_video, visible_videos,
)


# --------------------------------------------------------------------------- #
# Vocabulaire et referentiels
# --------------------------------------------------------------------------- #

@api(("GET",), login = False)
def meta(request):
    """Listes de choix : niveaux, domaines, contrats, visibilites..."""
    return ok(serializers.meta())


@api(("GET", "POST"), login = False)
def skills(request):
    """Referentiel de competences.

    GET  : recherche pour l'autocompletion (`?q=jav&category=LANGUAGE`).
    POST : ajout d'une competence au referentiel, canonicalisee. Renvoyer une
           competence existante plutot qu'un doublon est le comportement
           attendu, pas une erreur.
    """
    if request.method == "GET":
        queryset = Skill.objects.all()
        if term := (request.GET.get("q") or "").strip():
            queryset = queryset.filter(
                Q(name__icontains = term) | Q(slug__icontains = term)
                | Q(aliases__normalized__icontains = term)
            ).distinct()
        if category := request.GET.get("category"):
            queryset = queryset.filter(category = category)

        raw_limit = request.GET.get("limit") or "20"
        try:
            limit = max(1, min(int(raw_limit), 100))
        except ValueError:
            raise BadRequest(f"limit invalide: {raw_limit!r}", "invalid_field")
        return ok({"skills": [serializers.skill_reference(s) for s in queryset[:limit]]})

    if not request.user.is_authenticated:
        return fail("authentification requise", "unauthenticated", 401)

    payload = body(request)
    skill   = resolve_skill(
        payload.get("name") or "", create = True, category = payload.get("category"),
    )
    return ok(serializers.skill_reference(skill), status = 201)


@api(("GET",), login = False)
def languages(request):
    return ok({"languages": [
        {"id": row.id, "code": row.code, "name": row.name}
        for row in Language.objects.all()
    ]})


# --------------------------------------------------------------------------- #
# Consultation d'un profil (section 2)
# --------------------------------------------------------------------------- #

@api(("GET",), login = False)
def profile_detail(request, username):
    """Profil public, expurge selon ce que le visiteur a le droit de voir."""
    profile = services.profile_by_username(username)
    if profile is None:
        return fail("profil introuvable", "not_found", 404)

    assert_can_view(request.user, profile)
    return ok(serializers.public_profile(profile, _viewer(request, profile)))


@api(("GET",), login = False)
def profile_videos(request, username):
    """Videos d'un profil (section 15).

    La section existe et repond des maintenant ; elle renvoie une liste vide
    tant que personne n'a publie de video. C'est un etat vide, pas un faux
    contenu.
    """
    profile = services.profile_by_username(username)
    if profile is None:
        return fail("profil introuvable", "not_found", 404)

    assert_can_view(request.user, profile)
    viewer   = _viewer(request, profile)
    is_owner = audience_of(viewer, profile) >= c.AUDIENCE_OWNER
    rows     = visible_videos(viewer, profile).prefetch_related("skill_links__skill")
    return ok({
        "username": profile.username,
        "videos":   [serializers.video(row, include_moderation = is_owner) for row in rows],
    })


def _viewer(request, profile):
    """Utilisateur du point de vue duquel le profil est rendu.

    `?preview=public` ou `?preview=registered` permet au proprietaire de voir
    sa page telle qu'un visiteur la verra (section 22). La previsualisation ne
    peut que **restreindre** : elle ne donne jamais acces a ce que l'on ne
    verrait pas autrement.
    """
    preview = request.GET.get("preview")
    if not preview or not permissions.owns(request.user, profile):
        return request.user
    if preview == "public":
        return PreviewViewer(c.AUDIENCE_ANONYMOUS)
    if preview == "registered":
        return PreviewViewer(c.AUDIENCE_REGISTERED)
    return request.user


# --------------------------------------------------------------------------- #
# Recherche (sections 12 a 14)
# --------------------------------------------------------------------------- #

@api(("GET",), login = False)
def search(request):
    """Recherche de profils.

    Exemple :
        /api/profiles/search/?skill=java&skill=docker&mode=AND
        &min_level=INTERMEDIATE&contract=CDI&available=1&sort=relevance
    """
    query  = ProfileQuery.from_params(request.GET)
    result = run_search(query, request.user)
    return ok(serializers.search_response(result, query, request.user))


# --------------------------------------------------------------------------- #
# Mon profil
# --------------------------------------------------------------------------- #

def _me(request):
    return services.get_profile(request.user)


@api(("GET", "PUT", "PATCH"))
def me(request):
    """Consultation et modification de mon profil."""
    profile = _me(request)
    if request.method != "GET":
        permissions.assert_can_edit(request.user, profile)
        services.update_profile(profile, body(request))
        profile.refresh_from_db()
    return ok(serializers.owner_profile(profile))


@api(("GET", "PUT", "PATCH"))
def me_privacy(request):
    """Visibilite du profil, des sections, et apparition dans les recherches."""
    profile = _me(request)
    if request.method != "GET":
        permissions.assert_can_edit(request.user, profile)
        payload = body(request)
        if "profile_visibility" in payload:
            services.update_profile(profile, {"visibility": payload["profile_visibility"]})
        if isinstance(payload.get("sections"), dict):
            services.update_visibility(profile, payload["sections"])
        if isinstance(payload.get("search"), dict):
            services.update_search_settings(profile, payload["search"])
        profile.refresh_from_db()

    return ok({
        "profile_visibility": profile.visibility,
        "sections":           profile.visibility_settings().as_dict(),
        "search":             serializers.search_settings(profile),
    })


@api(("GET", "PUT"))
def me_links(request):
    profile = _me(request)
    if request.method == "PUT":
        permissions.assert_can_edit(request.user, profile)
        services.set_links(profile, body(request).get("links"))
    return ok({"links": [serializers.link(row) for row in profile.links.all()]})


# --------------------------------------------------------------------------- #
# Competences (section 3)
# --------------------------------------------------------------------------- #

@api(("GET", "POST"))
def me_skills(request):
    profile = _me(request)
    if request.method == "POST":
        permissions.assert_can_edit(request.user, profile)
        row = services.add_skill(profile, body(request))
        return ok(serializers.user_skill(row), status = 201)
    return ok({"skills": [
        serializers.user_skill(row) for row in profile.skills.select_related("skill")
    ]})


@api(("PUT", "PATCH", "DELETE"))
def me_skill_item(request, skill_id):
    """L'identifiant de la route est celui de la **competence**, pas du lien.

    C'est ce que decrit la section 21, et c'est plus stable : le client
    connait la competence qu'il manipule, pas la cle technique de son
    rattachement.
    """
    profile = _me(request)
    row = profile.skills.filter(skill_id = skill_id).select_related("skill").first()
    permissions.assert_owns_child(request.user, profile, row, "competence")

    if request.method == "DELETE":
        services.remove_skill(row)
        return ok()
    return ok(serializers.user_skill(services.update_skill(row, body(request))))


@api(("POST",))
def me_skills_reorder(request):
    profile = _me(request)
    permissions.assert_can_edit(request.user, profile)
    rows = services.reorder_skills(profile, body(request).get("skills"))
    return ok({"skills": [serializers.user_skill(row) for row in rows]})


# --------------------------------------------------------------------------- #
# Sections de parcours
# --------------------------------------------------------------------------- #

def _collection(request, relation: str, serialize, create, prefetch = ("skill_links__skill",)):
    """GET : lister mes entrees. POST : en creer une."""
    profile = _me(request)
    if request.method == "POST":
        permissions.assert_can_edit(request.user, profile)
        return ok(serialize(create(profile, body(request))), status = 201)

    rows = getattr(profile, relation).all()
    if prefetch:
        rows = rows.prefetch_related(*prefetch)
    return ok({relation: [serialize(row) for row in rows]})


def _item(request, model, pk, serialize, update, delete, label: str):
    """PUT : modifier une entree. DELETE : la supprimer."""
    profile = _me(request)
    row = model.objects.filter(pk = pk).first()
    permissions.assert_owns_child(request.user, profile, row, label)

    if request.method == "DELETE":
        delete(row)
        return ok()
    return ok(serialize(update(row, body(request))))


@api(("GET", "POST"))
def me_experiences(request):
    return _collection(request, "experiences", serializers.experience, services.create_experience)


@api(("PUT", "PATCH", "DELETE"))
def me_experience_item(request, pk):
    return _item(request, WorkExperience, pk, serializers.experience,
                 services.update_experience, services.delete_experience, "experience")


@api(("GET", "POST"))
def me_education(request):
    return _collection(request, "education", serializers.education, services.create_education)


@api(("PUT", "PATCH", "DELETE"))
def me_education_item(request, pk):
    return _item(request, Education, pk, serializers.education,
                 services.update_education, services.delete_education, "formation")


@api(("GET", "POST"))
def me_certifications(request):
    return _collection(request, "certifications", serializers.certification,
                       services.create_certification)


@api(("PUT", "PATCH", "DELETE"))
def me_certification_item(request, pk):
    return _item(request, Certification, pk, serializers.certification,
                 services.update_certification, services.delete_certification, "certification")


@api(("GET", "POST"))
def me_projects(request):
    return _collection(request, "projects", serializers.project, services.create_project)


@api(("PUT", "PATCH", "DELETE"))
def me_project_item(request, pk):
    return _item(request, Project, pk, serializers.project,
                 services.update_project, services.delete_project, "projet")


@api(("GET", "POST"))
def me_languages(request):
    profile = _me(request)
    if request.method == "POST":
        permissions.assert_can_edit(request.user, profile)
        row = services.set_language(profile, body(request))
        return ok(serializers.language(row), status = 201)
    return ok({"languages": [
        serializers.language(row) for row in profile.languages.select_related("language")
    ]})


@api(("DELETE",))
def me_language_item(request, pk):
    profile = _me(request)
    row = UserLanguage.objects.filter(pk = pk).select_related("language").first()
    permissions.assert_owns_child(request.user, profile, row, "langue")
    services.remove_language(row)
    return ok()


# --------------------------------------------------------------------------- #
# Videos (sections 15 a 17, et moderation)
# --------------------------------------------------------------------------- #
#
# Ces routes ne passent pas par `_collection`/`_item` : la moderation leur
# donne assez de comportement propre (soumission, confirmation explicite,
# re-soumission) pour que forcer le moule generique coute plus cher qu'il
# n'economise.

def _own_video(request, pk) -> ProfileVideo:
    profile = _me(request)
    video = ProfileVideo.objects.filter(pk = pk).select_related("profile").first()
    permissions.assert_owns_child(request.user, profile, video, "video")
    return video


@api(("GET", "POST"))
def me_videos(request):
    """Mes videos, tous statuts confondus (section 1 : "consulter a tout
    moment le statut de ses videos") ; POST soumet un nouveau lien.
    """
    profile = _me(request)
    if request.method == "POST":
        permissions.assert_can_edit(request.user, profile)
        video = services.submit_video_link(profile, body(request))
        return ok(serializers.video(video, include_moderation = True), status = 201)

    rows = profile.videos.exclude(status = c.VIDEO_DELETED).prefetch_related("skill_links__skill")
    return ok({"videos": [serializers.video(row, include_moderation = True) for row in rows]})


@api(("GET", "PATCH", "DELETE"))
def me_video_item(request, pk):
    video = _own_video(request, pk)

    if request.method == "DELETE":
        services.delete_video(video, actor = c.ACTOR_OWNER, user = request.user)
        return ok()

    payload = body(request)
    if request.method == "PATCH":
        new_link = payload.pop("file_url", None)
        if new_link:
            services.replace_video_link(video, new_link, user = request.user)
        if payload:
            services.update_video(video, payload)

    return ok(serializers.video(video, include_moderation = True))


@api(("POST",))
def me_video_publish(request, pk):
    """Confirmation explicite de publication (section 2) : le seul geste qui
    rend une video de presentation visible au public.
    """
    video = _own_video(request, pk)
    services.publish_presentation_video(video, user = request.user)
    return ok(serializers.video(video, include_moderation = True))


@api(("POST",))
def me_video_resubmit(request, pk):
    """Re-soumission apres un refus (section 1)."""
    video = _own_video(request, pk)
    services.resubmit_video(video, user = request.user,
                            new_file_url = body(request).get("file_url"))
    return ok(serializers.video(video, include_moderation = True))


# --------------------------------------------------------------------------- #
# Videos : engagement du feed (vues, reactions)
# --------------------------------------------------------------------------- #

def _feed_video(request, pk):
    """Video visible du spectateur, ou None -- meme reponse 404 dans les deux
    cas, pour ne pas divulguer l'existence d'une video cachee."""
    video = ProfileVideo.objects.filter(pk = pk).select_related("profile__user").first()
    if video is None or not can_view_video(request.user, video):
        return None
    return video


@api(("POST",), login = False)
def video_view(request, pk):
    """Enregistre une vue sur une video du feed (section 6 : statistiques).

    Ouverte aux visiteurs anonymes -- une vue est une vue. Le dedoublonnage
    par session evite qu'un simple rechargement regonfle le compteur.
    """
    video = _feed_video(request, pk)
    if video is None:
        return fail("video introuvable", "not_found", 404)

    if not request.session.session_key:
        request.session.save()
    engagement.register_view(
        video,
        user = request.user if request.user.is_authenticated else None,
        session_key = request.session.session_key or "",
    )
    return ok({"views": ProfileVideo.objects.values_list("view_count", flat = True).get(pk = pk)})


@api(("POST",))
def video_react(request, pk):
    """Pose / retire / remplace un like-dislike sur une video du feed."""
    video = _feed_video(request, pk)
    if video is None:
        return fail("video introuvable", "not_found", 404)

    reaction = (body(request).get("reaction") or "").strip()
    try:
        return ok(engagement.set_reaction(video, request.user, reaction))
    except ValueError:
        return fail(f"reaction invalide: {reaction!r}", "invalid_field", 400)


# --------------------------------------------------------------------------- #
# Videos : moderation administrateur
# --------------------------------------------------------------------------- #

@api(("GET",), perm = c.PERM_MODERATE)
def admin_video_queue(request):
    """File d'attente de moderation : toutes les videos en `PENDING`."""
    rows = (ProfileVideo.objects.filter(status = c.VIDEO_PENDING)
            .select_related("profile__user").order_by("created_at"))
    return ok({"videos": [
        {**serializers.video(row, include_moderation = True),
         "profile": {"username": row.profile.username, "user_id": row.profile.user_id}}
        for row in rows
    ]})


def _admin_video(pk) -> ProfileVideo:
    video = ProfileVideo.objects.filter(pk = pk).first()
    if video is None:
        from django.core.exceptions import ObjectDoesNotExist
        raise ObjectDoesNotExist("video introuvable")
    return video


@api(("POST",), perm = c.PERM_MODERATE)
def admin_video_approve(request, pk):
    video = _admin_video(pk)
    services.approve_video(video, user = request.user)
    return ok(serializers.video(video, include_moderation = True))


@api(("POST",), perm = c.PERM_MODERATE)
def admin_video_reject(request, pk):
    video = _admin_video(pk)
    reason = (body(request).get("reason") or "").strip()
    services.reject_video(video, reason, user = request.user)
    return ok(serializers.video(video, include_moderation = True))


@api(("GET",), perm = c.PERM_MODERATE)
def admin_video_history(request, pk):
    video  = _admin_video(pk)
    events = video.moderation_events.select_related("actor")
    return ok({"history": [
        {
            "actor":      event.actor.username if event.actor_id else None,
            "source":     event.source,
            "old_status": event.old_status,
            "new_status": event.new_status,
            "reason":     event.reason,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]})
