##http.py
"""Couche HTTP JSON du module profils.

Le projet n'utilise pas de framework d'API. Les primitives d'enveloppe
(`ok`, `fail`, `body`, `get_int`, `get_bool`, `BadRequest`) existent deja dans
`questionnaires/http.py` : elles sont importees plutot que recopiees, pour que
les deux modules ne repondent pas un jour avec deux formats d'erreur
differents.

Seul le decorateur `api` est propre au module : il traduit les exceptions
metier des profils, que le decorateur des questionnaires ne connait pas.
"""

from functools import wraps

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from profils.questionnaires.http import BadRequest, body, fail, get_bool, get_int, ok

from .permissions import ProfileAccessDenied, has_perm

__all__ = ["BadRequest", "api", "body", "fail", "get_bool", "get_int", "ok"]


def api(methods = ("GET",), *, perm: str = None, login: bool = True):
    """Decorateur de vue JSON.

    `login = False` ouvre la vue aux visiteurs anonymes : c'est le cas des
    profils publics et de la recherche, ou l'anonymat est une audience, pas un
    refus. La visibilite reste verifiee a l'interieur de la vue.
    """

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
            if perm and not has_perm(request.user, perm):
                return fail("permission refusee", "forbidden", 403, required = perm)

            try:
                return view(request, *args, **kwargs)
            except ProfileAccessDenied as exc:
                return fail(exc.reason, exc.code, exc.status)
            except BadRequest as exc:
                return fail(exc.message, exc.code, 400)
            except ValidationError as exc:
                return fail("; ".join(exc.messages), "validation_error", 400)
            except ObjectDoesNotExist:
                return fail("ressource introuvable", "not_found", 404)

        return wrapper

    return decorator
