from django.http.request        import HttpRequest
from django.http.response       import HttpResponse, JsonResponse
from django.shortcuts           import redirect
from django.contrib.auth.models import User
from django.contrib.auth        import authenticate, login as login_
from .models                    import Role, VideoLink, Reaction, VideoFile
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
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

def video_delete(request: HttpRequest) -> HttpResponse:
    """Suppression par son proprietaire (section 1 : "l'utilisateur peut
    supprimer sa video"). Un administrateur la supprime depuis /admin/.
    """

    if request.user.is_authenticated and (video_id := request.POST.get("video_id")):
        VideoLink.objects.filter(id = video_id, user = request.user).delete()

    return redirect(request.GET.get("camefrom", "/"))

def react(request: HttpRequest) -> HttpResponse:

    if not request.user.is_authenticated:
        return HttpResponse(status = 401)

    body = json.loads(request.body)

    if (
        "video_id" not in body or
        "reaction" not in body or
        body["reaction"] not in constants.REACTIONS
    ):
        return HttpResponse(status = 404)

    vid = VideoLink.objects.filter(id = body["video_id"]).first()

    if vid is None:
        return HttpResponse(status = 400)

    prev_reaction = Reaction.objects.filter(user = request.user, video = vid).first()
    is_new_reaction = prev_reaction is None or prev_reaction.reaction != body["reaction"]

    if is_new_reaction:
        Reaction.objects.create(
            user     = request.user,
            video    = vid,
            reaction = body["reaction"]
        ).save()

    if prev_reaction:
        prev_reaction.delete()

    if is_new_reaction and vid.user_id != request.user.id:
        from profils.notifications import services as notifications
        from profils.notifications import types as notification_types

        notif_type = (
            notification_types.VIDEO_LIKED if body["reaction"] == "like"
            else notification_types.VIDEO_DISLIKED
        )
        notifications.notify(
            vid.user, notif_type, target = vid,
            url = f"/profile/{vid.user.username}/",
        )

    return HttpResponse(status = 200)

def videofile_upload(request: HttpRequest) -> HttpResponse:

    file = request.FILES.get('file')

    if not file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    path = default_storage.save(constants.VIDEOFILE_STORAGE_PATH + file.name, file)
    video = VideoFile(user=request.user, file=path)
    video.save()

    return JsonResponse({'url': f"'{constants.VIDEOFILE_STORAGE_PATH}{file.name}'"})
