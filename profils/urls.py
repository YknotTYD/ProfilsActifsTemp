"""
URL configuration for profils project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls    import path, re_path, include
from .mainapp       import views
from .mainapp       import api
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.shortcuts import render

def swagger_ui(request):
    return render(request, 'swagger.html')

# Le feed vertical a laisse des adresses derriere lui : elles ont circule par
# mail et par lien partage, et doivent mener a la grille plutot qu'a une 404.
# Redirection permanente (301) : ces adresses ne reviendront pas, autant que
# les navigateurs et les moteurs de recherche l'apprennent une bonne fois.
# `/?` accepte l'adresse avec ou sans slash final, en une seule etape ;
# `query_string` conserve ce qui suivait (`?page=2` d'un vieux signet).
_old_feed = RedirectView.as_view(url = "/", permanent = True, query_string = True)

urlpatterns = [
    path('admin/',            admin.site.urls),
    path("",                  views.main),

    re_path(r"^feed/?$",             _old_feed),
    re_path(r"^api/feed/?$",         _old_feed),
    re_path(r"^api/videos/feed/?$",  _old_feed),

    path("quiz/",             views.quiz),
    path("cgu/",              views.cgu),
    path("accessibilite/",    views.accessibilite),
    path("register/",         views.register),
    path("login/",            views.login),
    path("logout/",           views.logout),
    path("api/register/",     api.register),
    path("api/login/",        api.login),
    path("api/upload/video/", api.video_upload),
    path("api/delete/video/", api.video_delete),
    path("api/react/",        api.react),
    path("health/",           views.health),
    path("",                  include("profils.questionnaires.urls")),
    path("",                  include("profils.profiles.urls")),
    path("",                  include("profils.notifications.urls")),
    path("",                  include("profils.messaging.urls")),
    path('api/docs/', swagger_ui, name='swagger-ui'),
]

urlpatterns += static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)
