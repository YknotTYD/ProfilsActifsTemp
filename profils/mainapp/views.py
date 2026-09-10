from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse, JsonResponse, Http404
from django.shortcuts           import render, redirect
from django.contrib.auth        import logout as logout_
from .models                    import Role, VideoLink, VideoFile
from django.utils               import timezone
from . import constants
from django.db import connections
from django.db.models import Q
from django.db.utils import OperationalError
from profils.profiles           import constants as pc
from profils.profiles.feed      import playback
from django.core.paginator      import Paginator

def _candidate(user) -> dict:
    """Carte d'identite du candidat, affichee sous sa vignette video.

    Le titre, le resume et la photo viennent du profil professionnel : la
    grille n'a pas sa propre notion de candidat, elle affiche celle que le
    profil expose deja. Un utilisateur qui n'a jamais ouvert son profil n'en
    a pas encore -- l'acces retombe alors sur son seul nom d'utilisateur
    plutot que de casser la page.
    """

    profile = getattr(user, "professional_profile", None)

    return {
        "name":        profile.full_name if profile else user.username,
        "title":       profile.headline  if profile else "",
        "description": profile.summary   if profile else "",
        "avatar_url":  profile.photo_url if profile else "",
        "initial":     (user.username or "?")[0].upper(),
        "profile_url": f"/profile/{user.username}/",
    }

def get_video_filepaths(request: HttpRequest) -> list[dict]:
    """Videos televersees par fichier, mises en forme pour la grille.

    Moderation desactivee temporairement : toutes les videos sont affichees
    quel que soit leur `status`.
    """

    files = (
        VideoFile.objects
            .select_related("user", "user__professional_profile")
            # retrait du catalogue (RGPD art. 21) : la grille recruteur est une
            # liste filtree comme une autre, un profil retire n'y figure plus.
            .filter(Q(user__professional_profile__isnull = True)
                    | Q(user__professional_profile__withdrawn_at__isnull = True))
            .order_by("-id")
    )

    return [
        {
            "id":         f"file-{video.id}",
            "video_url":  video.file.url,
            "video_mode": "file",
            "poster_url": "",
            "candidate":  _candidate(video.user),
        }
        for video in files
    ]

def get_videos(request: HttpRequest) -> list[dict]:
    """Videos des candidats, mises en forme pour la grille recruteur/admin.

    Lit directement `profiles.ProfileVideo` (pipeline unifie), en reutilisant
    les regles de visibilite de `feed._visible_video_filter` et la logique de
    lecture de `feed.playback` -- `dashboard_feed_items` n'existe plus dans
    `feed.py`, ce module-ci en est desormais le seul point d'assemblage.
    """
    from profils.profiles.feed import _visible_video_filter, playback
    from profils.profiles.models import ProfileVideo

    videos = list(
        VideoLink.objects
            .select_related("user", "user__professional_profile")
            # retrait du catalogue (RGPD art. 21) : un profil retire ne figure
            # plus dans la grille recruteur.
            .filter(Q(user__professional_profile__isnull = True)
                    | Q(user__professional_profile__withdrawn_at__isnull = True))
            .order_by("-id")
    )

    items = []
    for video in videos:
        mode, url = playback(video.source_type, video.file_url, video_id=video.id)
        items.append({
            "id":         video.id,
            "video_url":  url,
            "video_mode": mode,
            "poster_url": video.thumbnail_url,
            "candidate": {
                "name":        video.profile.full_name or video.profile.username,
                "title":       video.profile.headline,
                "description": video.profile.summary,
                "avatar_url":  video.profile.photo_url,
                "initial":     (video.profile.username or "?")[0].upper(),
                "profile_url": f"/profile/{video.profile.username}/",
            },
        })
    return items


def candidate_grid(request: HttpRequest):
    """Page courante de la grille de profils (points 3.2 et 3.4)."""
    paginator = Paginator(get_videos(request), constants.CANDIDATE_GRID_PAGE_SIZE)
    return paginator.get_page(request.GET.get("page"))

def _my_video_status(user):
    """Statut de la video de presentation de `user`, cote pipeline
    `profiles.ProfileVideo` -- celui que sert `/profiles/me/video/`.

    Le formulaire d'upload de la page d'accueil postait autrefois vers
    `mainapp.VideoLink`, un second systeme de moderation invisible du
    panneau d'administration dedie. Le tableau de bord affiche desormais un
    resume tire de la meme source que la page de gestion, pour qu'il n'y ait
    plus qu'un seul endroit ou une video de presentation existe.
    """
    from profils.profiles import constants as pc
    from profils.profiles import services as profile_services
    from profils.profiles.models import ProfileVideo

    profile = profile_services.get_profile(user)
    rows = list(
        ProfileVideo.objects.filter(profile = profile, is_presentation = True)
            .exclude(status__in = (pc.VIDEO_DELETED, pc.VIDEO_HIDDEN))
            .order_by("-created_at")
    )
    return {
        "current": next((v for v in rows if v.status == pc.VIDEO_PUBLISHED), None),
        "pending": next((v for v in rows if v.status != pc.VIDEO_PUBLISHED), None),
    }

def main(request: HttpRequest) -> HttpResponse:

    role = (
        str(Role.objects.filter(user = request.user).first())
            if request.user.is_authenticated else "None"
    )

    return render(
        request,
        "main.html",
        {
            "user":  request.user,
            "role":  role,
            "grid":  candidate_grid(request) if role in ("Recruiter", "Admin") else None,
            "my_video_status": _my_video_status(request.user) if role == "JobSeeker" else None,
        }
    )

def register(request: HttpRequest) -> HttpResponse:

    if request.user.is_authenticated:
        return main(request)

    today = timezone.localdate()
    try:
        max_birth_date = today.replace(year = today.year - constants.MINIMUM_REGISTRATION_AGE)
    except ValueError:
        max_birth_date = today.replace(year = today.year - constants.MINIMUM_REGISTRATION_AGE, day = 28)

    return render(request, "register.html", {
        "error": request.GET.get("error"),
        "username": request.GET.get("username", ""),
        "birth_date": request.GET.get("birth_date", ""),
        "is_recruiter": request.GET.get("is_recruiter", "0"),
        "organisation": request.GET.get("organisation", ""),
        "max_birth_date": max_birth_date,
    })

def login(request: HttpRequest) -> HttpResponse:

    if request.user.is_authenticated:
        return main(request)

    return render(request, "login.html")

def logout(request: HttpRequest) -> HttpResponse:

    if not request.user.is_authenticated:
        return main(request)

    logout_(request)
    return redirect("/")

def quiz(request: HttpRequest) -> HttpResponse:

    if not request.user.is_authenticated:
        return redirect("/login/")

    from profils.questionnaires             import constants as qc
    from profils.questionnaires.access      import visible_questionnaires
    from profils.questionnaires.models      import Questionnaire
    from profils.questionnaires.serializers import public_questionnaire

    questionnaires = visible_questionnaires(
        request.user,
        Questionnaire.objects.exclude(status = qc.STATUS_DRAFT).select_related("current_version"),
    )

    return render(request, "quiz.html", {
        "questionnaires": [public_questionnaire(q, request.user) for q in questionnaires],
    })

def cgu(request: HttpRequest) -> HttpResponse:
    return render(request, "cgu.html")

def health(request: HttpRequest) -> JsonResponse:

    try:
        db_conn = connections['default']
        db_conn.cursor()
    except OperationalError:
        return JsonResponse({'status': 'error', 'database': 'down'}, status = 503)

    return JsonResponse({'status': 'ok', 'database': 'up'})
