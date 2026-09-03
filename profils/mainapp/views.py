from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse
from django.shortcuts           import render, redirect
from django.contrib.auth        import logout as logout_
from .models                    import Role, VideoLink, VideoFile, Reaction

# TODO: deleting
# TODO: support for multiple languages
# TODO: @api_view stuff
# TODO: video -> videolink

def get_video_filepaths(request: HttpRequest) -> list:
    files = list(VideoFile.objects.all())
    return [(f, False, False, 0) for f in files]

def get_videos(request: HttpRequest) -> list[tuple]:

    videos = [vid for vid in VideoLink.objects.all()]
    liked_disliked = [(False, False)] * len(videos)

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
            "videos_ldl":
                get_videos(request)

        }
    )

def register(request: HttpRequest) -> HttpResponse:

    if request.user.is_authenticated:
        return main(request)

    return render(request, "register.html", {
        "error": request.GET.get("error"),
        "username": request.GET.get("username", ""),
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
