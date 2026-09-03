##versioning.py
"""Cycle de vie des versions.

Regles appliquees ici, et nulle part ailleurs :

  * une version n'est modifiable qu'en statut DRAFT et tant qu'aucune tentative
    ne s'y rattache ;
  * passer une version en TEST ou en PUBLISHED la fige definitivement ;
  * modifier un questionnaire fige revient a creer une nouvelle version, copie
    conforme de la precedente, avec les memes cles stables ;
  * restaurer une ancienne version cree une nouvelle version a partir d'elle :
    l'ancienne n'est jamais reecrite.
"""

from django.core.exceptions import ValidationError
from django.db             import transaction
from django.utils          import timezone

from . import constants as c
from .auditing import log
from .models   import Question, QuestionOption, QuestionnaireVersion


# --------------------------------------------------------------------------- #
# Creation / copie
# --------------------------------------------------------------------------- #

def next_version_number(questionnaire) -> int:
    latest = questionnaire.versions.order_by("-version_number").first()
    return (latest.version_number + 1) if latest else 1


@transaction.atomic
def create_version(questionnaire, *, source = None, actor = None, title = None,
                   description = None, scoring_config = None, copy_content = True):
    """Cree une nouvelle version DRAFT, eventuellement copiee depuis `source`."""
    source = source or questionnaire.current_version or questionnaire.latest_version()

    version = QuestionnaireVersion.objects.create(
        questionnaire  = questionnaire,
        version_number = next_version_number(questionnaire),
        status         = c.STATUS_DRAFT,
        title          = title if title is not None else (source.title if source else questionnaire.title),
        description    = description if description is not None else (
            source.description if source else questionnaire.description
        ),
        scoring_config = scoring_config if scoring_config is not None else (
            dict(source.scoring_config) if source else dict(c.DEFAULT_VERSION_SCORING)
        ),
        created_by   = actor if (actor and actor.is_authenticated) else None,
        derived_from = source,
    )

    if source and copy_content:
        copy_questions(source, version)

    log(
        actor, c.AUDIT_VERSION_CREATE, version,
        questionnaire = questionnaire,
        new = {"version_number": version.version_number},
        source_version = source.version_number if source else None,
    )
    return version


def copy_questions(source: QuestionnaireVersion, target: QuestionnaireVersion):
    """Duplique les questions et options en conservant les cles stables."""
    for question in source.questions.prefetch_related("options").all():
        clone = Question.objects.create(
            version         = target,
            stable_key      = question.stable_key,
            order           = question.order,
            text            = question.text,
            description     = question.description,
            explanation     = question.explanation,
            type            = question.type,
            required        = question.required,
            config          = dict(question.config or {}),
            expected_config = dict(question.expected_config or {}),
            scoring_config  = dict(question.scoring_config or {}),
            condition       = question.condition,
        )
        QuestionOption.objects.bulk_create([
            QuestionOption(
                question    = clone,
                stable_key  = option.stable_key,
                order       = option.order,
                text        = option.text,
                description = option.description,
                value       = option.value,
                is_correct  = option.is_correct,
                score       = option.score,
            )
            for option in question.options.all()
        ])


@transaction.atomic
def editable_version(questionnaire, *, actor = None):
    """Retourne une version modifiable, en en creant une au besoin.

    C'est la porte d'entree de l'editeur : tant que le brouillon courant n'a pas
    ete publie ni utilise, il est reutilise ; sinon une nouvelle version est
    derivee automatiquement.
    """
    draft = questionnaire.draft_version()
    if draft and draft.is_editable:
        return draft
    return create_version(questionnaire, source = draft or None, actor = actor)


# --------------------------------------------------------------------------- #
# Transitions
# --------------------------------------------------------------------------- #

@transaction.atomic
def publish_version(version, *, actor = None, carry_over = None):
    """Met une version en ligne.

    `carry_over` force le report des reponses des participants, ou l'empeche ;
    sans precision, le reglage du questionnaire decide.
    """
    if version.status == c.STATUS_INVALIDATED:
        raise ValidationError("une version invalidee ne peut pas etre publiee")
    if not version.questions.exists():
        raise ValidationError("impossible de publier une version sans question")

    questionnaire = version.questionnaire
    previous      = questionnaire.current_version

    if previous and previous.pk != version.pk and previous.status == c.STATUS_PUBLISHED:
        previous.status = c.STATUS_ARCHIVED
        previous.save(update_fields = ["status"])

    version.status       = c.STATUS_PUBLISHED
    version.published_at = timezone.now()
    version.published_by = actor if (actor and actor.is_authenticated) else None
    version.save(update_fields = ["status", "published_at", "published_by"])

    questionnaire.current_version = version
    questionnaire.status          = c.STATUS_PUBLISHED
    questionnaire.title           = version.title
    questionnaire.description     = version.description
    questionnaire.save(update_fields = ["current_version", "status", "title", "description", "updated_at"])

    log(
        actor, c.AUDIT_PUBLISH, version,
        questionnaire = questionnaire,
        old = {"previous_version": previous.version_number if previous else None},
        new = {"version_number": version.version_number},
    )

    # les participants deja passes ne repartent pas de zero
    wanted = questionnaire.carry_over_answers if carry_over is None else carry_over
    if wanted and previous is not None and previous.pk != version.pk:
        from .carryover import carry_over as run_carry_over

        version.carry_over_report = run_carry_over(questionnaire, version, actor = actor)
    else:
        version.carry_over_report = None

    return version


@transaction.atomic
def set_version_test(version, *, actor = None):
    """Bascule une version en mode TEST : elle se fige et devient testable."""
    if version.status not in (c.STATUS_DRAFT, c.STATUS_TEST):
        raise ValidationError("seule une version brouillon peut passer en test")
    if not version.questions.exists():
        raise ValidationError("impossible de tester une version sans question")

    version.status = c.STATUS_TEST
    version.save(update_fields = ["status"])

    questionnaire = version.questionnaire
    if questionnaire.status == c.STATUS_DRAFT:
        questionnaire.status = c.STATUS_TEST
        questionnaire.save(update_fields = ["status", "updated_at"])

    log(actor, c.AUDIT_TEST_MODE, version, questionnaire = questionnaire,
        new = {"status": c.STATUS_TEST})
    return version


@transaction.atomic
def invalidate_version(version, *, actor = None, reason: str = ""):
    """Invalide une version : plus aucune reponse ne sera acceptee.

    Les tentatives et resultats deja enregistres restent intacts et consultables.
    """
    version.status              = c.STATUS_INVALIDATED
    version.invalidated_at      = timezone.now()
    version.invalidated_by      = actor if (actor and actor.is_authenticated) else None
    version.invalidation_reason = reason
    version.save(update_fields = ["status", "invalidated_at", "invalidated_by", "invalidation_reason"])

    from .models import QuestionnaireAttempt

    open_attempts = QuestionnaireAttempt.objects.filter(
        version = version, status = c.ATTEMPT_IN_PROGRESS
    )
    invalidated = open_attempts.update(status = c.ATTEMPT_INVALIDATED)

    questionnaire = version.questionnaire
    if questionnaire.current_version_id == version.pk:
        questionnaire.current_version = None
        questionnaire.status          = c.STATUS_INVALIDATED
        questionnaire.save(update_fields = ["current_version", "status", "updated_at"])

    log(actor, c.AUDIT_INVALIDATE, version, questionnaire = questionnaire,
        new = {"status": c.STATUS_INVALIDATED, "reason": reason},
        invalidated_attempts = invalidated)
    return version


@transaction.atomic
def restore_version(questionnaire, source: QuestionnaireVersion, *, actor = None):
    """Restaure une ancienne version en en derivant une nouvelle."""
    version = create_version(questionnaire, source = source, actor = actor)
    log(actor, c.AUDIT_RESTORE, version, questionnaire = questionnaire,
        old = {"restored_from": source.version_number},
        new = {"version_number": version.version_number})
    return version


# --------------------------------------------------------------------------- #
# Comparaison
# --------------------------------------------------------------------------- #

_QUESTION_FIELDS = (
    "order", "text", "description", "explanation", "type", "required",
    "config", "expected_config", "scoring_config", "condition",
)
_OPTION_FIELDS = ("order", "text", "description", "value", "is_correct")


def _question_payload(question) -> dict:
    return {field: getattr(question, field) for field in _QUESTION_FIELDS}


def _option_payload(option) -> dict:
    payload = {field: getattr(option, field) for field in _OPTION_FIELDS}
    payload["score"] = str(option.score) if option.score is not None else None
    return payload


def _diff_options(old_question, new_question) -> dict:
    old_options = {o.stable_key: o for o in old_question.options.all()} if old_question else {}
    new_options = {o.stable_key: o for o in new_question.options.all()} if new_question else {}

    added   = [_option_payload(o) | {"stable_key": k} for k, o in new_options.items() if k not in old_options]
    removed = [_option_payload(o) | {"stable_key": k} for k, o in old_options.items() if k not in new_options]
    changed = []

    for key in set(old_options) & set(new_options):
        before, after = _option_payload(old_options[key]), _option_payload(new_options[key])
        fields = {f: {"from": before[f], "to": after[f]} for f in before if before[f] != after[f]}
        if fields:
            changed.append({"stable_key": key, "text": new_options[key].text, "fields": fields})

    return {"added": added, "removed": removed, "changed": changed}


def compare_versions(left: QuestionnaireVersion, right: QuestionnaireVersion) -> dict:
    """Compare deux versions question par question et option par option."""
    old_questions = {q.stable_key: q for q in left.questions.prefetch_related("options")}
    new_questions = {q.stable_key: q for q in right.questions.prefetch_related("options")}

    added = [
        {"stable_key": key, "text": q.text, "type": q.type,
         "options": [{"stable_key": o.stable_key, "text": o.text} for o in q.options.all()]}
        for key, q in new_questions.items() if key not in old_questions
    ]
    removed = [
        {"stable_key": key, "text": q.text, "type": q.type}
        for key, q in old_questions.items() if key not in new_questions
    ]
    changed = []

    for key in set(old_questions) & set(new_questions):
        before, after = _question_payload(old_questions[key]), _question_payload(new_questions[key])
        fields = {f: {"from": before[f], "to": after[f]} for f in before if before[f] != after[f]}
        options = _diff_options(old_questions[key], new_questions[key])
        if fields or any(options.values()):
            changed.append({
                "stable_key": key,
                "text":       new_questions[key].text,
                "fields":     fields,
                "options":    options,
            })

    meta = {}
    for field in ("title", "description", "scoring_config", "status"):
        before, after = getattr(left, field), getattr(right, field)
        if before != after:
            meta[field] = {"from": before, "to": after}

    return {
        "from": {
            "version_number": left.version_number,
            "status":         left.status,
            "created_at":     left.created_at.isoformat(),
            "created_by":     left.created_by.username if left.created_by else None,
        },
        "to": {
            "version_number": right.version_number,
            "status":         right.status,
            "created_at":     right.created_at.isoformat(),
            "created_by":     right.created_by.username if right.created_by else None,
        },
        "metadata":  meta,
        "questions": {"added": added, "removed": removed, "changed": changed},
        "summary": {
            "added":   len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }
