"""Conversion des modeles en structures JSON.

Deux familles de fonctions, volontairement distinctes :

  * `admin_*` : vue complete, reponses attendues et scoring compris ;
  * `runner_*` / `public_*` : vue utilisateur, expurgee de tout corrige.

Cette separation est la garantie qu'un corrige ne peut pas fuir par megarde
dans une reponse d'API destinee a un participant.
"""

from . import constants as c
from .access     import result_visibility
from .conditions import compute_visible
from .permissions import is_questionnaire_admin

def admin_option(option) -> dict:
    return {
        "id":          option.id,
        "stable_key":  option.stable_key,
        "order":       option.order,
        "text":        option.text,
        "description": option.description,
        "value":       option.value,
        "is_correct":  option.is_correct,
        "score":       str(option.score) if option.score is not None else None,
    }

def admin_question(question) -> dict:
    return {
        "id":              question.id,
        "stable_key":      question.stable_key,
        "order":           question.order,
        "text":            question.text,
        "description":     question.description,
        "explanation":     question.explanation,
        "type":            question.type,
        "required":        question.required,
        "config":          question.config,
        "expected_config": question.expected_config,
        "scoring_config":  question.scoring,
        "condition":       question.condition,
        "is_graded":       question.is_graded,
        "options":         [admin_option(o) for o in question.options.all()],
    }

def admin_version(version, *, with_questions: bool = False) -> dict:
    payload = {
        "id":             version.id,
        "version_number": version.version_number,
        "status":         version.status,
        "title":          version.title,
        "description":    version.description,
        "scoring_config": version.scoring,
        "valid_from":     _iso(version.valid_from),
        "valid_until":    _iso(version.valid_until),
        "created_at":     _iso(version.created_at),
        "created_by":     version.created_by.username if version.created_by else None,
        "derived_from":   version.derived_from.version_number if version.derived_from else None,
        "published_at":   _iso(version.published_at),
        "published_by":   version.published_by.username if version.published_by else None,
        "invalidated_at": _iso(version.invalidated_at),
        "invalidation_reason": version.invalidation_reason,
        "is_editable":    version.is_editable,
        "accepts_answers": version.accepts_answers,
        "question_count": version.questions.count(),
        "attempt_count":  version.attempts.count(),
    }
    if with_questions:
        payload["questions"] = [
            admin_question(q) for q in version.questions.prefetch_related("options")
        ]
    return payload

def admin_access_rule(rule) -> dict:
    return {
        "id":          rule.id,
        "kind":        rule.kind,
        "group_index": rule.group_index,
        "rule_type":   rule.rule_type,
        "negate":      rule.negate,
        "user":        {"id": rule.target_user_id, "username": rule.target_user.username}
                       if rule.target_user_id else None,
        "role":        rule.role,
        "badge":       {"id": rule.badge_id, "code": rule.badge.code} if rule.badge_id else None,
        "description": rule.describe(),
    }

def admin_questionnaire(questionnaire, *, detail: bool = False) -> dict:
    current = questionnaire.current_version
    payload = {
        "id":          questionnaire.id,
        "slug":        questionnaire.slug,
        "title":       questionnaire.title,
        "description": questionnaire.description,
        "status":      questionnaire.status,
        "created_at":  _iso(questionnaire.created_at),
        "updated_at":  _iso(questionnaire.updated_at),
        "created_by":  questionnaire.created_by.username if questionnaire.created_by else None,
        "current_version": current.version_number if current else None,
        "version_count":   questionnaire.versions.count(),
        "attempt_count":   questionnaire.attempts.filter(is_test = False).count(),
        "test_attempt_count": questionnaire.attempts.filter(is_test = True).count(),
        "available_from":  _iso(questionnaire.available_from),
        "available_until": _iso(questionnaire.available_until),
    }

    if not detail:
        return payload

    payload |= {
        "attempt_rules": {
            "max_attempts":           questionnaire.max_attempts,
            "cooldown_seconds":       questionnaire.cooldown_seconds,
            "time_limit_seconds":     questionnaire.time_limit_seconds,
            "attempt_expiry_seconds": questionnaire.attempt_expiry_seconds,
            "allow_retry_after_pass": questionnaire.allow_retry_after_pass,
            "allow_retry_after_fail": questionnaire.allow_retry_after_fail,
            "keep_previous_attempts": questionnaire.keep_previous_attempts,
            "carry_over_answers":     questionnaire.carry_over_answers,
        },
        "answer_rules": {
            "answer_edit_mode": questionnaire.answer_edit_mode,
            "navigation_mode":  questionnaire.navigation_mode,
            "allow_back":       questionnaire.allow_back,
        },
        "result_visibility": questionnaire.visibility_settings,
        "access_rules":      [admin_access_rule(r) for r in questionnaire.access_rules.all()],
        "versions":          [admin_version(v) for v in questionnaire.versions.all()],
    }
    return payload

def runner_option(option) -> dict:
    """Option telle qu'affichee : jamais d'indication de justesse."""
    return {
        "id":          option.id,
        "stable_key":  option.stable_key,
        "order":       option.order,
        "text":        option.text,
        "description": option.description,
        "value":       option.value,
    }

def runner_question(question, answer = None, *, visible: bool = True) -> dict:
    """Question telle qu'affichee, sans aucune information de correction."""
    handler = question.handler
    value   = answer.value if answer else None

    vocabulary = None
    if hasattr(handler, "vocabulary"):
        vocabulary = [
            {"code": code, "label": label}
            for code, label in handler.vocabulary(question).items()
        ]

    payload = {
        "id":          question.id,
        "stable_key":  question.stable_key,
        "order":       question.order,
        "text":        question.text,
        "description": question.description,
        "type":        question.type,
        "family":      handler.family,
        "widget":      handler.widget,
        "required":    question.required,
        "config":      question.config,
        "uses_options": handler.uses_options,
        "multiple":    handler.multiple,
        "visible":     visible,
        "options":     [runner_option(o) for o in question.options.all()] if handler.uses_options else [],
        "answer": {
            "value":           value,
            "answered":        handler.is_answered(value),
            "locked":          bool(answer.locked) if answer else False,
            "revision":        answer.revision if answer else 0,
            "client_sequence": answer.client_sequence if answer else 0,
            "updated_at":      _iso(answer.updated_at) if answer else None,
        },
    }
    if vocabulary is not None:
        payload["vocabulary"] = vocabulary
    if handler.family == c.FAMILY_NUMERIC:
        payload["units"] = list(getattr(handler, "units", ()))
    return payload

def runner_state(attempt) -> dict:
    """Etat complet d'une tentative, tel que consomme par l'interface."""
    from .services import answers_map, attempt_questions, next_unanswered

    questionnaire = attempt.questionnaire
    questions     = attempt_questions(attempt)
    answers       = answers_map(attempt)
    visible       = compute_visible(questions, {k: a.value for k, a in answers.items()})
    visible_ids   = {q.id for q in visible}

    resume = next_unanswered(attempt, answers)

    return {
        "attempt": {
            "id":             attempt.id,
            "status":         attempt.status,
            "is_test":        attempt.is_test,
            "attempt_number": attempt.attempt_number,
            "revision":       attempt.revision,
            "started_at":     _iso(attempt.started_at),
            "last_activity_at": _iso(attempt.last_activity_at),
            "expires_at":     _iso(attempt.expires_at),
            "progress": {
                "answered": attempt.answered_count,
                "total":    attempt.visible_count,
                "percent":  str(attempt.progress_percent),
            },
            "resume_question_id": resume.id if resume else None,
        },
        "questionnaire": {
            "id":          questionnaire.id,
            "title":       attempt.version.title,
            "description": attempt.version.description,
            "navigation_mode":  questionnaire.navigation_mode,
            "answer_edit_mode": questionnaire.answer_edit_mode,
            "allow_back":       questionnaire.allow_back,
        },
        "version": {
            "id":             attempt.version_id,
            "version_number": attempt.version.version_number,
            "status":         attempt.version.status,
        },
        "questions": [
            runner_question(q, answers.get(q.stable_key), visible = q.id in visible_ids)
            for q in questions if q.id in visible_ids
        ],
        "visible_question_ids": [q.id for q in visible],
        "server_time": _now(),
    }

def public_questionnaire(questionnaire, user) -> dict:
    """Carte d'un questionnaire dans la liste utilisateur."""
    from .models   import QuestionnaireAttempt, QuestionnaireResult
    from .services import current_attempt

    attempts = QuestionnaireAttempt.objects.filter(
        questionnaire = questionnaire, user = user, is_test = False
    )
    best = QuestionnaireResult.objects.filter(
        questionnaire = questionnaire, user = user, is_test = False
    ).order_by("-percentage").first()

    open_attempt = current_attempt(questionnaire, user)
    version      = questionnaire.runnable_version(test = False)

    return {
        "id":          questionnaire.id,
        "slug":        questionnaire.slug,
        "title":       questionnaire.title,
        "description": questionnaire.description,
        "status":      questionnaire.status,
        "question_count": version.questions.count() if version else 0,
        "available_from":  _iso(questionnaire.available_from),
        "available_until": _iso(questionnaire.available_until),
        "max_attempts":    questionnaire.max_attempts,
        "attempts_used":   attempts.count(),
        "has_open_attempt": open_attempt is not None,
        "open_attempt_id":  open_attempt.id if open_attempt else None,
        "best_result": {
            "percentage": str(best.percentage),
            "passed":     best.passed,
            "computed_at": _iso(best.computed_at),
        } if best else None,
        "can_start": _can_start(questionnaire, user),
    }

def _can_start(questionnaire, user) -> dict:
    from .access   import AccessDenied, assert_can_start, assert_version_usable
    from .services import AttemptError, _check_attempt_quota

    try:
        assert_can_start(questionnaire, user)
        assert_version_usable(questionnaire.runnable_version(test = False))
        _check_attempt_quota(questionnaire, user, test = False)
    except (AccessDenied, AttemptError) as exc:
        return {"allowed": False, "code": exc.code, "reason": exc.reason}
    return {"allowed": True, "code": None, "reason": None}

def result_payload(result, viewer) -> dict:
    """Resultat filtre selon la configuration de visibilite (section 23)."""
    questionnaire = result.questionnaire
    allowed       = result_visibility(questionnaire, viewer)
    is_admin      = is_questionnaire_admin(viewer)

    payload = {
        "attempt_id":     result.attempt_id,
        "questionnaire":  {"id": questionnaire.id, "title": questionnaire.title},
        "version":        result.version.version_number,
        "is_test":        result.is_test,
        "computed_at":    _iso(result.computed_at),
        "duration_seconds": result.duration_seconds,
        "visibility":     allowed,
    }

    if allowed.get("show_score"):
        payload |= {"score": str(result.score), "max_score": str(result.max_score)}
    if allowed.get("show_percentage"):
        payload["percentage"] = str(result.percentage)
    if allowed.get("show_pass_fail"):
        payload |= {"passed": result.passed, "level": result.level}
    if allowed.get("show_badge"):
        payload["badges"] = [
            {"code": b.badge.code, "name": b.badge.name}
            for b in result.awarded_badges.select_related("badge")
        ]

    if any(allowed.get(key) for key in
           ("show_user_answers", "show_correct_answers", "show_incorrect_answers", "show_explanations")):
        payload["answers"] = _result_answers(result, allowed, is_admin)

    return payload

def _result_answers(result, allowed: dict, is_admin: bool) -> list[dict]:
    entries = {
        entry.get("question_id"): entry
        for entry in (result.details or {}).get("questions", [])
    }
    rows = []

    for answer in result.attempt.answers.select_related("question").prefetch_related("question__options"):
        question = answer.question
        entry    = entries.get(question.id, {})
        row = {
            "question_id": question.id,
            "text":        (answer.snapshot or {}).get("text", question.text),
            "type":        question.type,
            "skipped":     entry.get("skipped"),
        }

        if allowed.get("show_user_answers"):
            row["given"] = question.handler.display(question, answer.value, answer.snapshot)

        show_correctness = (
            allowed.get("show_correct_answers")
            or (allowed.get("show_incorrect_answers") and answer.is_correct is False)
        )
        if show_correctness:
            row["is_correct"] = answer.is_correct
            row["expected"]   = question.handler.describe_expected(question, answer.snapshot)
        elif allowed.get("show_pass_fail") and answer.is_correct is not None:
            row["is_correct"] = answer.is_correct

        if allowed.get("show_explanations") and question.explanation:
            row["explanation"] = question.explanation

        if allowed.get("show_score") and entry:
            row |= {"score": entry.get("score"), "max_score": entry.get("max_score")}

        if is_admin:
            row["details"] = entry

        rows.append(row)

    return rows

def attempt_summary(attempt, *, for_admin: bool = False) -> dict:
    payload = {
        "id":             attempt.id,
        "user":           attempt.user.username,
        "user_id":        attempt.user_id,
        "questionnaire":  attempt.questionnaire_id,
        "version":        attempt.version.version_number,
        "status":         attempt.status,
        "is_test":        attempt.is_test,
        "attempt_number": attempt.attempt_number,
        "started_at":     _iso(attempt.started_at),
        "completed_at":   _iso(attempt.completed_at),
        "expires_at":     _iso(attempt.expires_at),
        "progress":       str(attempt.progress_percent),
        "answered_count": attempt.answered_count,
        "visible_count":  attempt.visible_count,
    }
    if for_admin:
        payload |= {
            "score":      str(attempt.score) if attempt.score is not None else None,
            "percentage": str(attempt.percentage) if attempt.percentage is not None else None,
            "passed":     attempt.passed,
        }
    return payload

def audit_entry(entry) -> dict:
    return {
        "id":         entry.id,
        "action":     entry.action,
        "actor":      entry.actor.username if entry.actor else None,
        "object":     f"{entry.object_type}#{entry.object_id}",
        "created_at": _iso(entry.created_at),
        "old_value":  entry.old_value,
        "new_value":  entry.new_value,
        "metadata":   entry.metadata,
    }

def _iso(value):
    return value.isoformat() if value else None

def _now():
    from django.utils import timezone

    return timezone.now().isoformat()
