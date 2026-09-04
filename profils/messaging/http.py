"""Couche HTTP JSON du module messaging, sur le meme modele que
`profiles/http.py` : les primitives d'enveloppe viennent de
`questionnaires/http.py`, seul le decorateur `api` est propre au module,
pour traduire `MessagingAccessDenied`.
"""

from functools import wraps

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from profils.questionnaires.http import BadRequest, body, fail, get_bool, get_int, ok

__all__ = ["BadRequest", "MessagingAccessDenied", "api", "body", "fail", "get_bool", "get_int", "ok"]

class MessagingAccessDenied(Exception):
    def __init__(self, reason: str, code: str = "access_denied", status: int = 403):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.status = status

def api(methods = ("GET",), *, login: bool = True):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return fail(
                    f"methode {request.method} non autorisee", "method_not_allowed", 405,
                    allowed = list(methods),
                )
            if login and not request.user.is_authenticated:
                return fail("authentification requise", "unauthenticated", 401)
            try:
                return view(request, *args, **kwargs)
            except MessagingAccessDenied as exc:
                return fail(exc.reason, exc.code, exc.status)
            except BadRequest as exc:
                return fail(exc.message, exc.code, 400)
            except ValidationError as exc:
                return fail("; ".join(exc.messages), "validation_error", 400)
            except ObjectDoesNotExist:
                return fail("ressource introuvable", "not_found", 404)

        return wrapper

    return decorator
