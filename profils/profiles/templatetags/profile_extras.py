"""Filtres de presentation des profils.

L'API renvoie des dates ISO et des durees en secondes : ce sont les bonnes
valeurs a transmettre, mais pas celles a afficher. La mise en forme reste donc
cote presentation, et le serialiseur n'a pas a connaitre la langue de
l'interface.

`{% load versioned_static %}` reste celui des questionnaires : les
bibliotheques de balises sont partagees par tout le projet.
"""

from django import template
from django.utils.dateparse import parse_date

register = template.Library()

_MONTHS = (
    "janv.", "fevr.", "mars", "avril", "mai", "juin",
    "juil.", "aout", "sept.", "oct.", "nov.", "dec.",
)

@register.filter
def month_year(value) -> str:
    """`2020-01-01` -> `janv. 2020`."""
    if not value:
        return ""
    date = parse_date(value) if isinstance(value, str) else value
    if date is None:
        return str(value)
    return f"{_MONTHS[date.month - 1]} {date.year}"

@register.filter
def period(entry) -> str:
    """Periode d'une entree de parcours, `en cours` comprise."""
    start = month_year(entry.get("start_date") or entry.get("started_on"))
    if entry.get("is_current"):
        return f"{start} — aujourd'hui"
    end = month_year(entry.get("end_date") or entry.get("ended_on"))
    if start and end:
        return f"{start} — {end}"
    return start or end or ""

@register.filter
def duration_months(months) -> str:
    """`30` -> `2 ans 6 mois`."""
    try:
        months = int(months)
    except (TypeError, ValueError):
        return ""
    years, rest = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} an{'s' if years > 1 else ''}")
    if rest or not years:
        parts.append(f"{rest} mois")
    return " ".join(parts)

@register.filter
def duration_seconds(seconds) -> str:
    """`58` -> `0:58`."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    return f"{seconds // 60}:{seconds % 60:02d}"

@register.filter
def bars(rank) -> range:
    """Quatre crans, pour dessiner un niveau sans avoir a le lire."""
    return range(1, 5)

@register.filter
def dictkey(mapping, key):
    """Libelle d'un code, en retombant sur le code lui-meme s'il est inconnu."""
    return (mapping or {}).get(key, key)
