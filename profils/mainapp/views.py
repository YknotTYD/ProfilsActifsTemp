from django.shortcuts     import render
from django.http.request  import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts     import render, redirect
from django.contrib.auth  import logout as logout_

def main(request: HttpRequest) -> HttpResponse:
    return render(request, "main.html", {"user": request.user})

def register(request: HttpRequest) -> HttpResponse:

    if request.user.is_authenticated:
        return main(request)

    return render(request, "register.html")

def login(request: HttpRequest) -> HttpResponse:

    if request.user.is_authenticated:
        return main(request)

    return render(request, "login.html")

def logout(request: HttpRequest) -> HttpResponse:

    if not request.user.is_authenticated:
        return main(request)

    logout_(request)
    return redirect("/")
