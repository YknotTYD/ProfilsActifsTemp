##http.py
"""Petite couche HTTP JSON.

Le projet n'utilise pas de framework d'API : ce module fournit le strict
necessaire (parsing, enveloppe d'erreur, verification de methode et de
permission) dans le meme esprit que `mainapp/api.py`.
"""

import json
from functools import wraps

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http            import JsonResponse

from .access         import AccessDenied
from .permissions    import has_perm
from .question_types import AnswerError, ConfigError


class BadRequest(Exception):
    def __init__(self, message: str, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.code    = code


def ok(payload = None, status: int = 200) -> JsonResponse:
    return JsonResponse(payload if payload is not None else {"ok": True}, status = status)


def fail(message: str, code: str = "error", status: int = 400, **extra) -> JsonResponse:
    return JsonResponse({"error": message, "code": code, **extra}, status = status)


def body(request) -> dict:
    """Corps JSON de la requete (ou formulaire, pour rester compatible)."""
    if request.content_type and "application/json" in request.content_type:
        if not request.body:
            return {}
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise BadRequest("corps JSON invalide", "invalid_json")
        if not isinstance(payload, dict):
            raise BadRequest("un objet JSON est attendu", "invalid_json")
        return payload
    return request.POST.dict()


def api(methods = ("GET",), *, perm: str = None, login: bool = True):
    """Decorateur de vue JSON.

    Traduit les exceptions metier en reponses JSON coherentes, ce qui evite de
    repeter la meme gestion d'erreur dans chaque endpoint.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            from .services import AttemptError, StaleWrite

            if request.method not in methods:
                return fail(
                    f"methode {request.method} non autorisee", "method_not_allowed", 405,
                    allowed = list(methods),
                )
            if login and not request.user.is_authenticated:
                return fail("authentification requise", "unauthenticated", 401)
            if perm and not has_perm(request.user, perm):
                return fail("permission refusee", "forbidden", 403, required = perm)

            try:
                return view(request, *args, **kwargs)
            except StaleWrite as exc:
                return fail(exc.reason, exc.code, exc.status, answer = {
                    "question_id":     exc.answer.question_id,
                    "value":           exc.answer.value,
                    "revision":        exc.answer.revision,
                    "client_sequence": exc.answer.client_sequence,
                })
            except AttemptError as exc:
                return fail(exc.reason, exc.code, exc.status)
            except AccessDenied as exc:
                return fail(exc.reason, exc.code, exc.status)
            except BadRequest as exc:
                return fail(exc.message, exc.code, 400)
            except (AnswerError, ConfigError) as exc:
                return fail(str(exc), "invalid_payload", 400)
            except ValidationError as exc:
                return fail("; ".join(exc.messages), "validation_error", 400)
            except ObjectDoesNotExist:
                return fail("ressource introuvable", "not_found", 404)

        return wrapper

    return decorator


def get_int(payload: dict, key: str, *, required: bool = True, default = None):
    if key not in payload or payload[key] in (None, ""):
        if required:
            raise BadRequest(f"champ manquant: {key}", "missing_field")
        return default
    try:
        return int(payload[key])
    except (TypeError, ValueError):
        raise BadRequest(f"champ invalide: {key}", "invalid_field")


def get_bool(payload: dict, key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)
