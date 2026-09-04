"""Mise en forme des compteurs du feed video.

Le meme calcul existe en JavaScript dans `templates/feed.html` : le serveur
rend le compteur pour que la page reste lisible sans JS, le navigateur le
recalcule quand le visiteur aime une video. Les deux doivent produire
exactement le meme texte -- la regle est donc ecrite ici en toutes lettres,
et recopiee la-bas telle quelle.
"""

from django import template

register = template.Library()

_SCALES = ((1_000_000, "M"), (1_000, "k"))

@register.filter
def compact_count(value) -> str:
    """`999` -> `999` ; `1200` -> `1,2k` ; `1500000` -> `1,5M`.

    La virgule est le separateur decimal francais ; `1,0k` n'apporte rien et
    devient `1k`.
    """
    try:
        count = int(value)
    except (TypeError, ValueError):
        return "0"

    for limit, suffix in _SCALES:
        if count >= limit * 0.9995:
            scaled = f"{count / limit:.1f}".rstrip("0").rstrip(".")
            return f"{scaled.replace('.', ',')}{suffix}"

    return str(count)
