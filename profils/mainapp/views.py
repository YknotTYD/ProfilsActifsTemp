from django.shortcuts     import render
from django.http.request  import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts     import render

# Create your views here.

def test_view(request: HttpRequest) -> HttpResponse:
    return render(request, "test.html")
