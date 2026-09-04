"""Enregistrement dans l'administration Django.

Complement de l'interface dediee : utile pour l'inspection et le depannage.
"""

from django.contrib import admin

from .models import (
    AuditLog, Badge, Question, QuestionOption, Questionnaire,
    QuestionnaireAccessRule, QuestionnaireAttempt, QuestionnaireResult,
    QuestionnaireVersion, UserAnswer, UserBadge,
)

class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0

class QuestionInline(admin.TabularInline):
    model  = Question
    extra  = 0
    fields = ("order", "text", "type", "required")

@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display  = ("id", "title", "status", "current_version", "updated_at")
    list_filter   = ("status",)
    search_fields = ("title", "slug")

@admin.register(QuestionnaireVersion)
class QuestionnaireVersionAdmin(admin.ModelAdmin):
    list_display = ("questionnaire", "version_number", "status", "created_at", "published_at")
    list_filter  = ("status",)
    inlines      = (QuestionInline,)

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "version", "order", "type", "required")
    list_filter  = ("type", "required")
    inlines      = (QuestionOptionInline,)

@admin.register(QuestionnaireAttempt)
class QuestionnaireAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "questionnaire", "version", "status", "is_test", "percentage")
    list_filter  = ("status", "is_test")

@admin.register(QuestionnaireResult)
class QuestionnaireResultAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "questionnaire", "version", "percentage", "passed", "is_test")
    list_filter  = ("passed", "is_test")

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "object_type", "object_id")
    list_filter  = ("action",)

admin.site.register(QuestionOption)
admin.site.register(QuestionnaireAccessRule)
admin.site.register(UserAnswer)
admin.site.register(Badge)
admin.site.register(UserBadge)
