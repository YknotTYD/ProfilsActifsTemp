##urls.py
"""Routes du systeme de questionnaires.

Les routes d'API suivent la nomenclature de la specification ; les routes de
pages restent dans le style plat du projet.
"""

from django.urls import path

from . import api, api_admin, views

urlpatterns = [
    # ------------------------------------------------------------------ #
    # Pages
    # ------------------------------------------------------------------ #
    path("questionnaires/",                          views.catalog,       name = "q_catalog"),
    path("questionnaires/<int:pk>/",                 views.run,           name = "q_run"),
    path("questionnaires/<int:pk>/results/",         views.results,       name = "q_results"),
    path("questionnaires/manage/",                   views.manage,        name = "q_manage"),
    path("questionnaires/manage/<int:pk>/",          views.editor,        name = "q_editor"),
    path("questionnaires/manage/<int:pk>/versions/", views.versions,      name = "q_versions"),
    path("questionnaires/manage/<int:pk>/attempts/", views.attempts,      name = "q_attempts"),
    path("questionnaires/manage/<int:pk>/preview/<int:number>/", views.preview, name = "q_preview"),

    # ------------------------------------------------------------------ #
    # API - administration
    # ------------------------------------------------------------------ #
    path("api/questionnaires/",                      api_admin.collection),
    path("api/questionnaires/types/",                api_admin.question_types),
    path("api/questionnaires/<int:pk>/",             api_admin.item),
    path("api/questionnaires/<int:pk>/duplicate/",   api_admin.duplicate),
    path("api/questionnaires/<int:pk>/archive/",     api_admin.archive),
    path("api/questionnaires/<int:pk>/disable/",     api_admin.disable),
    path("api/questionnaires/<int:pk>/reactivate/",  api_admin.reactivate),
    path("api/questionnaires/<int:pk>/invalidate/",  api_admin.invalidate),
    path("api/questionnaires/<int:pk>/access/",      api_admin.access),
    path("api/questionnaires/<int:pk>/attempts/",    api_admin.attempts),
    path("api/questionnaires/<int:pk>/attempts/<int:attempt_id>/transcript/",
         api_admin.attempt_transcript_view),
    path("api/questionnaires/<int:pk>/attempts/<int:attempt_id>/invalidate/",
         api_admin.attempt_invalidate),
    path("api/questionnaires/<int:pk>/audit/",       api_admin.audit),
    path("api/questionnaires/<int:pk>/statistics/",  api_admin.statistics),

    # versions
    path("api/questionnaires/<int:pk>/versions/",                api_admin.versions),
    path("api/questionnaires/<int:pk>/versions/compare/",        api_admin.version_compare),
    path("api/questionnaires/<int:pk>/versions/editable/",       api_admin.version_editable),
    path("api/questionnaires/<int:pk>/versions/<int:number>/",   api_admin.version_item),
    path("api/questionnaires/<int:pk>/versions/<int:number>/publish/",    api_admin.version_publish),
    path("api/questionnaires/<int:pk>/versions/<int:number>/test/",       api_admin.version_test),
    path("api/questionnaires/<int:pk>/versions/<int:number>/invalidate/", api_admin.version_invalidate),
    path("api/questionnaires/<int:pk>/versions/<int:number>/restore/",    api_admin.version_restore),
    path("api/questionnaires/<int:pk>/versions/<int:number>/preview/",    api_admin.version_preview),

    # questions et options
    path("api/questionnaires/<int:pk>/versions/<int:number>/questions/",
         api_admin.questions),
    path("api/questionnaires/<int:pk>/versions/<int:number>/questions/reorder/",
         api_admin.questions_reorder),
    path("api/questionnaires/<int:pk>/versions/<int:number>/questions/<int:question_id>/",
         api_admin.question_item),
    path("api/questionnaires/<int:pk>/versions/<int:number>/questions/<int:question_id>/options/",
         api_admin.options),
    path("api/questionnaires/<int:pk>/versions/<int:number>/questions/<int:question_id>/options/<int:option_id>/",
         api_admin.option_item),

    # badges (administration)
    path("api/badges/", api_admin.badge_collection),

    # ------------------------------------------------------------------ #
    # API - utilisation
    # ------------------------------------------------------------------ #
    path("api/questionnaires/available/",            api.available),
    path("api/questionnaires/<int:pk>/start/",       api.start),
    path("api/questionnaires/<int:pk>/current/",     api.current),
    path("api/questionnaires/<int:pk>/state/",       api.state),
    path("api/questionnaires/<int:pk>/answers/",     api.answer),
    path("api/questionnaires/<int:pk>/answers/clear/", api.clear),
    path("api/questionnaires/<int:pk>/finish/",      api.finish),
    path("api/questionnaires/<int:pk>/abandon/",     api.abandon),
    path("api/questionnaires/<int:pk>/results/me/",  api.my_results),
    path("api/questionnaires/<int:pk>/results/",     api_admin.results),
    path("api/attempts/<int:attempt_id>/",           api.attempt_detail),

    # badges (section 21)
    path("api/users/<int:user_id>/badges/",          api.badges),
]
