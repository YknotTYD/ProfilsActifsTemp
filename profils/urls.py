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
from django.urls    import path
from .mainapp       import views
from .mainapp       import api

urlpatterns = [
    path('admin/',            admin.site.urls),
    path("",                  views.main),
    path("register/",         views.register),
    path("login/",            views.login),
    path("logout/",           views.logout),
    path("api/register/",     api.register),
    path("api/login/",        api.login),
    path("api/upload/video/", api.video_upload),
    path("api/react/",        api.react)
]
