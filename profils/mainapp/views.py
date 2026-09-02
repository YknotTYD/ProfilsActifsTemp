from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse
from django.shortcuts           import render, redirect
from django.contrib.auth        import logout as logout_
from .models                    import Role, VideoLink, Reaction

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

def certification(request: HttpRequest) -> HttpResponse:
    return render(request, "certification.html")

def cgu(request: HttpRequest) -> HttpResponse:
    return render(request, "cgu.html")
    
