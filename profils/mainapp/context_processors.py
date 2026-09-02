import os

from django.conf import settings


def css_version(request):
    try:
        mtime = os.path.getmtime(settings.BASE_DIR / "static" / "style.css")
    except OSError:
        mtime = 0
    return {"css_version": int(mtime)}
