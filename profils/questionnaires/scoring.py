##scoring.py
"""Moteur de scoring.

Separe de l'affichage et des modeles : il ne connait que des questions, des
valeurs canoniques et une configuration. Ajouter une strategie de scoring
revient a ajouter un mode dans `_effective_ratio`, sans toucher au reste.

Configuration d'une question (`Question.scoring_config`) :

    {"weight": 2, "correct_score": 1, "incorrect_score": -0.5,
     "unanswered_score": 0, "partial": true, "partial_mode": "proportional",
     "partial_threshold": 0.5}

Configuration d'une version (`QuestionnaireVersion.scoring_config`) :

    {"pass_threshold_percent": 60, "floor_negative": true,
     "levels": [{"name": "Bronze", "min_percent": 50}, ...]}
"""

from decimal import Decimal, ROUND_HALF_UP

from . import constants as c
from .conditions import compute_visible

ZERO   = Decimal("0")
CENT   = Decimal("100")
QUANT3 = Decimal("0.001")
QUANT2 = Decimal("0.01")


def _d(value) -> Decimal:
    return Decimal(str(value))


def _effective_ratio(ratio: float, scoring: dict) -> Decimal:
    """Convertit un ratio de justesse brut en ratio retenu pour le score."""
    ratio = _d(ratio)
    if not scoring.get("partial", True):
        return Decimal(1) if ratio >= 1 else ZERO

    mode = scoring.get("partial_mode", c.PARTIAL_PROPORTIONAL)
    if mode == c.PARTIAL_ALL_OR_NOTHING:
        return Decimal(1) if ratio >= 1 else ZERO
    if mode == c.PARTIAL_THRESHOLD:
        return Decimal(1) if ratio >= _d(scoring.get("partial_threshold", 0.5)) else ZERO
    return ratio


def score_question(question, value, answered: bool) -> dict:
    """Score une reponse unique.

    Retourne un dict decrivant entierement le calcul, ce qui permet de
    l'historiser tel quel dans `QuestionnaireResult.details`.
    """
    scoring = question.scoring
    weight  = _d(scoring["weight"])
    graded  = question.is_graded

    entry = {
        "question_id":  question.id,
        "stable_key":   question.stable_key,
        "type":         question.type,
        "weight":       str(weight),
        "graded":       graded,
        "answered":     answered,
    }

    if not graded:
        entry |= {"score": "0", "max_score": "0", "is_correct": None, "ratio": None}
        return entry

    max_score = weight * _d(scoring["correct_score"])

    if not answered:
        score = weight * _d(scoring["unanswered_score"])
        entry |= {
            "score":      str(score.quantize(QUANT3)),
            "max_score":  str(max_score.quantize(QUANT3)),
            "is_correct": False,
            "ratio":      "0",
        }
        return entry

    ratio, details = question.handler.evaluate(question, value)
    effective = _effective_ratio(ratio, scoring)
    score = weight * (
        _d(scoring["correct_score"]) * effective
        + _d(scoring["incorrect_score"]) * (Decimal(1) - effective)
    )

    entry |= {
        "score":      str(score.quantize(QUANT3)),
        "max_score":  str(max_score.quantize(QUANT3)),
        "is_correct": bool(effective >= 1),
        "ratio":      str(effective.quantize(QUANT3)),
        "raw_ratio":  str(_d(ratio).quantize(QUANT3)),
        "details":    details,
    }
    return entry


def _level_for(percentage: Decimal, version_scoring: dict) -> str:
    best, best_min = "", None
    for level in version_scoring.get("levels") or []:
        minimum = _d(level.get("min_percent", 0))
        if percentage >= minimum and (best_min is None or minimum > best_min):
            best, best_min = level.get("name", ""), minimum
    return best


def score_attempt(attempt) -> dict:
    """Calcule le score complet d'une tentative.

    Seules les questions visibles comptent : une question masquee par une
    condition, meme repondue avant qu'elle ne le devienne, est exclue du score
    tout en restant conservee dans les details a des fins d'audit.
    """
    version   = attempt.version
    questions = list(
        version.questions.prefetch_related("options").order_by("order", "id")
    )
    answers = {
        answer.question.stable_key: answer
        for answer in attempt.answers.select_related("question")
    }
    values  = {key: answer.value for key, answer in answers.items()}

    visible     = compute_visible(questions, values)
    visible_ids = {q.id for q in visible}

    entries   = []
    total     = ZERO
    max_total = ZERO

    for question in visible:
        answer   = answers.get(question.stable_key)
        value    = answer.value if answer else None
        answered = question.handler.is_answered(value)

        entry = score_question(question, value, answered)
        entry["answer_id"] = answer.id if answer else None
        entries.append(entry)

        total     += _d(entry["score"])
        max_total += _d(entry["max_score"])

    for question in questions:
        if question.id in visible_ids:
            continue
        answer = answers.get(question.stable_key)
        entries.append({
            "question_id": question.id,
            "stable_key":  question.stable_key,
            "type":        question.type,
            "graded":      False,
            "skipped":     "hidden_by_condition",
            "answer_id":   answer.id if answer else None,
            "score":       "0",
            "max_score":   "0",
            "is_correct":  None,
        })

    version_scoring = version.scoring
    if version_scoring.get("floor_negative", True) and total < ZERO:
        total = ZERO

    percentage = (
        (total / max_total * CENT).quantize(QUANT2, rounding = ROUND_HALF_UP)
        if max_total > ZERO else ZERO
    )
    threshold = _d(version_scoring.get("pass_threshold_percent", 60))

    return {
        "score":      total.quantize(QUANT3),
        "max_score":  max_total.quantize(QUANT3),
        "percentage": percentage,
        "passed":     bool(max_total > ZERO and percentage >= threshold),
        "level":      _level_for(percentage, version_scoring),
        "details":    {
            "questions":       entries,
            "visible_count":   len(visible),
            "graded_count":    sum(1 for e in entries if e.get("graded")),
            "correct_count":   sum(1 for e in entries if e.get("is_correct")),
            "threshold":       str(threshold),
            "scoring_config":  version_scoring,
        },
    }
