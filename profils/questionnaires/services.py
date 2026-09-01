##services.py
"""Cycle de vie des tentatives : demarrage, sauvegarde, reprise, fin.

Toute la logique metier vit ici ; l'API n'est qu'une couche de transport. Rien
n'est jamais accorde sur la foi de ce qu'envoie le client : la version, le
numero de tentative, la visibilite des questions et le score sont recalcules
cote serveur.
"""

from decimal import Decimal

from django.db    import IntegrityError, transaction
from django.utils          import timezone

from . import constants as c
from .access     import assert_can_start, assert_version_usable, attempt_deadline
from .auditing   import log
from .conditions import compute_visible
from .models     import (
    Question, QuestionnaireAttempt, QuestionnaireResult, UserAnswer, UserAnswerSelection,
)
from .question_types import AnswerError
from .scoring        import score_attempt
from .snapshots      import answer_snapshot


class AttemptError(Exception):
    """Erreur de cycle de vie d'une tentative."""

    def __init__(self, reason: str, code: str = "attempt_error", status: int = 409):
        super().__init__(reason)
        self.reason = reason
        self.code   = code
        self.status = status


class StaleWrite(AttemptError):
    """Ecriture perimee : une reponse plus recente existe deja."""

    def __init__(self, answer):
        super().__init__("une reponse plus recente existe deja", "stale_write", 409)
        self.answer = answer


# --------------------------------------------------------------------------- #
# Expiration
# --------------------------------------------------------------------------- #

def expire_if_needed(attempt) -> bool:
    """Bascule la tentative en EXPIRED si son echeance est depassee."""
    if attempt.status != c.ATTEMPT_IN_PROGRESS or not attempt.is_expired:
        return False
    attempt.status = c.ATTEMPT_EXPIRED
    attempt.save(update_fields = ["status", "last_activity_at"])
    log(attempt.user, c.AUDIT_UPDATE, attempt, questionnaire = attempt.questionnaire,
        new = {"status": c.ATTEMPT_EXPIRED}, reason = "expiration")
    return True


def expire_stale_attempts(questionnaire = None) -> int:
    """Balayage des tentatives echues. Appelable par une tache planifiee."""
    queryset = QuestionnaireAttempt.objects.filter(
        status     = c.ATTEMPT_IN_PROGRESS,
        expires_at__isnull = False,
        expires_at__lt     = timezone.now(),
    )
    if questionnaire is not None:
        queryset = queryset.filter(questionnaire = questionnaire)
    return queryset.update(status = c.ATTEMPT_EXPIRED)


# --------------------------------------------------------------------------- #
# Demarrage / reprise
# --------------------------------------------------------------------------- #

def current_attempt(questionnaire, user, *, test: bool = False):
    """Tentative en cours de l'utilisateur, ou None."""
    attempt = QuestionnaireAttempt.objects.filter(
        questionnaire = questionnaire, user = user,
        is_test = test, status = c.ATTEMPT_IN_PROGRESS,
    ).select_related("version").first()

    if attempt and expire_if_needed(attempt):
        return None
    return attempt


def _check_attempt_quota(questionnaire, user, *, test: bool):
    """Nombre de tentatives, delai d'attente et rejouabilite (section 15)."""
    if test:
        return

    previous = QuestionnaireAttempt.objects.filter(
        questionnaire = questionnaire, user = user, is_test = False,
    ).order_by("-started_at")

    used = previous.count()
    if questionnaire.max_attempts is not None and used >= questionnaire.max_attempts:
        raise AttemptError(
            f"nombre maximal de tentatives atteint ({questionnaire.max_attempts})",
            "attempt_limit_reached",
        )

    last = previous.first()
    if last is None:
        return

    if questionnaire.cooldown_seconds and last.completed_at:
        from datetime import timedelta

        ready_at = last.completed_at + timedelta(seconds = questionnaire.cooldown_seconds)
        if timezone.now() < ready_at:
            raise AttemptError(
                f"nouvelle tentative possible a partir de {ready_at.isoformat()}",
                "cooldown_active",
            )

    best = QuestionnaireResult.objects.filter(
        questionnaire = questionnaire, user = user, is_test = False,
    ).order_by("-percentage").first()

    if best is not None:
        if best.passed and not questionnaire.allow_retry_after_pass:
            raise AttemptError("questionnaire deja reussi", "already_passed")
        if not best.passed and not questionnaire.allow_retry_after_fail:
            raise AttemptError("nouvelle tentative non autorisee apres echec", "retry_after_fail_denied")


@transaction.atomic
def start_attempt(questionnaire, user, *, test: bool = False) -> QuestionnaireAttempt:
    """Demarre une tentative, ou rend celle deja en cours.

    Idempotent : rappeler `start` alors qu'une tentative est ouverte rend la
    meme tentative plutot que d'en creer une seconde.
    """
    existing = current_attempt(questionnaire, user, test = test)
    if existing is not None:
        return existing

    assert_can_start(questionnaire, user, test = test)

    version = questionnaire.runnable_version(test = test)
    assert_version_usable(version, test = test)
    _check_attempt_quota(questionnaire, user, test = test)

    number = QuestionnaireAttempt.objects.filter(
        questionnaire = questionnaire, user = user, is_test = test,
    ).count() + 1

    try:
        attempt = QuestionnaireAttempt.objects.create(
            user           = user,
            questionnaire  = questionnaire,
            version        = version,
            is_test        = test,
            attempt_number = number,
            expires_at     = attempt_deadline(questionnaire),
        )
    except IntegrityError:
        # course entre deux onglets : la contrainte d'unicite a tranche
        existing = current_attempt(questionnaire, user, test = test)
        if existing is None:
            raise
        return existing

    refresh_progress(attempt)
    log(user, c.AUDIT_CREATE, attempt, questionnaire = questionnaire,
        new = {"version": version.version_number, "is_test": test, "attempt_number": number})
    return attempt


# --------------------------------------------------------------------------- #
# Etat / progression
# --------------------------------------------------------------------------- #

def attempt_questions(attempt) -> list[Question]:
    return list(attempt.version.questions.prefetch_related("options").order_by("order", "id"))


def answers_map(attempt) -> dict:
    """Cle stable de question -> UserAnswer."""
    return {
        answer.question.stable_key: answer
        for answer in attempt.answers.select_related("question").prefetch_related("selections")
    }


def visible_questions(attempt, questions = None, answers = None) -> list[Question]:
    questions = questions if questions is not None else attempt_questions(attempt)
    answers   = answers   if answers   is not None else answers_map(attempt)
    return compute_visible(questions, {key: a.value for key, a in answers.items()})


def refresh_progress(attempt, *, questions = None, answers = None, save = True) -> dict:
    """Recalcule la progression a partir des seules questions visibles."""
    questions = questions if questions is not None else attempt_questions(attempt)
    answers   = answers   if answers   is not None else answers_map(attempt)
    visible   = visible_questions(attempt, questions, answers)

    answered = sum(
        1 for question in visible
        if question.handler.is_answered(
            (answers.get(question.stable_key).value if answers.get(question.stable_key) else None)
        )
    )
    total   = len(visible)
    percent = Decimal(answered * 100) / Decimal(total) if total else Decimal(0)

    attempt.answered_count   = answered
    attempt.visible_count    = total
    attempt.progress_percent = percent.quantize(Decimal("0.01"))

    if save:
        attempt.revision += 1
        attempt.save(update_fields = [
            "answered_count", "visible_count", "progress_percent", "revision", "last_activity_at",
        ])

    return {
        "answered": answered,
        "total":    total,
        "percent":  str(attempt.progress_percent),
        "visible":  [q.id for q in visible],
    }


def next_unanswered(attempt, answers = None):
    """Question sur laquelle reprendre la tentative."""
    answers = answers if answers is not None else answers_map(attempt)
    for question in visible_questions(attempt, answers = answers):
        answer = answers.get(question.stable_key)
        if not question.handler.is_answered(answer.value if answer else None):
            return question
    return None


# --------------------------------------------------------------------------- #
# Sauvegarde d'une reponse
# --------------------------------------------------------------------------- #

def _assert_answer_writable(attempt, question, existing):
    questionnaire = attempt.questionnaire

    if attempt.status != c.ATTEMPT_IN_PROGRESS:
        raise AttemptError(f"tentative {attempt.status.lower()}", "attempt_closed")
    if attempt.is_expired:
        expire_if_needed(attempt)
        raise AttemptError("tentative expiree", "attempt_expired")
    if not attempt.version.accepts_answers:
        raise AttemptError(
            f"version {attempt.version.status.lower()} : plus aucune reponse acceptee",
            "version_closed",
        )
    if question.version_id != attempt.version_id:
        raise AttemptError("cette question n'appartient pas a la version en cours", "question_mismatch", 400)

    if existing is not None:
        if existing.locked:
            raise AttemptError("reponse verrouillee", "answer_locked")
        if questionnaire.answer_edit_mode == c.ANSWERS_LOCKED_ON_VALIDATE:
            raise AttemptError("les reponses ne sont pas modifiables", "answer_not_editable")


@transaction.atomic
def save_answer(attempt, question_id: int, raw_value, *,
                client_sequence: int = None, idempotency_key: str = "") -> dict:
    """Enregistre immediatement une reponse et rend le nouvel etat serveur.

    Trois garde-fous de concurrence (section 33) :

      * `idempotency_key` : rejouer la meme requete ne cree pas de doublon et
        renvoie l'etat deja enregistre ;
      * `client_sequence` : une requete arrivee dans le desordre n'ecrase pas
        une reponse plus recente (None = le client ne sequence pas ; 0 est une
        valeur de sequence valide) ;
      * `revision` : compteur serveur renvoye au client a chaque ecriture.
    """
    attempt = QuestionnaireAttempt.objects.select_for_update().get(pk = attempt.pk)

    question = attempt.version.questions.prefetch_related("options").filter(pk = question_id).first()
    if question is None:
        raise AttemptError("question inconnue pour cette tentative", "unknown_question", 404)

    existing = UserAnswer.objects.filter(attempt = attempt, question = question).first()

    if idempotency_key and existing and existing.idempotency_key == idempotency_key:
        return answer_state(attempt, existing, replayed = True)

    _assert_answer_writable(attempt, question, existing)

    if existing and client_sequence is not None and existing.client_sequence > client_sequence:
        raise StaleWrite(existing)

    questions = attempt_questions(attempt)
    answers   = {a.question.stable_key: a for a in attempt.answers.select_related("question")}
    if question.stable_key not in {q.stable_key for q in visible_questions(attempt, questions, answers)}:
        raise AttemptError("cette question n'est pas visible en l'etat", "question_not_visible", 409)

    try:
        value = question.handler.normalize_answer(question, raw_value)
    except AnswerError as exc:
        raise AttemptError(str(exc), "invalid_answer", 400)

    if existing is None:
        answer = UserAnswer(attempt = attempt, question = question)
        answer.question_stable_key = question.stable_key
    else:
        answer = existing
        answer.revision += 1

    answer.value           = value
    answer.snapshot        = answer_snapshot(question)
    answer.client_sequence = max(client_sequence or 0, answer.client_sequence or 0)
    answer.idempotency_key = idempotency_key or ""
    if attempt.questionnaire.answer_edit_mode == c.ANSWERS_LOCKED_ON_VALIDATE:
        answer.locked = True

    try:
        answer.save()
    except IntegrityError:
        # deux onglets ont cree la reponse en meme temps : on reprend l'existante
        answer = UserAnswer.objects.get(attempt = attempt, question = question)
        answer.value    = value
        answer.snapshot = answer_snapshot(question)
        answer.revision += 1
        answer.save()

    _sync_selections(answer, question, value)

    answers[question.stable_key] = answer
    attempt.current_question = question
    progress = refresh_progress(attempt, questions = questions, answers = answers, save = False)
    attempt.revision += 1
    attempt.save(update_fields = [
        "answered_count", "visible_count", "progress_percent",
        "current_question", "revision", "last_activity_at",
    ])

    return answer_state(attempt, answer, progress = progress)


def _sync_selections(answer, question, value):
    """Maintient la table des options retenues (statistiques futures)."""
    if not question.handler.uses_options:
        answer.selections.all().delete()
        return

    wanted   = set((value or {}).get("option_ids") or [])
    existing = {s.option_id: s for s in answer.selections.all()}

    for option_id, selection in existing.items():
        if option_id not in wanted:
            selection.delete()

    keys = dict(question.options.values_list("id", "stable_key"))
    UserAnswerSelection.objects.bulk_create([
        UserAnswerSelection(
            answer            = answer,
            option_id         = option_id,
            option_stable_key = keys.get(option_id, ""),
        )
        for option_id in wanted if option_id not in existing
    ])


def answer_state(attempt, answer, *, progress = None, replayed: bool = False) -> dict:
    """Etat renvoye au client apres une sauvegarde."""
    return {
        "saved":            True,
        "replayed":         replayed,
        "server_time":      timezone.now().isoformat(),
        "attempt_revision": attempt.revision,
        "answer": {
            "question_id":     answer.question_id,
            "value":           answer.value,
            "revision":        answer.revision,
            "client_sequence": answer.client_sequence,
            "locked":          answer.locked,
            "updated_at":      answer.updated_at.isoformat() if answer.updated_at else None,
        },
        "progress": progress if progress is not None else refresh_progress(attempt, save = False),
    }


@transaction.atomic
def clear_answer(attempt, question_id: int) -> dict:
    """Efface une reponse (retour a l'etat non repondu)."""
    answer = UserAnswer.objects.filter(attempt = attempt, question_id = question_id).first()
    if answer is None:
        raise AttemptError("aucune reponse a effacer", "no_answer", 404)
    _assert_answer_writable(attempt, answer.question, answer)

    answer.selections.all().delete()
    answer.value    = None
    answer.revision += 1
    answer.save(update_fields = ["value", "revision", "updated_at"])

    progress = refresh_progress(attempt)
    return {"cleared": True, "progress": progress}


# --------------------------------------------------------------------------- #
# Fin de tentative
# --------------------------------------------------------------------------- #

@transaction.atomic
def finish_attempt(attempt, *, force: bool = False) -> QuestionnaireResult:
    """Termine une tentative, calcule le score et historise le resultat."""
    attempt = QuestionnaireAttempt.objects.select_for_update().get(pk = attempt.pk)

    if attempt.status != c.ATTEMPT_IN_PROGRESS:
        existing = QuestionnaireResult.objects.filter(attempt = attempt).first()
        if existing is not None:
            return existing
        raise AttemptError(f"tentative {attempt.status.lower()}", "attempt_closed")

    questions = attempt_questions(attempt)
    answers   = answers_map(attempt)
    visible   = compute_visible(questions, {k: a.value for k, a in answers.items()})

    if not force:
        missing = [
            question.id for question in visible
            if question.required and not question.handler.is_answered(
                answers[question.stable_key].value if question.stable_key in answers else None
            )
        ]
        if missing:
            raise AttemptError(
                "des questions obligatoires sont sans reponse", "missing_required", 400
            )

    computed = score_attempt(attempt)

    for entry in computed["details"]["questions"]:
        if not entry.get("answer_id"):
            continue
        UserAnswer.objects.filter(pk = entry["answer_id"]).update(
            is_correct    = entry.get("is_correct"),
            score         = Decimal(entry["score"]),
            score_details = entry.get("details", {}),
            locked        = True,
        )

    now = timezone.now()
    attempt.status       = c.ATTEMPT_COMPLETED
    attempt.completed_at = now
    attempt.score        = computed["score"]
    attempt.max_score    = computed["max_score"]
    attempt.percentage   = computed["percentage"]
    attempt.passed       = computed["passed"]
    attempt.revision    += 1
    attempt.save(update_fields = [
        "status", "completed_at", "score", "max_score", "percentage",
        "passed", "revision", "last_activity_at",
    ])

    result = QuestionnaireResult.objects.create(
        attempt       = attempt,
        user          = attempt.user,
        questionnaire = attempt.questionnaire,
        version       = attempt.version,
        score         = computed["score"],
        max_score     = computed["max_score"],
        percentage    = computed["percentage"],
        passed        = computed["passed"],
        level         = computed["level"],
        is_test       = attempt.is_test,
        duration_seconds = int((now - attempt.started_at).total_seconds()),
        details       = computed["details"],
    )

    log(attempt.user, c.AUDIT_UPDATE, attempt, questionnaire = attempt.questionnaire,
        new = {"status": c.ATTEMPT_COMPLETED, "percentage": str(result.percentage)},
        is_test = attempt.is_test)

    if not attempt.is_test:
        from .badges import award_for_result

        award_for_result(result)

    return result


@transaction.atomic
def abandon_attempt(attempt) -> QuestionnaireAttempt:
    if attempt.status != c.ATTEMPT_IN_PROGRESS:
        raise AttemptError(f"tentative {attempt.status.lower()}", "attempt_closed")
    attempt.status = c.ATTEMPT_ABANDONED
    attempt.save(update_fields = ["status", "last_activity_at"])
    log(attempt.user, c.AUDIT_UPDATE, attempt, questionnaire = attempt.questionnaire,
        new = {"status": c.ATTEMPT_ABANDONED})
    return attempt


@transaction.atomic
def invalidate_attempt(attempt, *, actor = None, reason: str = "") -> QuestionnaireAttempt:
    attempt.status = c.ATTEMPT_INVALIDATED
    attempt.save(update_fields = ["status", "last_activity_at"])
    log(actor, c.AUDIT_INVALIDATE, attempt, questionnaire = attempt.questionnaire,
        new = {"status": c.ATTEMPT_INVALIDATED, "reason": reason})
    return attempt
