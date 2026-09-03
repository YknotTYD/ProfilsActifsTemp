from django.http.request        import HttpRequest
from django.http.response       import HttpResponse, JsonResponse
from django.shortcuts           import redirect
from django.contrib.auth.models import User
from django.contrib.auth        import authenticate, login as login_
from .models                    import Role, VideoLink, Reaction, VideoFile
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from . import constants
from urllib.parse import urlencode
import json

# TODO: RESTful email on login/logout
# TODO: RESTful login/logout
# TODO: check @api_view
# TODO: actual APIs with json responses

def register(request: HttpRequest) -> HttpResponse:

    if "username" not in request.POST or "password" not in request.POST or "is_recruiter" not in request.POST:
        return redirect("/")

    if User.objects.filter(username = request.POST["username"]).first():
        query = urlencode({"error": "Ce nom d'utilisateur est déjà pris.", "username": request.POST["username"]})
        return redirect(f"/register/?{query}")

    try:
        validate_password(request.POST["password"])
    except ValidationError as e:
        query = urlencode({"error": " ".join(e.messages), "username": request.POST["username"]})
        return redirect(f"/register/?{query}")

    user = User.objects.create_user(
        request.POST["username"],
        None,
        request.POST["password"]
    )

    if request.POST["is_recruiter"] == "1":
        Role(user = user, role = "Recruiter").save()
    else:
        Role(user = user, role = "JobSeeker").save()

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

def videofile_upload(request: HttpRequest) -> HttpResponse:

    file = request.FILES.get('file')

    if not file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    path = default_storage.save(constants.VIDEOFILE_STORAGE_PATH + file.name, file)
    video = VideoFile(user=request.user, file=path)
    video.save()

    return JsonResponse({'url': f"'{constants.VIDEOFILE_STORAGE_PATH}{file.name}'"})
