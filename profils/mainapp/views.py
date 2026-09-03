from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse
from django.shortcuts           import render, redirect
from django.contrib.auth        import logout as logout_
from .models                    import Role, VideoLink, VideoFile, Reaction
from django.utils               import timezone
from . import constants

# TODO: deleting
# TODO: support for multiple languages
# TODO: @api_view stuff
# TODO: video -> videolink

def get_video_filepaths(request: HttpRequest) -> list:
    # `VideoFile` n'a pas encore de champ de moderation (voir models.py) :
    # tant qu'il n'existe pas, un fichier televerse ne doit pas atterrir
    # dans le feed recruteur/admin sans avoir ete verifie -- exactement ce
    # que la moderation des VideoLink existe pour empecher. A rebrancher des
    # que VideoFile aura son propre statut.
    return []

def get_videos(request: HttpResponse) -> list[tuple[int, int]]:
    """Videos du feed recruteur/admin.

    Filtre sur `APPROVED` : une video en attente ou refusee n'a rien a faire
    devant un recruteur (section 1, "une video n'est jamais publique avant
    validation").
    """

    videos = [vid for vid in VideoLink.objects.filter(status = constants.VIDEO_LINK_APPROVED)]
    liked_disliked = [(0, 0)] * len(videos)

    if request.user.is_authenticated:
        reactions = [
            Reaction.objects.filter(user=request.user, video=vid).first() for vid in videos
        ]
        liked_disliked = [
            (r.reaction == "like", r.reaction == "dislike") if r else (False, False)
                for r in reactions
        ]

    videos = [(vid, l, d, 1) for vid, (l, d) in zip(videos, liked_disliked)]
    return videos + get_video_filepaths(request)

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
            "videos_ld": get_videos(request),
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
