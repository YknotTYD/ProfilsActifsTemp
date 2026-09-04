"""Pages du systeme de questionnaires.

Les templates ne portent aucune logique metier : ils recoivent l'etat initial et
dialoguent ensuite avec l'API. Toute decision d'acces est reprise cote serveur
avant le rendu.
"""

from django.http      import Http404
from django.shortcuts import get_object_or_404, redirect, render

from . import constants as c
from .access      import can_see
from .models      import Questionnaire, QuestionnaireResult
from .permissions import admin_capabilities, can_manage, has_perm, is_questionnaire_admin
from .serializers import public_questionnaire, result_payload
from .services    import current_attempt

def _login_required(request):
    return None if request.user.is_authenticated else redirect("/login/")

def catalog(request):
    """Liste des questionnaires accessibles a l'utilisateur."""
    if redirect_to := _login_required(request):
        return redirect_to

    from .access import visible_questionnaires

    questionnaires = visible_questionnaires(
        request.user,
        Questionnaire.objects.exclude(status = c.STATUS_DRAFT).select_related("current_version"),
    )
    return render(request, "questionnaires/catalog.html", {
        "questionnaires": [public_questionnaire(q, request.user) for q in questionnaires],
        "can_manage":     can_manage(request.user),
    })

def run(request, pk):
    """Interface de passage d'un questionnaire."""
    if redirect_to := _login_required(request):
        return redirect_to

    questionnaire = get_object_or_404(Questionnaire.objects.prefetch_related("access_rules"), pk = pk)
    if not can_see(questionnaire, request.user):
        raise Http404

    test    = request.GET.get("test") in ("1", "true", "yes")
    attempt = current_attempt(questionnaire, request.user, test = test)

    return render(request, "questionnaires/run.html", {
        "questionnaire": questionnaire,
        "card":          public_questionnaire(questionnaire, request.user),
        "test_mode":     test and (is_questionnaire_admin(request.user) or has_perm(request.user, c.PERM_TEST)),
        "has_attempt":   attempt is not None,
        "can_manage":    can_manage(request.user),
    })

def results(request, pk):
    """Historique des resultats de l'utilisateur pour un questionnaire."""
    if redirect_to := _login_required(request):
        return redirect_to

    questionnaire = get_object_or_404(Questionnaire, pk = pk)
    rows = QuestionnaireResult.objects.filter(
        questionnaire = questionnaire, user = request.user, is_test = False,
    ).select_related("attempt", "version", "questionnaire")

    return render(request, "questionnaires/results.html", {
        "questionnaire": questionnaire,
        "results":       [result_payload(r, request.user) for r in rows],
        "can_manage":    can_manage(request.user),
    })

def _admin_required(request):
    if not request.user.is_authenticated:
        return redirect("/login/")
    if not can_manage(request.user):
        raise Http404
    return None

def manage(request):
    if response := _admin_required(request):
        return response
    return render(request, "questionnaires/manage.html", {
        "capabilities": admin_capabilities(request.user),
        "statuses":     dict(c.QUESTIONNAIRE_STATUSES),
    })

def editor(request, pk):
    if response := _admin_required(request):
        return response
    questionnaire = get_object_or_404(Questionnaire, pk = pk)
    return render(request, "questionnaires/editor.html", {
        "questionnaire": questionnaire,
        "capabilities":  admin_capabilities(request.user),
    })

def versions(request, pk):
    if response := _admin_required(request):
        return response
    questionnaire = get_object_or_404(Questionnaire, pk = pk)
    return render(request, "questionnaires/versions.html", {
        "questionnaire": questionnaire,
        "capabilities":  admin_capabilities(request.user),
    })

def attempts(request, pk):
    if response := _admin_required(request):
        return response
    questionnaire = get_object_or_404(Questionnaire, pk = pk)
    return render(request, "questionnaires/attempts.html", {
        "questionnaire": questionnaire,
        "capabilities":  admin_capabilities(request.user),
    })

def preview(request, pk, number):
    """Previsualisation d'une version, telle que la verra l'utilisateur."""
    if response := _admin_required(request):
        return response
    questionnaire = get_object_or_404(Questionnaire, pk = pk)
    return render(request, "questionnaires/preview.html", {
        "questionnaire": questionnaire,
        "version_number": number,
    })
