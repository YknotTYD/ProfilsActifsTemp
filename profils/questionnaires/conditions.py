"""Moteur de conditions d'affichage.

Une condition est un arbre JSON porte par `Question.condition` :

    {"op": "AND", "conditions": [
        {"question": "<stable_key>", "operator": "EQUALS", "value": "<option_key>"},
        {"op": "OR", "conditions": [...]}
    ]}

Les questions et les options sont referencees par leur cle stable, jamais par
leur cle primaire : une condition survit donc a la creation d'une nouvelle
version. L'evaluation est faite exclusivement cote serveur ; le frontend ne
recoit que la liste des questions visibles.
"""

from decimal import Decimal, InvalidOperation

from . import constants as c
from .question_types import ConfigError

class ConditionError(ConfigError):
    """Condition mal formee."""

def validate_condition(condition, known_keys: set[str], _depth: int = 0):
    """Valide un arbre de conditions. `known_keys` = cles stables disponibles."""
    if condition in (None, {}):
        return None
    if _depth > 10:
        raise ConditionError("condition trop profondement imbriquee")
    if not isinstance(condition, dict):
        raise ConditionError("une condition doit etre un objet")

    if "op" in condition:
        if condition["op"] not in c.LOGIC_OPERATORS:
            raise ConditionError(f"operateur logique invalide: {condition['op']!r}")
        children = condition.get("conditions")
        if not isinstance(children, list) or not children:
            raise ConditionError("un groupe doit contenir au moins une condition")
        return {
            "op":         condition["op"],
            "conditions": [validate_condition(child, known_keys, _depth + 1) for child in children],
        }

    key = condition.get("question")
    if not key:
        raise ConditionError("une condition simple doit referencer une question")
    if known_keys and str(key) not in known_keys:
        raise ConditionError(f"question inconnue dans une condition: {key!r}")

    operator = condition.get("operator")
    if operator not in c.CONDITION_OPERATORS:
        raise ConditionError(f"operateur invalide: {operator!r}")

    node = {"question": str(key), "operator": operator}
    if operator not in (c.OP_ANSWERED, c.OP_NOT_ANSWERED):
        if "value" not in condition:
            raise ConditionError(f"l'operateur {operator} exige une valeur")
        node["value"] = condition["value"]
    return node

def referenced_keys(condition) -> set[str]:
    """Cles stables de questions citees par une condition."""
    if not condition:
        return set()
    if "op" in condition:
        keys = set()
        for child in condition.get("conditions", []):
            keys |= referenced_keys(child)
        return keys
    return {str(condition["question"])}

def _condition_value(question, value, operator):
    """Valeur d'une reponse telle que le moteur de conditions la compare.

    Pour les types a options, on compare des cles stables d'options afin que la
    condition reste valable apres un changement de libelle ou de version.
    """
    handler = question.handler

    if handler.uses_options:
        numeric_ops = (c.OP_GT, c.OP_LT, c.OP_GTE, c.OP_LTE)
        if operator in numeric_ops and hasattr(handler, "numeric_value"):
            return handler.numeric_value(question, value)
        ids  = handler.comparable(question, value)
        keys = dict(question.options.values_list("id", "stable_key"))
        return [keys.get(i, str(i)) for i in ids]

    return handler.comparable(question, value)

def _coerce_pair(left, right):
    """Aligne deux operandes pour une comparaison ordonnee."""
    if isinstance(left, (int, float, Decimal)) or isinstance(right, (int, float, Decimal)):
        try:
            return Decimal(str(left)), Decimal(str(right))
        except (InvalidOperation, TypeError, ValueError):
            return str(left), str(right)
    return left, right

def _evaluate_leaf(node, question, answered: bool, value) -> bool:
    operator = node["operator"]

    if operator == c.OP_ANSWERED:
        return answered
    if operator == c.OP_NOT_ANSWERED:
        return not answered
    if not answered:
        return False

    actual   = _condition_value(question, value, operator)
    expected = node.get("value")

    if actual is None:
        return False

    if operator in (c.OP_EQUALS, c.OP_NOT_EQUALS):
        if isinstance(actual, list):
            wanted = expected if isinstance(expected, list) else [expected]
            equal  = sorted(str(a) for a in actual) == sorted(str(w) for w in wanted)
        else:
            left, right = _coerce_pair(actual, expected)
            equal = left == right
        return equal if operator == c.OP_EQUALS else not equal

    if operator in (c.OP_CONTAINS, c.OP_NOT_CONTAINS):
        if isinstance(actual, list):
            wanted   = expected if isinstance(expected, list) else [expected]
            contains = set(str(w) for w in wanted) <= set(str(a) for a in actual)
        else:
            contains = str(expected) in str(actual)
        return contains if operator == c.OP_CONTAINS else not contains

    if isinstance(actual, list):
        return False

    left, right = _coerce_pair(actual, expected)
    try:
        if operator == c.OP_GT:
            return left > right
        if operator == c.OP_LT:
            return left < right
        if operator == c.OP_GTE:
            return left >= right
        if operator == c.OP_LTE:
            return left <= right
    except TypeError:
        return False
    raise ConditionError(f"operateur non gere: {operator!r}")

def evaluate(condition, questions_by_key: dict, answers_by_key: dict, visible_keys: set[str]) -> bool:
    """Evalue un arbre de conditions.

    `answers_by_key` : cle stable -> valeur canonique.
    `visible_keys`   : cles des questions actuellement visibles ; la reponse a
                       une question devenue invisible est ignoree, ce qui evite
                       qu'une branche masquee continue d'influencer l'affichage.
    """
    if not condition:
        return True

    if "op" in condition:
        results = (
            evaluate(child, questions_by_key, answers_by_key, visible_keys)
            for child in condition["conditions"]
        )
        return all(results) if condition["op"] == c.LOGIC_AND else any(results)

    key      = condition["question"]
    question = questions_by_key.get(key)
    if question is None:
        return False

    usable  = key in visible_keys
    value   = answers_by_key.get(key) if usable else None
    answered = usable and question.handler.is_answered(value)
    return _evaluate_leaf(condition, question, answered, value)

def compute_visible(questions, answers_by_key: dict) -> list:
    """Retourne les questions visibles, dans l'ordre.

    Les questions sont parcourues dans leur ordre d'affichage : une condition
    qui reference une question posterieure la voit donc comme sans reponse, ce
    qui rend l'evaluation deterministe et exempte de cycle.
    """
    questions_by_key = {q.stable_key: q for q in questions}
    visible_keys: set[str] = set()
    visible: list = []

    for question in questions:
        if evaluate(question.condition, questions_by_key, answers_by_key, visible_keys):
            visible_keys.add(question.stable_key)
            visible.append(question)

    return visible
