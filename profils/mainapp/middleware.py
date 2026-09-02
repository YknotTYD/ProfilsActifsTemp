from django.conf import settings


class NoCacheStaticFilesMiddleware:
    """In DEBUG, prevent browsers from caching /static/ files so local CSS/JS
    changes show up on the next reload instead of a stale cached copy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.DEBUG and request.path.startswith(settings.STATIC_URL):
            response["Cache-Control"] = "no-cache"
        return response
