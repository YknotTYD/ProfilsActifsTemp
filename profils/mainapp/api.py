from django.shortcuts           import render
from django.http.request        import HttpRequest
from django.http.response       import HttpResponse
from django.shortcuts           import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth        import authenticate, login

def register(request: HttpRequest) -> HttpResponse:

    if "username" in request.POST and "password" in request.POST:
        if User.objects.get(username = request.POST["username"]):
            pass
        user = User.objects.create_user(
            request.POST["username"],
            None,
            request.POST["password"]
        )
        user.save()
        auth_user = authenticate(request, username = request.POST["username"], password = request.POST["password"])
        login(request, auth_user)


    return redirect("/")
