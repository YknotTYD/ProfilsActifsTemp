from django.shortcuts     import render
from django.http.request  import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts     import render

# Create your views here.

def main(request: HttpRequest) -> HttpResponse:

    if not request.user.is_authenticated:
        return register(request)

    return render(request, "main.html", {"user": request.user})

def register(request: HttpRequest) -> HttpResponse:

    if request.user.is_authenticated:
        return main(request)

    return render(request, "register.html")
