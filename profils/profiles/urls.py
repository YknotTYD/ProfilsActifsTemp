##urls.py
"""Routes des profils professionnels.

Les routes d'API suivent la nomenclature de la section 21 ; les routes de
pages restent dans le style plat du projet, comme celles des questionnaires.
"""

from django.urls import path

from . import api, views

urlpatterns = [
    # ------------------------------------------------------------------ #
    # Pages
    # ------------------------------------------------------------------ #
    path("profiles/",              views.search_page,        name = "p_search"),
    path("profiles/edit/",         views.editor_page,        name = "p_editor"),
    path("profile/",               views.my_profile_redirect, name = "p_me"),
    path("profile/<str:username>/", views.profile_page,      name = "p_profile"),

    # ------------------------------------------------------------------ #
    # API - referentiels et vocabulaire
    # ------------------------------------------------------------------ #
    path("api/profiles/meta/",   api.meta),
    path("api/skills/",          api.skills),
    path("api/languages/",       api.languages),

    # ------------------------------------------------------------------ #
    # API - recherche (sections 12 a 14)
    # ------------------------------------------------------------------ #
    path("api/profiles/search/", api.search),

    # ------------------------------------------------------------------ #
    # API - mon profil
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # API - consultation publique
    #
    # Ces deux routes viennent en dernier : `<str:username>` accepterait
    # sinon "me", "search" ou "meta" et masquerait les routes ci-dessus.
    # ------------------------------------------------------------------ #
    path("api/profiles/<str:username>/",        api.profile_detail),
    path("api/profiles/<str:username>/videos/", api.profile_videos),
]
