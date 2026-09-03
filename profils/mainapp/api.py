from django.http.request        import HttpRequest
from django.http.response       import HttpResponse
from django.shortcuts           import redirect
from django.contrib.auth.models import User
from django.contrib.auth        import authenticate, login as login_
from .models                    import Role, VideoLink, Reaction
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date
from django.utils import timezone
from . import constants
from urllib.parse import urlencode
import json


def _age_on(birth_date, today):
    """Age en annees revolues a la date `today`.

    Un simple `today.year - birth_date.year` compterait un an de trop tant que
    l'anniversaire de l'annee en cours n'est pas encore passe.
    """
    had_birthday_this_year = (today.month, today.day) >= (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (0 if had_birthday_this_year else 1)


def _register_error(message: str, request: HttpRequest):
    query = urlencode({
        "error":      message,
        "username":   request.POST.get("username", ""),
        "birth_date": request.POST.get("birth_date", ""),
    })
    return redirect(f"/register/?{query}")

# TODO: RESTful email on login/logout
# TODO: RESTful login/logout
# TODO: check @api_view
# TODO: actual APIs with json responses

def register(request: HttpRequest) -> HttpResponse:

    required = ("username", "password", "password_confirm", "birth_date", "is_recruiter")
    if any(field not in request.POST for field in required):
        return redirect("/")

    if User.objects.filter(username = request.POST["username"]).first():
        return _register_error("Ce nom d'utilisateur est déjà pris.", request)

    if request.POST["password"] != request.POST["password_confirm"]:
        return _register_error("Les mots de passe ne correspondent pas.", request)

    try:
        validate_password(request.POST["password"])
    except ValidationError as e:
        return _register_error(" ".join(e.messages), request)

    birth_date = parse_date(request.POST["birth_date"])
    if birth_date is None:
        return _register_error("Date de naissance invalide.", request)

    if _age_on(birth_date, timezone.localdate()) < constants.MINIMUM_REGISTRATION_AGE:
        return _register_error(
            f"Vous devez avoir au moins {constants.MINIMUM_REGISTRATION_AGE} ans pour créer un compte.",
            request,
        )

    user = User.objects.create_user(
        request.POST["username"],
        None,
        request.POST["password"]
    )

    role = "Recruiter" if request.POST["is_recruiter"] == "1" else "JobSeeker"
    Role(user = user, role = role, birth_date = birth_date).save()

    auth_user = authenticate(request, username = request.POST["username"], password = request.POST["password"])
    login_(request, auth_user)
    return redirect("/")

def login(request: HttpRequest) -> HttpResponse:

    if "username" in request.POST and "password" in request.POST:
        auth_user = authenticate(
            request,
            username = request.POST["username"],
            password = request.POST["password"]
        )
        if auth_user is None:
            return redirect("/login")
        login_(request, auth_user)
    else:
        return redirect("/login")

    return redirect("/")

def video_upload(request: HttpRequest) -> HttpResponse:

    if request.user.is_authenticated and (url := request.POST.get("url")):

        url = "https://" + url.removeprefix("https://")

        if url.startswith("https://www.youtube.com/watch?v="):
            url = url.removeprefix("https://www.youtube.com/watch?v=")
            url = "https://www.youtube.com/embed/" + url

        VideoLink.objects.create(user = request.user, url = url).save()

    return redirect(request.GET.get("camefrom", "/"))

def react(request: HttpRequest) -> HttpResponse:

    if not request.user.is_authenticated:
        return HttpResponse(status = 401)

    body = json.loads(request.body)

    if (
        "video_id" not in body or
        "reaction" not in body or
        body["reaction"] not in constants.REACTIONS
    ): # invalid data
        return HttpResponse(status = 404)

    vid = VideoLink.objects.filter(id = body["video_id"]).first() # take a guess

    if vid is None:
        return HttpResponse(status = 400)

    prev_reaction = Reaction.objects.filter(user = request.user, video = vid).first()

    if prev_reaction is None or prev_reaction.reaction != body["reaction"]:
        Reaction.objects.create(
            user     = request.user,
            video    = vid,
            reaction = body["reaction"]
        ).save()

    if prev_reaction:
        prev_reaction.delete()

    return HttpResponse(status = 200)
