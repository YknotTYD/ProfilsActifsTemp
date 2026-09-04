"""Routes des profils professionnels.

Les routes d'API suivent la nomenclature de la section 21 ; les routes de
pages restent dans le style plat du projet, comme celles des questionnaires.
"""

from django.urls import path

from . import api, views

urlpatterns = [
    path("profiles/",              views.search_page,        name = "p_search"),
    path("profiles/edit/",         views.editor_page,        name = "p_editor"),
    path("profiles/me/video/",     views.my_video_page,      name = "p_my_video"),
    path("profile/",               views.my_profile_redirect, name = "p_me"),
    path("profile/<str:username>/", views.profile_page,      name = "p_profile"),
    path("profiles/admin/videos/", views.admin_videos_page,  name = "p_admin_videos"),

    path("api/profiles/meta/",   api.meta),
    path("api/skills/",          api.skills),
    path("api/languages/",       api.languages),

    path("api/profiles/search/", api.search),

    path("api/profiles/me/",          api.me),
    path("api/profiles/me/privacy/",  api.me_privacy),
    path("api/profiles/me/links/",    api.me_links),

    path("api/profiles/me/skills/",                  api.me_skills),
    path("api/profiles/me/skills/reorder/",          api.me_skills_reorder),
    path("api/profiles/me/skills/<int:skill_id>/",   api.me_skill_item),

    path("api/profiles/me/experiences/",             api.me_experiences),
    path("api/profiles/me/experiences/<int:pk>/",    api.me_experience_item),

    path("api/profiles/me/education/",               api.me_education),
    path("api/profiles/me/education/<int:pk>/",      api.me_education_item),

    path("api/profiles/me/certifications/",          api.me_certifications),
    path("api/profiles/me/certifications/<int:pk>/", api.me_certification_item),

    path("api/profiles/me/projects/",                api.me_projects),
    path("api/profiles/me/projects/<int:pk>/",       api.me_project_item),

    path("api/profiles/me/languages/",               api.me_languages),
    path("api/profiles/me/languages/<int:pk>/",      api.me_language_item),

    path("api/profiles/me/videos/",                  api.me_videos),
    path("api/profiles/me/videos/<int:pk>/",         api.me_video_item),
    path("api/profiles/me/videos/<int:pk>/publish/",  api.me_video_publish),
    path("api/profiles/me/videos/<int:pk>/resubmit/", api.me_video_resubmit),

    path("api/profiles/videos/<int:pk>/view/",  api.video_view),
    path("api/profiles/videos/<int:pk>/react/", api.video_react),

    path("api/profiles/admin/videos/pending/",        api.admin_video_queue),
    path("api/profiles/admin/videos/rejected/",       api.admin_video_rejections),
    path("api/profiles/admin/videos/<int:pk>/approve/", api.admin_video_approve),
    path("api/profiles/admin/videos/<int:pk>/reject/",  api.admin_video_reject),
    path("api/profiles/admin/videos/<int:pk>/history/", api.admin_video_history),

    path("api/profiles/<str:username>/",        api.profile_detail),
    path("api/profiles/<str:username>/videos/", api.profile_videos),
]
