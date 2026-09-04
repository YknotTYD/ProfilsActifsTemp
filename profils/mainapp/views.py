from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse, JsonResponse, Http404
from django.shortcuts           import render, redirect
from django.contrib.auth        import logout as logout_
from django.db.models           import Count, Q
from .models                    import Role, VideoLink, VideoFile, Reaction
from django.utils               import timezone
from . import constants
from django.db import connections
from django.db.utils import OperationalError

def _candidate(user) -> dict:
    """Carte d'identite du candidat, affichee en bas de sa video.

    Le titre, le resume et la photo viennent du profil professionnel : le feed
    n'a pas sa propre notion de candidat, il affiche celle que le profil
    expose deja. Un utilisateur qui n'a jamais ouvert son profil n'en a pas
    encore -- l'acces retombe alors sur son seul nom d'utilisateur plutot que
    de casser la page.
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

def _liked_video_ids(user, videos) -> set:
    """Videos deja aimees par le visiteur, en une seule requete.

    Une requete par video ferait autant d'allers-retours que d'elements du
    feed, pour une information que le feed lit sur chacun d'eux.
    """

    if not user.is_authenticated or not videos:
        return set()

    return set(
        Reaction.objects
            .filter(user = user, video__in = videos, reaction = "like")
            .values_list("video_id", flat = True)
    )

def get_video_filepaths(request: HttpRequest) -> list[dict]:
    """Videos televersees par fichier, mises en forme pour `feed.html`.

    Moderation desactivee temporairement : toutes les videos sont affichees
    quel que soit leur `status`.
    """

    files = (
        VideoFile.objects
            .select_related("user", "user__professional_profile")
            .order_by("-id")
    )

    return [
        {
            "id":             f"file-{video.id}",
            "video_url":      video.file.url,
            "poster_url":     "",
            "candidate":      _candidate(video.user),
            "likes_count":    0,
            "comments_count": 0,
            "saves_count":    0,
            "shares_count":   0,
            "liked":          False,
        }
        for video in files
    ]

def get_videos(request: HttpRequest) -> list[dict]:
    """Videos du feed recruteur/admin, mises en forme pour `feed.html`.

    Moderation desactivee temporairement : toutes les videos sont affichees
    quel que soit leur `status`.

    La forme retournee est documentee en tete de `templates/feed.html` : le
    gabarit ne connait ni `VideoLink`, ni `VideoFile`, seulement des elements
    de feed. C'est ce qui permet aux deux sources de cohabiter sans que la
    presentation ait a les distinguer.
    """

    videos = list(
        VideoLink.objects
            .select_related("user", "user__professional_profile")
            .annotate(like_total = Count("reaction", filter = Q(reaction__reaction = "like")))
            .order_by("-id")
    )

    liked = _liked_video_ids(request.user, videos)

    return [
        {
            "id":             vid.id,
            "video_url":      vid.url,
            "poster_url":     "",
            "candidate":      _candidate(vid.user),
            "likes_count":    vid.like_total,
            "comments_count": 0,
            "saves_count":    0,
            "shares_count":   0,
            "liked":          vid.id in liked,
        }
        for vid in videos
    ] + get_video_filepaths(request)

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
            "feed_items": get_videos(request) if role in ("Recruiter", "Admin") else [],
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
