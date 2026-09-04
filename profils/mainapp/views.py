from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse, JsonResponse, Http404
from django.shortcuts           import render, redirect
from django.contrib.auth        import logout as logout_
from .models                    import Role
from django.utils               import timezone
from . import constants
from django.db import connections
from django.db.utils import OperationalError

# TODO: deleting
# TODO: support for multiple languages
# TODO: @api_view stuff

def get_videos(request: HttpRequest) -> list[dict]:
    """Videos du feed recruteur/admin.

    Sert desormais une seule source, `profiles.ProfileVideo` publiees et
    visibles du spectateur : l'upload video est unifie sur la pile moderee,
    donc une video envoyee par un candidat apparait ici des sa publication.
    L'ancien `mainapp.VideoLink` n'alimente plus le feed.
    """
    from profils.profiles.feed import dashboard_feed_items

    return dashboard_feed_items(request.user)

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
            # section 1 : "l'utilisateur doit pouvoir consulter a tout moment
            # le statut de ses videos". Uniquement pour un demandeur d'emploi :
            # `get_profile` cree un profil professionnel s'il n'en a pas
            # encore, ce qu'on ne veut surtout pas declencher pour un
            # recruteur ou un administrateur de passage sur la page d'accueil.
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
        # 29 fevrier tombant sur une annee non bissextile 18 ans plus tot
        max_birth_date = today.replace(year = today.year - constants.MINIMUM_REGISTRATION_AGE, day = 28)

    return render(request, "register.html", {
        "error": request.GET.get("error"),
        "username": request.GET.get("username", ""),
        "birth_date": request.GET.get("birth_date", ""),
        # date la plus recente acceptable : au-dela, l'utilisateur n'a pas
        # encore l'age minimum aujourd'hui — sert de borne au selecteur de
        # date cote navigateur, en plus du controle fait par l'API.
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
