##snapshots.py
"""Instantanes des questions au moment ou l'utilisateur y repond.

Objectif (section 18) : pouvoir reconstituer exactement ce que l'utilisateur
avait devant lui, meme des annees plus tard et meme si la structure du systeme
evolue. Le snapshot complete le versioning, il ne le remplace pas : la version
reste la source de verite pour la correction et le scoring.

Ce qui est volontairement absent : les reponses attendues et les indicateurs de
justesse. Ils restent dans la version (protegee en suppression tant qu'une
tentative s'y rattache), ce qui evite tout risque de fuite de corrige via un
snapshot renvoye au client.
"""

SNAPSHOT_FORMAT = 1


def question_snapshot(question) -> dict:
    """Photographie d'une question et de ses options."""
    return {
        "format":      SNAPSHOT_FORMAT,
        "question_id": question.id,
        "stable_key":  question.stable_key,
        "order":       question.order,
        "text":        question.text,
        "description": question.description,
        "type":        question.type,
        "required":    question.required,
        "config":      dict(question.config or {}),
        "condition":   question.condition,
        "options": [
            {
                "id":          option.id,
                "stable_key":  option.stable_key,
                "order":       option.order,
                "text":        option.text,
                "description": option.description,
                "value":       option.value,
            }
            for option in question.options.all()
        ],
    }


def answer_snapshot(question) -> dict:
    """Snapshot stocke sur `UserAnswer`, enrichi du contexte de version."""
    version = question.version
    snapshot = question_snapshot(question)
    snapshot["version"] = {
        "id":             version.id,
        "version_number": version.version_number,
        "status":         version.status,
        "questionnaire":  version.questionnaire_id,
        "title":          version.title,
    }
    return snapshot


def rebuild_answer(answer) -> dict:
    """Reconstruit une reponse passee a partir de son seul snapshot.

    Utilise par l'audit et l'affichage des anciennes tentatives : ne touche
    jamais aux objets courants, uniquement aux donnees figees.
    """
    snapshot = answer.snapshot or {}
    handler  = answer.question.handler

    return {
        "question": {
            "id":          snapshot.get("question_id", answer.question_id),
            "stable_key":  snapshot.get("stable_key", answer.question_stable_key),
            "text":        snapshot.get("text", ""),
            "description": snapshot.get("description", ""),
            "type":        snapshot.get("type", ""),
            "required":    snapshot.get("required", False),
        },
        "version":  snapshot.get("version", {}),
        "value":    answer.value,
        "display":  handler.display(answer.question, answer.value, snapshot),
        "answered_at": answer.answered_at.isoformat() if answer.answered_at else None,
        "updated_at":  answer.updated_at.isoformat() if answer.updated_at else None,
        "options": snapshot.get("options", []),
        "selected_option_ids": list((answer.value or {}).get("option_ids") or []),
    }


def attempt_transcript(attempt) -> dict:
    """Reconstitution complete d'une tentative, telle qu'elle a ete vecue."""
    return {
        "attempt": {
            "id":             attempt.id,
            "user":           attempt.user.username,
            "questionnaire":  attempt.questionnaire_id,
            "version":        attempt.version.version_number,
            "status":         attempt.status,
            "is_test":        attempt.is_test,
            "started_at":     attempt.started_at.isoformat(),
            "completed_at":   attempt.completed_at.isoformat() if attempt.completed_at else None,
            "snapshot_format": SNAPSHOT_FORMAT,
        },
        "answers": [
            rebuild_answer(answer)
            for answer in attempt.answers.select_related("question").order_by("question__order", "id")
        ],
    }
