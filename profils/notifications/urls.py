##urls.py

from django.urls import path

from . import api

urlpatterns = [
    path("api/notifications/",               api.list_notifications),
    path("api/notifications/unread-count/",  api.unread_count),
    path("api/notifications/read-all/",      api.mark_all_read),
    path("api/notifications/<int:pk>/read/", api.mark_read),
]
