"""Modeles du systeme de questionnaires.

Le modele est normalise : questions, options et selections d'options sont de
vraies lignes, ce qui garde possibles les recherches, les statistiques et
l'analyse des reponses. Le JSON n'est utilise que pour ce qui est reellement
propre a un type de question (config, reponses attendues, scoring, conditions).
"""

from .questionnaire import (
    Questionnaire,
    QuestionnaireVersion,
    Question,
    QuestionOption,
    QuestionnaireAccessRule,
    new_stable_key,
)
from .attempt import (
    QuestionnaireAttempt,
    UserAnswer,
    UserAnswerSelection,
    QuestionnaireResult,
)
from .badge import Badge, UserBadge
from .audit import AuditLog

__all__ = [
    "Questionnaire",
    "QuestionnaireVersion",
    "Question",
    "QuestionOption",
    "QuestionnaireAccessRule",
    "QuestionnaireAttempt",
    "UserAnswer",
    "UserAnswerSelection",
    "QuestionnaireResult",
    "Badge",
    "UserBadge",
    "AuditLog",
    "new_stable_key",
]
