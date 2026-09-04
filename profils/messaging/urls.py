
from django.urls import path

from . import views

urlpatterns = [
    path("messages/",         views.conversations_page),
    path("messages/start/",   views.start_conversation_view),
    path("messages/<int:pk>/", views.conversation_thread_page),
]
