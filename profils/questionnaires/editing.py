"""Edition du contenu d'une version.

Chaque ecriture verifie d'abord que la version est bien modifiable, valide la
charge utile via le handler du type de question, puis journalise l'action. La
validation n'est jamais deleguee au frontend.
"""

from django.core.exceptions import ValidationError
from django.db             import transaction

from . import constants as c
from .auditing   import log, snapshot_fields
from .conditions import validate_condition
from .models     import Badge, Question, QuestionOption, QuestionnaireAccessRule
from .question_types import ConfigError, get_type

def validate_scoring(scoring: dict) -> dict:
    """Valide un bloc de scoring de question."""
    scoring = {**c.DEFAULT_QUESTION_SCORING, **(scoring or {})}

    for key in ("weight", "correct_score", "incorrect_score", "unanswered_score", "partial_threshold"):
        try:
            scoring[key] = float(scoring[key])
        except (TypeError, ValueError):
            raise ConfigError(f"scoring.{key} doit etre un nombre")

    if scoring["weight"] < 0:
        raise ConfigError("scoring.weight doit etre positif")
    if scoring["partial_mode"] not in c.PARTIAL_MODES:
        raise ConfigError(f"scoring.partial_mode invalide: {scoring['partial_mode']!r}")
    scoring["partial"] = bool(scoring["partial"])
    return scoring

def validate_version_scoring(scoring: dict) -> dict:
    scoring = {**c.DEFAULT_VERSION_SCORING, **(scoring or {})}
    try:
        scoring["pass_threshold_percent"] = float(scoring["pass_threshold_percent"])
    except (TypeError, ValueError):
        raise ConfigError("pass_threshold_percent doit etre un nombre")

    levels = scoring.get("levels") or []
    if not isinstance(levels, list):
        raise ConfigError("levels doit etre une liste")
    for level in levels:
        if not isinstance(level, dict) or "name" not in level:
            raise ConfigError("chaque niveau doit avoir un `name`")
        level["min_percent"] = float(level.get("min_percent", 0))

    scoring["levels"]         = levels
    scoring["floor_negative"] = bool(scoring.get("floor_negative", True))
    return scoring

def _next_order(version) -> int:
    last = version.questions.order_by("-order").first()
    return (last.order + 1) if last else 0

def _apply_question_payload(question, payload: dict, *, version):
    """Applique et valide une charge utile sur une question (creee ou existante)."""
    if "type" in payload:
        question.type = payload["type"]
    handler = get_type(question.type)

    for field in ("text", "description", "explanation"):
        if field in payload:
            setattr(question, field, str(payload[field] or ""))
    if "required" in payload:
        question.required = bool(payload["required"])
    if "order" in payload:
        question.order = int(payload["order"])

    if "config" in payload or not question.pk:
        question.config = handler.validate_config(payload.get("config", question.config or {}))

    if "scoring_config" in payload or not question.pk:
        question.scoring_config = validate_scoring(payload.get("scoring_config", question.scoring_config))

    if "expected_config" in payload or not question.pk:
        question.expected_config = handler.validate_expected(
            payload.get("expected_config", question.expected_config or {}), question.config
        )

    if "condition" in payload:
        known = set(
            version.questions.exclude(pk = question.pk).values_list("stable_key", flat = True)
        )
        question.condition = validate_condition(payload["condition"], known)

    if not question.text:
        raise ConfigError("l'enonce de la question est obligatoire")

@transaction.atomic
def create_question(version, payload: dict, *, actor = None) -> Question:
    version.assert_editable()

    question = Question(version = version, type = payload.get("type", ""))
    question.order = payload.get("order", _next_order(version))
    _apply_question_payload(question, payload, version = version)
    question.save()

    handler = question.handler
    fixed   = getattr(handler, "fixed_options", ())
    if fixed:
        _create_options(question, [
            {"text": label, "value": value, "order": index}
            for index, (value, label) in enumerate(fixed)
        ])
    elif payload.get("options"):
        _create_options(question, payload["options"])
    elif handler.uses_options and getattr(handler, "min_options", 0) and question.type == c.TYPE_SCALE:
        _create_scale_options(question)

    log(actor, c.AUDIT_QUESTION_CHANGE, question, questionnaire = version.questionnaire,
        new = {"text": question.text, "type": question.type}, operation = "create")
    return question

@transaction.atomic
def update_question(question, payload: dict, *, actor = None) -> Question:
    question.version.assert_editable()

    before = snapshot_fields(question, ("text", "type", "required", "order"))
    scoring_before = dict(question.scoring_config or {})

    _apply_question_payload(question, payload, version = question.version)
    question.save()

    if "options" in payload:
        _replace_options(question, payload["options"])

    log(actor, c.AUDIT_QUESTION_CHANGE, question, questionnaire = question.version.questionnaire,
        old = before, new = snapshot_fields(question, ("text", "type", "required", "order")),
        operation = "update")

    if scoring_before != (question.scoring_config or {}):
        log(actor, c.AUDIT_SCORING_CHANGE, question,
            questionnaire = question.version.questionnaire,
            old = scoring_before, new = question.scoring_config)
    return question

@transaction.atomic
def delete_question(question, *, actor = None):
    version = question.version
    version.assert_editable()

    dependents = [
        other.text for other in version.questions.exclude(pk = question.pk)
        if question.stable_key in _condition_keys(other.condition)
    ]
    if dependents:
        raise ValidationError(
            f"cette question conditionne d'autres questions: {dependents}"
        )

    log(actor, c.AUDIT_QUESTION_CHANGE, question, questionnaire = version.questionnaire,
        old = {"text": question.text, "type": question.type}, operation = "delete")
    question.delete()

def _condition_keys(condition) -> set[str]:
    from .conditions import referenced_keys

    return referenced_keys(condition)

@transaction.atomic
def reorder_questions(version, ordered_ids: list[int], *, actor = None):
    version.assert_editable()

    known = set(version.questions.values_list("id", flat = True))
    given = [int(i) for i in ordered_ids]
    if set(given) != known:
        raise ValidationError("la liste d'ordre doit contenir exactement les questions de la version")

    for index, question_id in enumerate(given):
        Question.objects.filter(pk = question_id).update(order = index)

    log(actor, c.AUDIT_QUESTION_CHANGE, version, questionnaire = version.questionnaire,
        new = {"order": given}, operation = "reorder")

def _validate_option_payload(payload: dict) -> dict:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise ConfigError("le libelle d'une option est obligatoire")
    return {
        "text":        text[:500],
        "description": str(payload.get("description", ""))[:500],
        "value":       str(payload.get("value", ""))[:100],
        "is_correct":  bool(payload.get("is_correct", False)),
        "score":       payload.get("score"),
    }

def _create_options(question, options: list[dict]):
    for index, raw in enumerate(options):
        data = _validate_option_payload(raw)
        QuestionOption.objects.create(
            question = question,
            order    = raw.get("order", index),
            **data,
        )

def _replace_options(question, options: list[dict]):
    """Reecrit le jeu d'options en conservant les cles stables fournies."""
    keep = []
    for index, raw in enumerate(options):
        data = _validate_option_payload(raw)
        option_id = raw.get("id")
        existing  = question.options.filter(pk = option_id).first() if option_id else None

        if existing is None:
            existing = QuestionOption(question = question)
            if raw.get("stable_key"):
                existing.stable_key = str(raw["stable_key"])[:32]

        for field, value in data.items():
            setattr(existing, field, value)
        existing.order = raw.get("order", index)
        existing.save()
        keep.append(existing.pk)

    question.options.exclude(pk__in = keep).delete()

def _create_scale_options(question):
    config = question.config or {}
    labels = config.get("labels") or {}
    step   = config.get("step", 1)
    _create_options(question, [
        {"text": str(labels.get(str(value), value)), "value": str(value), "order": index}
        for index, value in enumerate(range(config.get("min", 1), config.get("max", 5) + 1, step))
    ])

@transaction.atomic
def add_option(question, payload: dict, *, actor = None) -> QuestionOption:
    question.version.assert_editable()
    if not question.handler.uses_options:
        raise ValidationError(f"le type {question.type} n'accepte pas d'options")

    last   = question.options.order_by("-order").first()
    data   = _validate_option_payload(payload)
    option = QuestionOption.objects.create(
        question = question,
        order    = payload.get("order", (last.order + 1) if last else 0),
        **data,
    )
    log(actor, c.AUDIT_OPTION_CHANGE, option, questionnaire = question.version.questionnaire,
        new = {"text": option.text}, operation = "create", question = question.id)
    return option

@transaction.atomic
def update_option(option, payload: dict, *, actor = None) -> QuestionOption:
    option.question.version.assert_editable()

    before = snapshot_fields(option, ("text", "value", "is_correct", "order"))
    data   = _validate_option_payload({**{
        "text": option.text, "description": option.description, "value": option.value,
        "is_correct": option.is_correct, "score": option.score,
    }, **payload})

    for field, value in data.items():
        setattr(option, field, value)
    if "order" in payload:
        option.order = int(payload["order"])
    option.save()

    log(actor, c.AUDIT_OPTION_CHANGE, option,
        questionnaire = option.question.version.questionnaire,
        old = before, new = snapshot_fields(option, ("text", "value", "is_correct", "order")),
        operation = "update", question = option.question_id)
    return option

@transaction.atomic
def delete_option(option, *, actor = None):
    question = option.question
    question.version.assert_editable()

    log(actor, c.AUDIT_OPTION_CHANGE, option, questionnaire = question.version.questionnaire,
        old = {"text": option.text}, operation = "delete", question = question.id)
    option.delete()

@transaction.atomic
def set_access_rules(questionnaire, kind: str, groups: list[list[dict]], *, actor = None):
    """Remplace le jeu de regles `kind` par la liste de groupes fournie.

    `groups` est une liste de groupes ; les regles d'un meme groupe sont
    combinees par AND, les groupes entre eux par OR.
    """
    if kind not in dict(c.RULE_KINDS):
        raise ValidationError(f"type de regle inconnu: {kind!r}")

    before = [r.describe() for r in questionnaire.access_rules.filter(kind = kind)]
    questionnaire.access_rules.filter(kind = kind).delete()

    created = []
    for group_index, group in enumerate(groups or []):
        for raw in group:
            rule_type = raw.get("rule_type")
            if rule_type not in dict(c.RULE_TYPES):
                raise ValidationError(f"regle inconnue: {rule_type!r}")

            rule = QuestionnaireAccessRule(
                questionnaire = questionnaire,
                kind          = kind,
                group_index   = group_index,
                rule_type     = rule_type,
                negate        = bool(raw.get("negate", False)),
                role          = str(raw.get("role", "")),
            )
            if rule_type == c.RULE_USER:
                rule.target_user_id = raw.get("user_id")
            if rule_type == c.RULE_BADGE:
                badge = (
                    Badge.objects.filter(pk = raw["badge_id"]).first()
                    if raw.get("badge_id") else Badge.objects.filter(code = raw.get("badge_code", "")).first()
                )
                if badge is None:
                    raise ValidationError("badge introuvable pour une regle BADGE")
                rule.badge = badge

            rule.full_clean(exclude = ["questionnaire"])
            rule.save()
            created.append(rule)

    log(actor, c.AUDIT_ACCESS_CHANGE, questionnaire, questionnaire = questionnaire,
        old = before, new = [r.describe() for r in created], kind = kind)
    return created
