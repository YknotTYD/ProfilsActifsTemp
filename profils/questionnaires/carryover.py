"""Report des reponses d'une version a la suivante.

Quand une nouvelle version est publiee, les participants ne repartent pas de
zero. Deux cas, traites differemment parce qu'ils n'ont pas la meme valeur :

  * **tentative en cours** - elle est deplacee telle quelle sur la nouvelle
    version. Le participant garde ses reponses et decouvre les nouvelles
    questions comme des questions sans reponse. Rien n'est fige, il n'y a donc
    rien a preserver.

  * **tentative terminee** - elle n'est jamais touchee : son resultat est
    historise et doit le rester. Une *nouvelle* tentative est creee sur la
    nouvelle version, prealablement remplie avec ses anciennes reponses. Si
    rien ne manque, elle est aussitot cloturee et un nouveau resultat est
    calcule a cote de l'ancien. Si de nouvelles questions sont apparues, elle
    reste en attente : le participant les completera a sa prochaine visite.

Les reponses sont appariees par cle stable, jamais par identifiant : un libelle
modifie ou une question deplacee ne casse pas le report. Une reponse dont la
question a disparu, ou qui ne satisfait plus la configuration de la nouvelle
version, est abandonnee et comptee dans le rapport.
"""

from django.db import transaction

from . import constants as c
from .auditing       import log
from .conditions     import compute_visible
from .models         import QuestionnaireAttempt, UserAnswer, UserAnswerSelection
from .question_types import AnswerError
from .snapshots      import answer_snapshot

def _previous_attempts(questionnaire, version):
    """Tentatives reelles rattachees a une version anterieure."""
    return (
        QuestionnaireAttempt.objects
        .filter(questionnaire = questionnaire, is_test = False)
        .exclude(version = version)
        .exclude(status__in = (c.ATTEMPT_INVALIDATED, c.ATTEMPT_EXPIRED))
        .select_related("user", "version")
        .order_by("user_id", "-started_at")
    )

def _latest_per_user(attempts) -> dict:
    """Derniere tentative de chaque participant, ordre deja decroissant."""
    latest = {}
    for attempt in attempts:
        latest.setdefault(attempt.user_id, attempt)
    return latest

def _selected_keys(answer) -> list[str]:
    """Cles stables des options retenues par une reponse.

    La table des selections fait foi ; l'instantane sert de secours pour les
    reponses ecrites avant qu'elle n'existe.
    """
    keys = [s.option_stable_key for s in answer.selections.all() if s.option_stable_key]
    if keys:
        return keys

    snapshot = answer.snapshot or {}
    by_id    = {int(o["id"]): o.get("stable_key") for o in snapshot.get("options", [])
                if o.get("id") is not None}
    return [by_id[i] for i in (answer.value or {}).get("option_ids", []) if i in by_id]

def _remap_options(answer, question):
    """Traduit des identifiants d'options d'une version vers une autre.

    Les cles primaires sont propres a chaque version : seule la cle stable
    traverse. Une option supprimee entre deux versions est simplement perdue.
    """
    old_keys = _selected_keys(answer)
    if not old_keys:
        return None

    new_ids = {option.stable_key: option.id for option in question.options.all()}
    mapped  = [new_ids[key] for key in old_keys if key in new_ids]
    return {"option_ids": mapped} if mapped else None

def _transferable(answer, questions_by_key: dict):
    """Question d'accueil d'une reponse, si elle est encore transferable.

    Rend (question, valeur) ou None : la question a disparu, ses options ont
    disparu, ou la valeur ne satisfait plus la configuration de la nouvelle
    version.
    """
    question = questions_by_key.get(answer.question_stable_key)
    if question is None or answer.value is None:
        return None

    raw = answer.value
    if question.handler.uses_options:
        raw = _remap_options(answer, question)
        if raw is None:
            return None

    try:
        value = question.handler.normalize_answer(question, raw)
    except AnswerError:
        return None
    if value is None:
        return None
    return question, value

def _write_answer(attempt, question, value, *, source = None) -> UserAnswer:
    """Ecrit une reponse reportee, avec un instantane de la nouvelle version."""
    answer = UserAnswer(
        attempt             = attempt,
        question            = question,
        question_stable_key = question.stable_key,
        value               = value,
        snapshot            = answer_snapshot(question),
        carried             = True,
        client_sequence     = source.client_sequence if source else 0,
    )
    answer.save()

    if question.handler.uses_options:
        keys = dict(question.options.values_list("id", "stable_key"))
        UserAnswerSelection.objects.bulk_create([
            UserAnswerSelection(answer = answer, option_id = option_id,
                                option_stable_key = keys.get(option_id, ""))
            for option_id in (value.get("option_ids") or [])
        ])
    return answer

def _missing_required(version, answers_by_key: dict) -> list:
    """Questions obligatoires visibles restees sans reponse."""
    questions = list(version.questions.prefetch_related("options").order_by("order", "id"))
    visible   = compute_visible(questions, answers_by_key)
    return [
        question for question in visible
        if question.required and not question.handler.is_answered(
            answers_by_key.get(question.stable_key))
    ]

def preview(questionnaire, version) -> dict:
    """Ce que le report ferait, sans rien ecrire.

    Sert a prevenir l'administrateur avant qu'il ne publie.
    """
    questions_by_key = {
        q.stable_key: q
        for q in version.questions.prefetch_related("options")
    }
    latest = _latest_per_user(_previous_attempts(questionnaire, version))

    report = {"participants": len(latest), "in_progress": 0, "rescored": 0,
              "pending": 0, "dropped_answers": 0, "new_questions": []}
    if not latest:
        return report

    previous_keys = set()
    for attempt in latest.values():
        previous_keys |= set(
            attempt.version.questions.values_list("stable_key", flat = True))
    report["new_questions"] = [
        q.text for key, q in questions_by_key.items() if key not in previous_keys
    ]

    for attempt in latest.values():
        carried, dropped = {}, 0
        for answer in attempt.answers.select_related("question"):
            transfer = _transferable(answer, questions_by_key)
            if transfer is None:
                dropped += 1
            else:
                carried[transfer[0].stable_key] = transfer[1]

        report["dropped_answers"] += dropped
        if attempt.status == c.ATTEMPT_IN_PROGRESS:
            report["in_progress"] += 1
        elif _missing_required(version, carried):
            report["pending"] += 1
        else:
            report["rescored"] += 1

    return report

@transaction.atomic
def carry_over(questionnaire, version, *, actor = None) -> dict:
    """Reporte les reponses des participants sur `version`.

    Retourne un rapport chiffre, journalise dans l'audit.
    """
    questions_by_key = {
        q.stable_key: q
        for q in version.questions.prefetch_related("options")
    }
    latest = _latest_per_user(_previous_attempts(questionnaire, version))

    report = {"participants": 0, "moved": 0, "rescored": 0, "pending": 0,
              "dropped_answers": 0, "skipped": 0}

    for attempt in latest.values():
        if attempt.version_id == version.id:
            continue
        report["participants"] += 1

        if attempt.status == c.ATTEMPT_IN_PROGRESS:
            outcome = _move_in_progress(attempt, version, questions_by_key)
        else:
            outcome = _continue_completed(attempt, version, questions_by_key)

        if outcome is None:
            report["skipped"] += 1
            continue
        kind, dropped = outcome
        report[kind] += 1
        report["dropped_answers"] += dropped

    if report["participants"]:
        log(actor, c.AUDIT_UPDATE, version, questionnaire = questionnaire,
            new = report, operation = "carry_over")
    return report

def _move_in_progress(attempt, version, questions_by_key: dict):
    """Deplace une tentative en cours sur la nouvelle version.

    Les reponses sont reecrites sur les questions correspondantes ; la tentative
    garde son identite, son historique et sa date de debut.
    """
    previous = list(attempt.answers.select_related("question"))
    carried, dropped = {}, 0

    for answer in previous:
        transfer = _transferable(answer, questions_by_key)
        if transfer is None:
            dropped += 1
        else:
            carried[transfer[0].stable_key] = (transfer[0], transfer[1], answer)

    UserAnswerSelection.objects.filter(answer__attempt = attempt).delete()
    attempt.answers.all().delete()

    attempt.version = version
    attempt.current_question = None
    attempt.save(update_fields = ["version", "current_question", "last_activity_at"])

    for question, value, source in carried.values():
        _write_answer(attempt, question, value, source = source)

    from .services import refresh_progress

    refresh_progress(attempt)
    return "moved", dropped

def _continue_completed(attempt, version, questions_by_key: dict):
    """Cree une tentative de suite pour un participant deja arrive au bout.

    L'ancienne tentative et son resultat ne sont pas touches.
    """
    from .services import finish_attempt, refresh_progress

    user = attempt.user

    if QuestionnaireAttempt.objects.filter(
        questionnaire = attempt.questionnaire, user = user,
        is_test = False, status = c.ATTEMPT_IN_PROGRESS,
    ).exists():
        return None

    if QuestionnaireAttempt.objects.filter(
        questionnaire = attempt.questionnaire, user = user,
        version = version, is_test = False,
    ).exists():
        return None

    carried, dropped = {}, 0
    for answer in attempt.answers.select_related("question"):
        transfer = _transferable(answer, questions_by_key)
        if transfer is None:
            dropped += 1
        else:
            carried[transfer[0].stable_key] = (transfer[0], transfer[1], answer)

    number = QuestionnaireAttempt.objects.filter(
        questionnaire = attempt.questionnaire, user = user, is_test = False,
    ).count() + 1

    successor = QuestionnaireAttempt.objects.create(
        user           = user,
        questionnaire  = attempt.questionnaire,
        version        = version,
        is_test        = False,
        attempt_number = number,
        carried_from   = attempt,
        expires_at     = attempt.expires_at,
        metadata       = {"carried_from_version": attempt.version.version_number},
    )
    for question, value, source in carried.values():
        _write_answer(successor, question, value, source = source)

    refresh_progress(successor)

    values  = {key: v for key, (_, v, _) in carried.items()}
    missing = _missing_required(version, values)
    if missing:
        return "pending", dropped

    finish_attempt(successor)
    return "rescored", dropped
