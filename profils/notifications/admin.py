from django.contrib import admin

from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ("id", "recipient", "type", "read_at", "created_at")
    list_filter   = ("type",)
    search_fields = ("recipient__username",)
