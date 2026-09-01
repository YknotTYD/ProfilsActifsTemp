##auditing.py
"""Ecriture du journal d'audit.

Un point d'entree unique afin qu'aucune action importante ne puisse etre
enregistree de facon incoherente.
"""

from .models import AuditLog


def log(actor, action: str, obj, *, questionnaire = None, old = None, new = None, **metadata):
    """Enregistre une action.

    `obj` peut etre une instance de modele ou un couple (type, identifiant).
    """
    if isinstance(obj, tuple):
        object_type, object_id = obj
    else:
        object_type, object_id = obj.__class__.__name__, obj.pk

    if questionnaire is None:
        questionnaire = getattr(obj, "questionnaire", None)
        if questionnaire is None and hasattr(obj, "version"):
            questionnaire = getattr(obj.version, "questionnaire", None)

    return AuditLog.objects.create(
        actor         = actor if (actor and actor.is_authenticated) else None,
        action        = action,
        object_type   = str(object_type),
        object_id     = str(object_id),
        questionnaire = questionnaire,
        old_value     = old,
        new_value     = new,
        metadata      = metadata or {},
    )


def snapshot_fields(instance, fields) -> dict:
    """Photographie d'un sous-ensemble de champs, pour `old`/`new`."""
    result = {}
    for field in fields:
        value = getattr(instance, field, None)
        result[field] = value if isinstance(value, (str, int, float, bool, list, dict, type(None))) else str(value)
    return result
