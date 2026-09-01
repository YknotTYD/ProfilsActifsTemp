##porting.py
"""Export et import de questionnaires au format JSON.

Le document est portable : il ne contient aucune cle primaire, uniquement les
cles stables. Un questionnaire exporte depuis une instance peut donc etre
importe dans une autre sans collision, en conservant les conditions d'affichage
qui referencent les questions par leur cle stable.

L'import passe par les memes fonctions de creation que l'editeur : la
configuration, les reponses attendues et les conditions sont donc validees
exactement comme une saisie manuelle.
"""

from django.core.exceptions import ValidationError
from django.db             import transaction
from django.utils          import timezone

from . import constants as c
from .auditing   import log
from .conditions import validate_condition
from .editing    import validate_scoring, validate_version_scoring
from .models     import Badge, Question, QuestionOption, Questionnaire
from .question_types import ConfigError, get_type
from .versioning import create_version

FORMAT  = "jibjob.questionnaire"
VERSION = 1

QUESTION_FIELDS = ("order", "text", "description", "explanation", "type", "required",
                   "config", "expected_config", "scoring_config", "condition")
OPTION_FIELDS   = ("order", "text", "description", "value", "is_correct")

ATTEMPT_FIELDS = ("max_attempts", "cooldown_seconds", "time_limit_seconds",
                  "attempt_expiry_seconds", "allow_retry_after_pass",
                  "allow_retry_after_fail", "keep_previous_attempts")
ANSWER_FIELDS  = ("answer_edit_mode", "navigation_mode", "allow_back")


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

def _rules_document(questionnaire, kind: str) -> list[list[dict]]:
    """Regles d'acces en groupes, avec des references portables."""
    groups: dict[int, list] = {}
    for rule in questionnaire.access_rules.all():
        if rule.kind != kind:
            continue
        entry = {"rule_type": rule.rule_type, "negate": rule.negate}
        if rule.rule_type == c.RULE_ROLE:
            entry["role"] = rule.role
        elif rule.rule_type == c.RULE_BADGE:
            entry["badge_code"] = rule.badge.code if rule.badge else None
        elif rule.rule_type == c.RULE_USER:
            # l'identifiant n'a pas de sens ailleurs : on exporte le nom
            entry["username"] = rule.target_user.username if rule.target_user else None
        groups.setdefault(rule.group_index, []).append(entry)
    return [groups[key] for key in sorted(groups)]


def export_questionnaire(questionnaire, version = None) -> dict:
    """Document JSON complet d'un questionnaire et d'une de ses versions."""
    version = version or questionnaire.current_version or questionnaire.latest_version()
    if version is None:
        raise ValidationError("ce questionnaire n'a aucune version a exporter")

    return {
        "format":      FORMAT,
        "format_version": VERSION,
        "exported_at": timezone.now().isoformat(),
        "source": {
            "questionnaire_id": questionnaire.id,
            "version_number":   version.version_number,
            "status":           version.status,
        },
        "questionnaire": {
            "title":       questionnaire.title,
            "description": questionnaire.description,
            "attempt_rules": {f: getattr(questionnaire, f) for f in ATTEMPT_FIELDS},
            "answer_rules":  {f: getattr(questionnaire, f) for f in ANSWER_FIELDS},
            "result_visibility": questionnaire.visibility_settings,
            "access":     _rules_document(questionnaire, c.RULE_KIND_ACCESS),
            "visibility": _rules_document(questionnaire, c.RULE_KIND_VISIBILITY),
        },
        "content": {
            "title":          version.title,
            "description":    version.description,
            "scoring_config": version.scoring,
            "questions": [
                {
                    "stable_key": question.stable_key,
                    **{f: getattr(question, f) for f in QUESTION_FIELDS},
                    "options": [
                        {"stable_key": option.stable_key,
                         **{f: getattr(option, f) for f in OPTION_FIELDS},
                         "score": str(option.score) if option.score is not None else None}
                        for option in question.options.all()
                    ],
                }
                for question in version.questions.prefetch_related("options")
            ],
        },
    }


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #

class ImportError_(ValidationError):
    """Document d'import invalide."""


def validate_document(document) -> dict:
    """Verifie la forme du document avant d'ecrire quoi que ce soit."""
    if not isinstance(document, dict):
        raise ImportError_("le document doit etre un objet JSON")
    if document.get("format") != FORMAT:
        raise ImportError_(
            f"format inconnu: {document.get('format')!r} (attendu {FORMAT!r})")
    if int(document.get("format_version", 0)) > VERSION:
        raise ImportError_(
            f"document produit par une version plus recente ({document['format_version']})")

    content = document.get("content")
    if not isinstance(content, dict):
        raise ImportError_("section « content » manquante")

    questions = content.get("questions")
    if not isinstance(questions, list):
        raise ImportError_("« content.questions » doit etre une liste")

    seen = set()
    for index, question in enumerate(questions, 1):
        if not isinstance(question, dict):
            raise ImportError_(f"question {index} : objet attendu")
        if not question.get("text"):
            raise ImportError_(f"question {index} : enonce manquant")
        try:
            get_type(question.get("type"))
        except ConfigError as exc:
            raise ImportError_(f"question {index} : {exc}")
        key = question.get("stable_key")
        if key:
            if key in seen:
                raise ImportError_(f"question {index} : cle stable en double ({key})")
            seen.add(key)
    return document


@transaction.atomic
def import_questionnaire(document, *, actor = None, title = None) -> Questionnaire:
    """Cree un questionnaire en brouillon a partir d'un document exporte."""
    validate_document(document)

    meta    = document.get("questionnaire") or {}
    content = document["content"]

    questionnaire = Questionnaire(
        title       = title or meta.get("title") or content.get("title") or "Questionnaire importe",
        description = meta.get("description", ""),
        created_by  = actor if (actor and actor.is_authenticated) else None,
    )
    for field, value in (meta.get("attempt_rules") or {}).items():
        if field in ATTEMPT_FIELDS:
            setattr(questionnaire, field, value)
    for field, value in (meta.get("answer_rules") or {}).items():
        if field in ANSWER_FIELDS:
            setattr(questionnaire, field, value)
    if meta.get("result_visibility"):
        questionnaire.result_visibility = {
            key: bool(meta["result_visibility"].get(key, default))
            for key, default in c.DEFAULT_RESULT_VISIBILITY.items()
        }
    questionnaire.save()

    version = create_version(
        questionnaire, source = None, actor = actor,
        title       = content.get("title") or questionnaire.title,
        description = content.get("description", ""),
        scoring_config = validate_version_scoring(content.get("scoring_config") or {}),
    )

    # premiere passe : les questions, sans leurs conditions
    pending = []
    for index, payload in enumerate(content["questions"]):
        question = _import_question(version, payload, index)
        if payload.get("condition"):
            pending.append((question, payload["condition"]))

    # seconde passe : les conditions, une fois toutes les cles stables connues
    known = set(version.questions.values_list("stable_key", flat = True))
    for question, condition in pending:
        try:
            question.condition = validate_condition(condition, known)
        except ConfigError as exc:
            raise ImportError_(f"condition de « {question.text} » : {exc}")
        question.save(update_fields = ["condition"])

    _import_rules(questionnaire, meta, actor = actor)

    log(actor, c.AUDIT_CREATE, questionnaire, questionnaire = questionnaire,
        new = {"title": questionnaire.title, "questions": len(content["questions"])},
        imported = True)
    return questionnaire


def _import_question(version, payload: dict, index: int) -> Question:
    handler = get_type(payload["type"])

    question = Question(version = version, type = payload["type"])
    if payload.get("stable_key"):
        question.stable_key = str(payload["stable_key"])[:32]
    question.order       = payload.get("order", index)
    question.text        = str(payload["text"])
    question.description = str(payload.get("description", ""))
    question.explanation = str(payload.get("explanation", ""))
    question.required    = bool(payload.get("required", True))

    try:
        question.config          = handler.validate_config(payload.get("config") or {})
        question.scoring_config  = validate_scoring(payload.get("scoring_config") or {})
        question.expected_config = handler.validate_expected(
            payload.get("expected_config") or {}, question.config)
    except ConfigError as exc:
        raise ImportError_(f"question {index + 1} « {question.text[:40]} » : {exc}")
    question.save()

    fixed = getattr(handler, "fixed_options", ())
    options = payload.get("options") or [
        {"text": label, "value": value} for value, label in fixed
    ]
    for position, option in enumerate(options):
        if not option.get("text"):
            raise ImportError_(f"question {index + 1} : une reponse proposee n'a pas de libelle")
        QuestionOption.objects.create(
            question    = question,
            stable_key  = str(option["stable_key"])[:32] if option.get("stable_key")
                          else QuestionOption.stable_key.field.get_default(),
            order       = option.get("order", position),
            text        = str(option["text"])[:500],
            description = str(option.get("description", ""))[:500],
            value       = str(option.get("value", ""))[:100],
            is_correct  = bool(option.get("is_correct", False)),
            score       = option.get("score"),
        )
    return question


def _import_rules(questionnaire, meta: dict, *, actor = None):
    """Rejoue les regles d'acces, en ignorant ce qui n'existe pas ici."""
    from django.contrib.auth.models import User

    from .editing import set_access_rules

    for key, kind in (("access", c.RULE_KIND_ACCESS), ("visibility", c.RULE_KIND_VISIBILITY)):
        groups = []
        for group in meta.get(key) or []:
            resolved = []
            for rule in group:
                entry = {"rule_type": rule.get("rule_type"), "negate": rule.get("negate", False)}
                if entry["rule_type"] == c.RULE_ROLE:
                    entry["role"] = rule.get("role", "")
                elif entry["rule_type"] == c.RULE_BADGE:
                    if not Badge.objects.filter(code = rule.get("badge_code", "")).exists():
                        continue        # badge absent de cette instance
                    entry["badge_code"] = rule["badge_code"]
                elif entry["rule_type"] == c.RULE_USER:
                    user = User.objects.filter(username = rule.get("username", "")).first()
                    if user is None:
                        continue        # utilisateur absent de cette instance
                    entry["user_id"] = user.id
                resolved.append(entry)
            if resolved:
                groups.append(resolved)
        if groups:
            set_access_rules(questionnaire, kind, groups, actor = actor)
