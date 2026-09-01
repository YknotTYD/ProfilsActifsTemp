##api_admin.py
"""API d'administration des questionnaires.

Chaque endpoint declare la permission qu'il exige ; la verification est faite
par le decorateur `api(...)`, donc toujours cote serveur.
"""

from django.db        import transaction
from django.shortcuts import get_object_or_404
from django.utils     import timezone

from . import constants as c
from .auditing    import log, snapshot_fields
from .editing     import (
    add_option, create_question, delete_option, delete_question, reorder_questions,
    set_access_rules, update_option, update_question, validate_version_scoring,
)
from .http        import api, body, fail, get_bool, ok
from .models      import (
    AuditLog, Badge, Question, QuestionOption, Questionnaire, QuestionnaireAccessRule,
    QuestionnaireAttempt, QuestionnaireResult, QuestionnaireVersion,
)
from .permissions import admin_capabilities
from .question_types import catalog
from .serializers import (
    admin_access_rule, admin_questionnaire, admin_version, attempt_summary, audit_entry,
)
from .services    import invalidate_attempt
from .snapshots   import attempt_transcript
from .versioning  import (
    compare_versions, create_version, editable_version, invalidate_version,
    publish_version, restore_version, set_version_test,
)

SETTINGS_FIELDS = (
    "max_attempts", "cooldown_seconds", "time_limit_seconds", "attempt_expiry_seconds",
    "allow_retry_after_pass", "allow_retry_after_fail", "keep_previous_attempts",
    "answer_edit_mode", "navigation_mode", "allow_back",
)


def _questionnaire(pk) -> Questionnaire:
    return get_object_or_404(Questionnaire.objects.prefetch_related("access_rules", "versions"), pk = pk)


def _version(pk, number) -> QuestionnaireVersion:
    return get_object_or_404(
        QuestionnaireVersion.objects.select_related("questionnaire"),
        questionnaire_id = pk, version_number = number,
    )


# --------------------------------------------------------------------------- #
# Catalogue des types
# --------------------------------------------------------------------------- #

@api(("GET",), perm = c.PERM_VIEW)
def question_types(request):
    """Types de questions disponibles, pour construire l'editeur dynamiquement."""
    return ok({"families": dict(c.QUESTION_FAMILIES), "types": catalog()})


# --------------------------------------------------------------------------- #
# Questionnaires
# --------------------------------------------------------------------------- #

@api(("GET", "POST"), perm = c.PERM_VIEW)
def collection(request):
    if request.method == "POST":
        return _create(request)

    queryset = Questionnaire.objects.select_related("current_version").prefetch_related("versions")
    if status := request.GET.get("status"):
        queryset = queryset.filter(status = status)
    if search := request.GET.get("q"):
        queryset = queryset.filter(title__icontains = search)

    return ok({
        "questionnaires": [admin_questionnaire(q) for q in queryset],
        "capabilities":   admin_capabilities(request.user),
        "statuses":       dict(c.QUESTIONNAIRE_STATUSES),
    })


@transaction.atomic
def _create(request):
    from .permissions import has_perm

    if not has_perm(request.user, c.PERM_CREATE):
        return fail("permission refusee", "forbidden", 403, required = c.PERM_CREATE)

    payload = body(request)
    title   = str(payload.get("title", "")).strip()
    if not title:
        return fail("le titre est obligatoire", "missing_field", 400)

    questionnaire = Questionnaire.objects.create(
        title       = title,
        description = str(payload.get("description", "")),
        created_by  = request.user,
    )
    version = create_version(
        questionnaire, source = None, actor = request.user,
        title = title, description = questionnaire.description,
    )
    log(request.user, c.AUDIT_CREATE, questionnaire, questionnaire = questionnaire,
        new = {"title": title})

    return ok(
        admin_questionnaire(questionnaire, detail = True) | {"draft_version": version.version_number},
        status = 201,
    )


@api(("GET", "PUT", "PATCH", "POST", "DELETE"), perm = c.PERM_VIEW)
def item(request, pk):
    questionnaire = _questionnaire(pk)

    if request.method == "GET":
        return ok({
            "questionnaire": admin_questionnaire(questionnaire, detail = True),
            "capabilities":  admin_capabilities(request.user),
        })
    if request.method == "DELETE":
        return _delete(request, questionnaire)
    return _update(request, questionnaire)


def _update(request, questionnaire):
    from .permissions import has_perm

    if not has_perm(request.user, c.PERM_UPDATE):
        return fail("permission refusee", "forbidden", 403, required = c.PERM_UPDATE)

    payload = body(request)
    before  = snapshot_fields(questionnaire, ("title", "status") + SETTINGS_FIELDS)

    for field in ("title", "description"):
        if field in payload:
            setattr(questionnaire, field, str(payload[field]))

    for field in SETTINGS_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if field in ("allow_retry_after_pass", "allow_retry_after_fail",
                     "keep_previous_attempts", "allow_back"):
            value = get_bool(payload, field)
        elif field in ("answer_edit_mode", "navigation_mode"):
            valid = dict(c.ANSWER_EDIT_MODES if field == "answer_edit_mode" else c.NAVIGATION_MODES)
            if value not in valid:
                return fail(f"{field} invalide", "invalid_field", 400)
        elif value in (None, ""):
            value = None
        else:
            value = int(value)
        setattr(questionnaire, field, value)

    for field in ("available_from", "available_until"):
        if field in payload:
            setattr(questionnaire, field, _parse_dt(payload[field]))

    if "result_visibility" in payload:
        questionnaire.result_visibility = {
            key: bool(payload["result_visibility"].get(key, default))
            for key, default in c.DEFAULT_RESULT_VISIBILITY.items()
        }

    questionnaire.save()
    log(request.user, c.AUDIT_UPDATE, questionnaire, questionnaire = questionnaire,
        old = before, new = snapshot_fields(questionnaire, ("title", "status") + SETTINGS_FIELDS))

    return ok({"questionnaire": admin_questionnaire(questionnaire, detail = True)})


def _delete(request, questionnaire):
    """Suppression : archivage par defaut, effacement reel seulement si vierge."""
    from .permissions import has_perm

    if not has_perm(request.user, c.PERM_DELETE):
        return fail("permission refusee", "forbidden", 403, required = c.PERM_DELETE)

    if questionnaire.attempts.exists():
        questionnaire.status = c.STATUS_ARCHIVED
        questionnaire.save(update_fields = ["status", "updated_at"])
        log(request.user, c.AUDIT_ARCHIVE, questionnaire, questionnaire = questionnaire,
            new = {"status": c.STATUS_ARCHIVED}, reason = "suppression avec tentatives existantes")
        return ok({"archived": True, "deleted": False,
                   "questionnaire": admin_questionnaire(questionnaire)})

    log(request.user, c.AUDIT_DELETE, ("Questionnaire", questionnaire.pk),
        old = {"title": questionnaire.title})
    questionnaire.delete()
    return ok({"archived": False, "deleted": True})


@api(("POST",), perm = c.PERM_CREATE)
@transaction.atomic
def duplicate(request, pk):
    """Duplique un questionnaire : nouveau brouillon, nouvelles cles stables."""
    source  = _questionnaire(pk)
    payload = body(request)

    copy = Questionnaire.objects.create(
        title       = payload.get("title") or f"{source.title} (copie)",
        description = source.description,
        created_by  = request.user,
        max_attempts           = source.max_attempts,
        cooldown_seconds       = source.cooldown_seconds,
        time_limit_seconds     = source.time_limit_seconds,
        attempt_expiry_seconds = source.attempt_expiry_seconds,
        allow_retry_after_pass = source.allow_retry_after_pass,
        allow_retry_after_fail = source.allow_retry_after_fail,
        answer_edit_mode       = source.answer_edit_mode,
        navigation_mode        = source.navigation_mode,
        allow_back             = source.allow_back,
        result_visibility      = dict(source.result_visibility or {}),
    )

    origin  = source.current_version or source.latest_version()
    version = create_version(copy, source = None, actor = request.user,
                             title = copy.title, description = copy.description)
    if origin:
        from .versioning import copy_questions

        copy_questions(origin, version)

    log(request.user, c.AUDIT_DUPLICATE, copy, questionnaire = copy,
        old = {"source": source.pk}, new = {"title": copy.title})
    return ok({"questionnaire": admin_questionnaire(copy, detail = True)}, status = 201)


@api(("POST",), perm = c.PERM_ARCHIVE)
def archive(request, pk):
    questionnaire = _questionnaire(pk)
    questionnaire.status = c.STATUS_ARCHIVED
    questionnaire.save(update_fields = ["status", "updated_at"])
    log(request.user, c.AUDIT_ARCHIVE, questionnaire, questionnaire = questionnaire,
        new = {"status": c.STATUS_ARCHIVED})
    return ok({"questionnaire": admin_questionnaire(questionnaire)})


@api(("POST",), perm = c.PERM_UPDATE)
def disable(request, pk):
    questionnaire = _questionnaire(pk)
    questionnaire.status = c.STATUS_DISABLED
    questionnaire.save(update_fields = ["status", "updated_at"])
    log(request.user, c.AUDIT_DISABLE, questionnaire, questionnaire = questionnaire,
        new = {"status": c.STATUS_DISABLED})
    return ok({"questionnaire": admin_questionnaire(questionnaire)})


@api(("POST",), perm = c.PERM_PUBLISH)
def reactivate(request, pk):
    """Reactive un questionnaire desactive, si une version publiee existe."""
    questionnaire = _questionnaire(pk)
    if questionnaire.current_version is None:
        return fail("aucune version publiee", "no_published_version", 409)

    questionnaire.status = c.STATUS_PUBLISHED
    questionnaire.save(update_fields = ["status", "updated_at"])
    log(request.user, c.AUDIT_PUBLISH, questionnaire, questionnaire = questionnaire,
        new = {"status": c.STATUS_PUBLISHED})
    return ok({"questionnaire": admin_questionnaire(questionnaire)})


@api(("POST",), perm = c.PERM_INVALIDATE)
@transaction.atomic
def invalidate(request, pk):
    """Invalide le questionnaire entier et toutes ses versions actives."""
    questionnaire = _questionnaire(pk)
    reason        = str(body(request).get("reason", ""))

    for version in questionnaire.versions.exclude(status = c.STATUS_INVALIDATED):
        invalidate_version(version, actor = request.user, reason = reason)

    questionnaire.status          = c.STATUS_INVALIDATED
    questionnaire.current_version = None
    questionnaire.save(update_fields = ["status", "current_version", "updated_at"])
    log(request.user, c.AUDIT_INVALIDATE, questionnaire, questionnaire = questionnaire,
        new = {"status": c.STATUS_INVALIDATED, "reason": reason})

    return ok({"questionnaire": admin_questionnaire(questionnaire, detail = True)})


# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #

@api(("GET", "POST"), perm = c.PERM_VIEW)
def versions(request, pk):
    questionnaire = _questionnaire(pk)

    if request.method == "GET":
        return ok({
            "versions": [admin_version(v) for v in questionnaire.versions.all()],
            "current":  questionnaire.current_version.version_number if questionnaire.current_version else None,
        })

    from .permissions import has_perm

    if not has_perm(request.user, c.PERM_MANAGE_VERSIONS):
        return fail("permission refusee", "forbidden", 403, required = c.PERM_MANAGE_VERSIONS)

    payload = body(request)
    source  = None
    if payload.get("from_version"):
        source = _version(pk, int(payload["from_version"]))

    version = create_version(
        questionnaire, source = source, actor = request.user,
        title = payload.get("title"), description = payload.get("description"),
        copy_content = get_bool(payload, "copy_content", True),
    )
    return ok({"version": admin_version(version, with_questions = True)}, status = 201)


@api(("GET", "PUT", "PATCH"), perm = c.PERM_VIEW)
def version_item(request, pk, number):
    version = _version(pk, number)

    if request.method == "GET":
        return ok({"version": admin_version(version, with_questions = True)})

    from .permissions import has_perm

    if not has_perm(request.user, c.PERM_UPDATE):
        return fail("permission refusee", "forbidden", 403, required = c.PERM_UPDATE)

    version.assert_editable()
    payload = body(request)

    for field in ("title", "description"):
        if field in payload:
            setattr(version, field, str(payload[field]))
    for field in ("valid_from", "valid_until"):
        if field in payload:
            setattr(version, field, _parse_dt(payload[field]))
    if "scoring_config" in payload:
        before = dict(version.scoring_config or {})
        version.scoring_config = validate_version_scoring(payload["scoring_config"])
        log(request.user, c.AUDIT_SCORING_CHANGE, version, questionnaire = version.questionnaire,
            old = before, new = version.scoring_config)

    version.save()
    log(request.user, c.AUDIT_UPDATE, version, questionnaire = version.questionnaire,
        new = {"title": version.title})
    return ok({"version": admin_version(version, with_questions = True)})


@api(("GET",), perm = c.PERM_VIEW)
def version_compare(request, pk):
    """GET ?from=1&to=3 — differences question par question."""
    left  = _version(pk, int(request.GET.get("from", 1)))
    right = _version(pk, int(request.GET.get("to", 1)))
    return ok({"diff": compare_versions(left, right)})


@api(("POST",), perm = c.PERM_PUBLISH)
def version_publish(request, pk, number):
    version = _version(pk, number)
    publish_version(version, actor = request.user)
    return ok({
        "version":       admin_version(version),
        "questionnaire": admin_questionnaire(version.questionnaire),
    })


@api(("POST",), perm = c.PERM_TEST)
def version_test(request, pk, number):
    version = _version(pk, number)
    set_version_test(version, actor = request.user)
    return ok({
        "version":       admin_version(version),
        "questionnaire": admin_questionnaire(version.questionnaire),
    })


@api(("POST",), perm = c.PERM_INVALIDATE)
def version_invalidate(request, pk, number):
    version = _version(pk, number)
    invalidate_version(version, actor = request.user, reason = str(body(request).get("reason", "")))
    return ok({"version": admin_version(version)})


@api(("POST",), perm = c.PERM_MANAGE_VERSIONS)
def version_restore(request, pk, number):
    source  = _version(pk, number)
    version = restore_version(source.questionnaire, source, actor = request.user)
    return ok({"version": admin_version(version, with_questions = True)}, status = 201)


@api(("GET",), perm = c.PERM_VIEW)
def version_preview(request, pk, number):
    """Previsualisation : exactement ce que verra l'utilisateur, sans corrige."""
    version = _version(pk, number)
    questions = list(version.questions.prefetch_related("options"))

    from .serializers import runner_question

    return ok({
        "version": admin_version(version),
        "preview": {
            "title":       version.title,
            "description": version.description,
            "questions":   [runner_question(q) for q in questions],
        },
    })


@api(("POST",), perm = c.PERM_UPDATE)
def version_editable(request, pk):
    """Rend une version modifiable, en la derivant si la courante est figee."""
    questionnaire = _questionnaire(pk)
    version       = editable_version(questionnaire, actor = request.user)
    return ok({"version": admin_version(version, with_questions = True)})


# --------------------------------------------------------------------------- #
# Questions et options
# --------------------------------------------------------------------------- #

@api(("POST",), perm = c.PERM_UPDATE)
def questions(request, pk, number):
    version  = _version(pk, number)
    question = create_question(version, body(request), actor = request.user)
    from .serializers import admin_question

    return ok({"question": admin_question(question)}, status = 201)


@api(("PUT", "PATCH", "DELETE"), perm = c.PERM_UPDATE)
def question_item(request, pk, number, question_id):
    version  = _version(pk, number)
    question = get_object_or_404(Question, pk = question_id, version = version)

    if request.method == "DELETE":
        delete_question(question, actor = request.user)
        return ok({"deleted": True})

    update_question(question, body(request), actor = request.user)
    from .serializers import admin_question

    return ok({"question": admin_question(question)})


@api(("POST",), perm = c.PERM_UPDATE)
def questions_reorder(request, pk, number):
    version = _version(pk, number)
    reorder_questions(version, body(request).get("order", []), actor = request.user)
    return ok({"version": admin_version(version, with_questions = True)})


@api(("POST",), perm = c.PERM_UPDATE)
def options(request, pk, number, question_id):
    version  = _version(pk, number)
    question = get_object_or_404(Question, pk = question_id, version = version)
    option   = add_option(question, body(request), actor = request.user)
    from .serializers import admin_option

    return ok({"option": admin_option(option)}, status = 201)


@api(("PUT", "PATCH", "DELETE"), perm = c.PERM_UPDATE)
def option_item(request, pk, number, question_id, option_id):
    version = _version(pk, number)
    option  = get_object_or_404(
        QuestionOption, pk = option_id, question_id = question_id, question__version = version
    )

    if request.method == "DELETE":
        delete_option(option, actor = request.user)
        return ok({"deleted": True})

    update_option(option, body(request), actor = request.user)
    from .serializers import admin_option

    return ok({"option": admin_option(option)})


# --------------------------------------------------------------------------- #
# Acces et visibilite
# --------------------------------------------------------------------------- #

@api(("GET", "PUT", "POST"), perm = c.PERM_VIEW)
def access(request, pk):
    questionnaire = _questionnaire(pk)

    if request.method == "GET":
        rules = questionnaire.access_rules.all()
        return ok({
            "access":     [admin_access_rule(r) for r in rules if r.kind == c.RULE_KIND_ACCESS],
            "visibility": [admin_access_rule(r) for r in rules if r.kind == c.RULE_KIND_VISIBILITY],
            "rule_types": dict(c.RULE_TYPES),
            "result_visibility": questionnaire.visibility_settings,
        })

    from .permissions import has_perm

    if not has_perm(request.user, c.PERM_MANAGE_ACCESS):
        return fail("permission refusee", "forbidden", 403, required = c.PERM_MANAGE_ACCESS)

    payload = body(request)
    if "access" in payload:
        set_access_rules(questionnaire, c.RULE_KIND_ACCESS, payload["access"], actor = request.user)
    if "visibility" in payload:
        set_access_rules(questionnaire, c.RULE_KIND_VISIBILITY, payload["visibility"], actor = request.user)
    if "result_visibility" in payload:
        questionnaire.result_visibility = {
            key: bool(payload["result_visibility"].get(key, default))
            for key, default in c.DEFAULT_RESULT_VISIBILITY.items()
        }
        questionnaire.save(update_fields = ["result_visibility", "updated_at"])

    # requete fraiche : le cache de prefetch date d'avant l'ecriture
    rules = QuestionnaireAccessRule.objects.filter(questionnaire = questionnaire) \
        .select_related("target_user", "badge")
    return ok({
        "access":     [admin_access_rule(r) for r in rules if r.kind == c.RULE_KIND_ACCESS],
        "visibility": [admin_access_rule(r) for r in rules if r.kind == c.RULE_KIND_VISIBILITY],
        "result_visibility": questionnaire.visibility_settings,
    })


# --------------------------------------------------------------------------- #
# Tentatives, resultats, audit
# --------------------------------------------------------------------------- #

@api(("GET",), perm = c.PERM_VIEW_ATTEMPTS)
def attempts(request, pk):
    questionnaire = _questionnaire(pk)
    queryset = QuestionnaireAttempt.objects.filter(questionnaire = questionnaire) \
        .select_related("user", "version")

    if request.GET.get("include_test") not in ("1", "true", "yes"):
        queryset = queryset.filter(is_test = False)
    if status := request.GET.get("status"):
        queryset = queryset.filter(status = status)
    if version_number := request.GET.get("version"):
        queryset = queryset.filter(version__version_number = version_number)

    return ok({"attempts": [attempt_summary(a, for_admin = True) for a in queryset[:500]]})


@api(("GET",), perm = c.PERM_VIEW_RESULTS)
def results(request, pk):
    questionnaire = _questionnaire(pk)
    queryset = QuestionnaireResult.objects.filter(questionnaire = questionnaire) \
        .select_related("user", "version", "attempt", "questionnaire")

    if request.GET.get("include_test") not in ("1", "true", "yes"):
        queryset = queryset.filter(is_test = False)

    return ok({
        "results": [
            {
                "id":         r.id,
                "user":       r.user.username,
                "user_id":    r.user_id,
                "attempt_id": r.attempt_id,
                "version":    r.version.version_number,
                "score":      str(r.score),
                "max_score":  str(r.max_score),
                "percentage": str(r.percentage),
                "passed":     r.passed,
                "level":      r.level,
                "is_test":    r.is_test,
                "computed_at": r.computed_at.isoformat(),
                "duration_seconds": r.duration_seconds,
            }
            for r in queryset[:500]
        ],
    })


@api(("GET",), perm = c.PERM_VIEW_ATTEMPTS)
def attempt_transcript_view(request, pk, attempt_id):
    attempt = get_object_or_404(
        QuestionnaireAttempt.objects.select_related("user", "version"),
        pk = attempt_id, questionnaire_id = pk,
    )
    return ok({"transcript": attempt_transcript(attempt)})


@api(("POST",), perm = c.PERM_INVALIDATE)
def attempt_invalidate(request, pk, attempt_id):
    attempt = get_object_or_404(QuestionnaireAttempt, pk = attempt_id, questionnaire_id = pk)
    invalidate_attempt(attempt, actor = request.user, reason = str(body(request).get("reason", "")))
    return ok({"attempt": attempt_summary(attempt, for_admin = True)})


@api(("GET",), perm = c.PERM_VIEW)
def audit(request, pk):
    questionnaire = _questionnaire(pk)
    entries = AuditLog.objects.filter(questionnaire = questionnaire).select_related("actor")[:300]
    return ok({"entries": [audit_entry(e) for e in entries]})


@api(("GET",), perm = c.PERM_VIEW_STATS)
def statistics(request, pk):
    """Statistiques de base ; la structure de donnees en autorise bien d'autres."""
    from django.db.models import Avg, Count, Q

    questionnaire = _questionnaire(pk)
    real = QuestionnaireAttempt.objects.filter(questionnaire = questionnaire, is_test = False)

    totals = real.aggregate(
        total       = Count("id"),
        completed   = Count("id", filter = Q(status = c.ATTEMPT_COMPLETED)),
        abandoned   = Count("id", filter = Q(status = c.ATTEMPT_ABANDONED)),
        expired     = Count("id", filter = Q(status = c.ATTEMPT_EXPIRED)),
        in_progress = Count("id", filter = Q(status = c.ATTEMPT_IN_PROGRESS)),
    )
    scores = QuestionnaireResult.objects.filter(questionnaire = questionnaire, is_test = False)

    return ok({
        "attempts": totals,
        "results": scores.aggregate(
            count       = Count("id"),
            passed      = Count("id", filter = Q(passed = True)),
            average     = Avg("percentage"),
            avg_seconds = Avg("duration_seconds"),
        ),
        "by_version": list(
            scores.values("version__version_number")
                  .annotate(count = Count("id"), average = Avg("percentage"))
                  .order_by("version__version_number")
        ),
    })


# --------------------------------------------------------------------------- #
# Badges
# --------------------------------------------------------------------------- #

@api(("GET", "POST"), perm = c.PERM_VIEW)
def badge_collection(request):
    if request.method == "GET":
        return ok({
            "badges": [
                {
                    "id": b.id, "code": b.code, "name": b.name,
                    "description": b.description, "icon": b.icon,
                    "criteria": b.criteria, "active": b.active,
                    "holders": b.holders.count(),
                }
                for b in Badge.objects.all()
            ],
        })

    from .permissions import has_perm

    if not has_perm(request.user, c.PERM_MANAGE_BADGES):
        return fail("permission refusee", "forbidden", 403, required = c.PERM_MANAGE_BADGES)

    payload = body(request)
    badge   = Badge.objects.create(
        code        = str(payload.get("code", "")).strip(),
        name        = str(payload.get("name", "")).strip(),
        description = str(payload.get("description", "")),
        icon        = str(payload.get("icon", "")),
        criteria    = payload.get("criteria") or {},
        active      = get_bool(payload, "active", True),
    )
    log(request.user, c.AUDIT_CREATE, badge, new = {"code": badge.code})
    return ok({"badge": {"id": badge.id, "code": badge.code}}, status = 201)


# --------------------------------------------------------------------------- #

def _parse_dt(value):
    if value in (None, ""):
        return None
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(str(value))
    if parsed is None:
        from .http import BadRequest

        raise BadRequest(f"date invalide: {value!r}", "invalid_datetime")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed
