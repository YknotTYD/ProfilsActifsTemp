from django.shortcuts     import render
from django.http.request  import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts     import render

# Create your views here.

def main(request: HttpRequest) -> HttpResponse:
    return render(request, "main.html")

def register(request: HttpRequest) -> HttpResponse:
    return render(request, "register.html")
