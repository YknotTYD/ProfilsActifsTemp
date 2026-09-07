"""Chainon recherche -> videos, et lecture d'une video (sections 18 et 19).

**Ce module n'expose aucune route.** Ce qui est ici, c'est le chainon entre
la recherche et les videos :

    recherche -> profils correspondants -> videos de ces profils

`video_candidates` produit ce troisieme etage sous forme de queryset, donc
paginable et ordonnable en base.

Le feed vertical qui devait s'y brancher a ete retire au profit d'une grille
de profils paginee (points 3.2 et 3.4) : elle vit dans `mainapp`, et ses
anciennes adresses redirigent vers elle (voir `profils/urls.py`). Ce qui
reste ici est ce dont la recherche se sert, plus `playback`, qui dit comment
lire une video quelle que soit sa source.

La section 19 (une recherche `Rust` renvoyant profils **et** videos) utilise le
meme point d'entree : `videos_for_skills` part des competences associees aux
videos, `video_candidates` part des profils trouves.
"""

from django.db.models import Q

from . import constants as c
from .visibility import rank

def _visible_video_filter(viewer) -> Q:
    """Conditions de visibilite communes a toutes les lectures de videos."""
    audience = c.AUDIENCE_REGISTERED if (viewer and viewer.is_authenticated) \
               else c.AUDIENCE_ANONYMOUS
    allowed  = [value for value, _ in c.VISIBILITIES if audience >= rank(value)]

    return (
        Q(status__in = c.VISIBLE_VIDEO_STATUSES)
        & Q(visibility__in = allowed)
        & Q(profile__visibility__in = allowed)
        & Q(profile__visibility_config__videos_visibility__in = allowed)
        & Q(profile__search_config__appear_in_video_feed = True)
    )

def video_candidates(query, viewer = None):
    """Videos des profils correspondant a une recherche.

    Reutilise telle quelle la recherche de profils : memes filtres, memes
    regles de visibilite, meme exclusion des profils non recherchables. Le feed
    ne peut donc pas montrer la video d'un profil que la recherche cache.
    """
    from .models import ProfileVideo
    from .search import apply_filters, base_queryset

    profiles = apply_filters(base_queryset(viewer), query).values("pk")

    return (
        ProfileVideo.objects
        .filter(_visible_video_filter(viewer), profile__in = profiles)
        .select_related("profile", "profile__user")
        .prefetch_related("skill_links__skill")
        .order_by("-published_at", "-id")
    )

def videos_for_skills(skill_ids, viewer = None):
    """Videos portant l'une des competences demandees (section 19).

    Part de `ProfileVideoSkill` : une video "Je developpe une API Rust" est
    trouvable par `Rust` meme si son auteur n'a pas encore declare Rust dans
    ses competences de profil.
    """
    from .models import ProfileVideo

    if not skill_ids:
        return ProfileVideo.objects.none()

    return (
        ProfileVideo.objects
        .filter(_visible_video_filter(viewer), skill_links__skill_id__in = skill_ids)
        .distinct()
        .select_related("profile", "profile__user")
        .prefetch_related("skill_links__skill")
        .order_by("-published_at", "-id")
    )

_IFRAME_HINTS = ("/embed/", "player.vimeo.com", "youtube.com", "youtu.be", "dailymotion.com/embed")
_FILE_SUFFIXES = (".mp4", ".webm", ".ogg", ".ogv", ".mov", ".m4v")

def _youtube_embed(url: str) -> str:
    """`watch?v=ID` ou `youtu.be/ID` -> `youtube.com/embed/ID`. Sinon inchange."""
    import re
    match = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{6,})", url)
    return f"https://www.youtube.com/embed/{match.group(1)}" if match else url

def playback(source_type: str, file_url: str, video_id: int | None = None) -> tuple[str, str]:
    """(`mode`, `url`) pour lire une video : `mode` vaut `"iframe"` ou `"file"`.

    Heuristique volontairement simple : les donnees reelles sont des liens
    d'integration (YouTube/Vimeo). Un lien inconnu est suppose integrable
    plutot que servi en `<video>`, ce qui echouerait silencieusement sur une
    page distante.
    """
    url = (file_url or "").strip()
    low = url.lower()
    if source_type == c.VIDEO_SOURCE_FILE:
        from django.urls import reverse
        return ("file", reverse("p_video_file", args=[video_id]))

    if "youtube.com/watch" in low or "youtu.be/" in low or "/shorts/" in low:
        return ("iframe", _youtube_embed(url))
    if any(hint in low for hint in _IFRAME_HINTS):
        return ("iframe", url)
    if low.rsplit("?", 1)[0].endswith(_FILE_SUFFIXES):
        return ("file", url)
    return ("iframe", url)
