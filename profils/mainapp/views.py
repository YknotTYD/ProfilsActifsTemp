from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse
from django.shortcuts           import render, redirect
from django.contrib.auth        import logout as logout_
from django.utils               import timezone
from .models                    import Role, VideoLink, Reaction
from . import constants

# TODO: deleting
# TODO: support for multiple languages
# TODO: @api_view stuff


def get_videos(request: HttpResponse) -> list[tuple[int, int]]:

    videos = [vid for vid in VideoLink.objects.all()]
    liked_disliked = [(0, 0)] * len(videos)

    if request.user.is_authenticated:        

        reactions = [
            Reaction.objects.filter(user = request.user, video = vid).first() for vid in videos
        ]
        liked_disliked = [
            (r.reaction == "like", r.reaction == "dislike") if r else (False, False)
                for r in reactions
        ]

    videos = [(vid, l, d) for vid, (l, d) in zip(videos, liked_disliked)]
    return videos


def main(request: HttpRequest) -> HttpResponse:

    return render(
        request,
        "main.html",
        {
            "user":
                request.user,
            "role":
                str(Role.objects.filter(user = request.user).first())
                    if request.user.is_authenticated else "None",
            "videos_ld":
                get_videos(request)

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
    
