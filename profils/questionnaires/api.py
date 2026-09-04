"""API utilisateur : passage d'un questionnaire.

Rien de ce que le client envoie n'est cru sur parole. La version utilisee, le
numero de tentative, la visibilite des questions, le verrouillage des reponses
et le score sont systematiquement determines cote serveur.
"""

from django.contrib.auth.models import User
from django.shortcuts           import get_object_or_404

from . import constants as c
from .access      import AccessDenied, result_visibility, visible_questionnaires
from .badges      import user_badges
from .http        import api, body, fail, get_bool, get_int, ok
from .models      import Questionnaire, QuestionnaireAttempt, QuestionnaireResult
from .permissions import is_questionnaire_admin
from .serializers import (
    attempt_summary, public_questionnaire, result_payload, runner_state,
)
from .services    import (
    abandon_attempt, clear_answer, current_attempt, expire_if_needed,
    finish_attempt, save_answer, start_attempt,
)
from .snapshots   import attempt_transcript

@api(("GET",))
def available(request):
    """Questionnaires que l'utilisateur a le droit de voir."""
    questionnaires = visible_questionnaires(
        request.user,
        Questionnaire.objects.exclude(status = c.STATUS_DRAFT).select_related("current_version"),
    )
    return ok({"questionnaires": [public_questionnaire(q, request.user) for q in questionnaires]})

def _questionnaire(pk) -> Questionnaire:
    return get_object_or_404(Questionnaire.objects.prefetch_related("access_rules"), pk = pk)

@api(("POST",))
def start(request, pk):
    """Demarre (ou reprend) une tentative."""
    questionnaire = _questionnaire(pk)
    payload       = body(request)
    test          = get_bool(payload, "test", False)

    attempt = start_attempt(questionnaire, request.user, test = test)
    return ok(runner_state(attempt), status = 201)

@api(("GET",))
def current(request, pk):
    """Etat de la tentative en cours : c'est le point de reprise."""
    questionnaire = _questionnaire(pk)
    test          = request.GET.get("test") in ("1", "true", "yes")

    attempt = current_attempt(questionnaire, request.user, test = test)
    if attempt is None:
        last = QuestionnaireAttempt.objects.filter(
            questionnaire = questionnaire, user = request.user, is_test = test,
        ).order_by("-started_at").first()
        return ok({
            "attempt":   None,
            "last_attempt": attempt_summary(last) if last else None,
            "can_start": public_questionnaire(questionnaire, request.user)["can_start"],
        })
    return ok(runner_state(attempt))

@api(("POST",))
def answer(request, pk):
    """Sauvegarde immediate d'une reponse (section 11).

    Corps attendu :
        {"question_id": 12, "value": ..., "client_sequence": 7,
         "idempotency_key": "..."}
    """
    questionnaire = _questionnaire(pk)
    payload       = body(request)
    test          = get_bool(payload, "test", False)

    attempt = current_attempt(questionnaire, request.user, test = test)
    if attempt is None:
        return fail("aucune tentative en cours", "no_attempt", 409)

    state = save_answer(
        attempt,
        get_int(payload, "question_id"),
        payload.get("value"),
        client_sequence = get_int(payload, "client_sequence", required = False, default = None),
        idempotency_key = str(payload.get("idempotency_key", ""))[:64],
    )
    state["visible_question_ids"] = state["progress"]["visible"]
    return ok(state)

@api(("POST",))
def clear(request, pk):
    """Efface une reponse."""
    questionnaire = _questionnaire(pk)
    payload       = body(request)

    attempt = current_attempt(questionnaire, request.user, test = get_bool(payload, "test", False))
    if attempt is None:
        return fail("aucune tentative en cours", "no_attempt", 409)

    return ok(clear_answer(attempt, get_int(payload, "question_id")))

@api(("GET",))
def state(request, pk):
    """Etat serveur complet, utilise pour la resynchronisation apres coupure."""
    questionnaire = _questionnaire(pk)
    test          = request.GET.get("test") in ("1", "true", "yes")

    attempt = current_attempt(questionnaire, request.user, test = test)
    if attempt is None:
        return fail("aucune tentative en cours", "no_attempt", 409)
    return ok(runner_state(attempt))

@api(("POST",))
def finish(request, pk):
    """Termine la tentative, calcule et historise le resultat."""
    questionnaire = _questionnaire(pk)
    payload       = body(request)

    attempt = current_attempt(questionnaire, request.user, test = get_bool(payload, "test", False))
    if attempt is None:
        return fail("aucune tentative en cours", "no_attempt", 409)

    result = finish_attempt(attempt, force = get_bool(payload, "force", False))
    return ok({"result": result_payload(result, request.user)})

@api(("POST",))
def abandon(request, pk):
    questionnaire = _questionnaire(pk)
    payload       = body(request)

    attempt = current_attempt(questionnaire, request.user, test = get_bool(payload, "test", False))
    if attempt is None:
        return fail("aucune tentative en cours", "no_attempt", 409)
    return ok(attempt_summary(abandon_attempt(attempt)))

@api(("GET",))
def my_results(request, pk):
    """Historique complet des resultats de l'utilisateur courant."""
    questionnaire = _questionnaire(pk)
    results = QuestionnaireResult.objects.filter(
        questionnaire = questionnaire, user = request.user,
    ).select_related("attempt", "version", "questionnaire")

    if request.GET.get("include_test") not in ("1", "true", "yes"):
        results = results.filter(is_test = False)

    return ok({
        "results":    [result_payload(r, request.user) for r in results],
        "visibility": result_visibility(questionnaire, request.user),
    })

@api(("GET",))
def attempt_detail(request, attempt_id):
    """Detail d'une tentative : la sienne, ou n'importe laquelle pour un admin."""
    attempt = get_object_or_404(
        QuestionnaireAttempt.objects.select_related("questionnaire", "version", "user"),
        pk = attempt_id,
    )
    if attempt.user_id != request.user.id and not is_questionnaire_admin(request.user):
        raise AccessDenied("tentative d'un autre utilisateur", "forbidden")

    expire_if_needed(attempt)
    payload = {"attempt": attempt_summary(attempt, for_admin = is_questionnaire_admin(request.user))}

    result = QuestionnaireResult.objects.filter(attempt = attempt).first()
    if result is not None:
        payload["result"] = result_payload(result, request.user)
    if request.GET.get("transcript") in ("1", "true", "yes"):
        payload["transcript"] = attempt_transcript(attempt)
    return ok(payload)

@api(("GET",))
def badges(request, user_id):
    """GET /api/users/:userId/badges"""
    if int(user_id) != request.user.id and not is_questionnaire_admin(request.user):
        raise AccessDenied("badges d'un autre utilisateur", "forbidden")

    user = get_object_or_404(User, pk = user_id)
    return ok({"user": user.username, "badges": user_badges(user)})
