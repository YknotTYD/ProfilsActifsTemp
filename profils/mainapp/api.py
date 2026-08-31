from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse
from django.shortcuts           import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth        import authenticate, login as login_

def register(request: HttpRequest) -> HttpResponse:

    if "username" in request.POST and "password" in request.POST:

        if User.objects.filter(username = request.POST["username"]).first():
            return redirect("/login")

        user = User.objects.create_user(
            request.POST["username"],
            None,
            request.POST["password"]
        )
        user.save()
        auth_user = authenticate(request, username = request.POST["username"], password = request.POST["password"])
        login_(request, auth_user)

    return redirect("/")

def login(request: HttpRequest) -> HttpResponse:

    if "username" in request.POST and "password" in request.POST:
        auth_user = authenticate(request, username = request.POST["username"], password = request.POST["password"])
        if auth_user is None:
            return redirect("/login")
        login_(request, auth_user)
    else:
        return redirect("/login")

    return redirect("/")
