"""URL de fichier statique suffixee par sa date de modification.

En developpement, Django sert les fichiers statiques sans marqueur de version :
le navigateur garde donc l'ancienne feuille de style ou l'ancien script apres
une modification, et il faut vider le cache a la main pour voir le changement.

`{% vstatic "questionnaires.css" %}` ajoute la date du fichier a l'URL, qui
change des que le fichier change. Le navigateur telecharge alors la nouvelle
version de lui-meme.
"""

import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

@register.simple_tag
def vstatic(path: str) -> str:
    url = static(path)
    try:
        located = finders.find(path)
        stamp   = int(os.path.getmtime(located)) if located else None
    except (OSError, ValueError):
        stamp = None
    return f"{url}?v={stamp}" if stamp else url
