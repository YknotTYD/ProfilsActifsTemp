##admin.py
"""Enregistrement dans l'administration Django.

Complement de l'interface dediee : utile pour l'inspection, le depannage et la
tenue du referentiel de competences.
"""

from django.contrib import admin

from .models import (
    Certification, CertificationSkill, Education, EducationSkill, Language,
    ProfessionalProfile, ProfileContractType, ProfileLink, ProfileSearchSettings,
    ProfileVideo, ProfileVideoSkill, ProfileVisibility, Project, ProjectSkill,
    Skill, SkillAlias, UserLanguage, UserSkill, VideoModerationEvent, WorkExperience,
    WorkExperienceSkill,
)


class UserSkillInline(admin.TabularInline):
    model  = UserSkill
    extra  = 0
    fields = ("skill", "level", "years_experience", "order")


class SkillAliasInline(admin.TabularInline):
    model = SkillAlias
    extra = 0


class ContractTypeInline(admin.TabularInline):
    model = ProfileContractType
    extra = 0


@admin.register(ProfessionalProfile)
class ProfessionalProfileAdmin(admin.ModelAdmin):
    list_display  = ("id", "user", "headline", "professional_field",
                     "availability_status", "visibility", "total_experience_months")
    list_filter   = ("visibility", "availability_status", "professional_field")
    search_fields = ("user__username", "user__first_name", "user__last_name", "headline")
    inlines       = (UserSkillInline, ContractTypeInline)
    readonly_fields = ("total_experience_months",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display  = ("id", "name", "slug", "category")
    list_filter   = ("category",)
    search_fields = ("name", "slug", "aliases__normalized")
    inlines       = (SkillAliasInline,)


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ("profile", "skill", "level", "level_rank", "years_experience")
    list_filter  = ("level",)


@admin.register(WorkExperience)
class WorkExperienceAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "title", "company", "start_date", "end_date", "is_current")
    list_filter  = ("is_current", "contract_type")


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "institution", "degree", "degree_level", "is_current")
    list_filter  = ("degree_level", "is_current")


@admin.register(ProfileVideo)
class ProfileVideoAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "title", "status", "source_type",
                    "is_presentation", "visibility", "published_at")
    list_filter  = ("status", "source_type", "is_presentation", "visibility")
    readonly_fields = ("file_blob", "moderated_at", "moderated_by")


@admin.register(VideoModerationEvent)
class VideoModerationEventAdmin(admin.ModelAdmin):
    """Lecture seule : cet historique n'appartient a personne (voir video.py)."""

    list_display  = ("id", "video", "source", "actor", "old_status", "new_status", "created_at")
    list_filter   = ("source", "old_status", "new_status")
    search_fields = ("video__title", "actor__username")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj = None):
        return False

    def has_delete_permission(self, request, obj = None):
        return False


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display  = ("code", "name")
    search_fields = ("code", "name")


admin.site.register(ProfileVisibility)
admin.site.register(ProfileSearchSettings)
admin.site.register(ProfileContractType)
admin.site.register(ProfileLink)
admin.site.register(SkillAlias)
admin.site.register(Certification)
admin.site.register(CertificationSkill)
admin.site.register(EducationSkill)
admin.site.register(Project)
admin.site.register(ProjectSkill)
admin.site.register(UserLanguage)
admin.site.register(WorkExperienceSkill)
admin.site.register(ProfileVideoSkill)
