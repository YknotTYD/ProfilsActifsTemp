"""Preparation du futur feed video (sections 18 et 19).

**Ce module n'expose aucun feed.** Il n'y a ni route, ni page, ni faux
carrousel : la section 18 demande explicitement de ne pas livrer un feed
factice. Ce qui est ici, c'est le chainon manquant entre la recherche et les
videos, ecrit et teste maintenant pour que le feed vertical n'ait plus qu'a
s'y brancher :

    recherche -> profils correspondants -> videos de ces profils -> feed

`video_candidates` produit ce troisieme etage sous forme de queryset, donc
paginable et ordonnable en base. Le jour ou le feed arrive, il ajoute une vue
et une pagination par curseur ; le calcul de "quelles videos" est deja la.

La section 19 (une recherche `Rust` renvoyant profils **et** videos) utilise le
meme point d'entree : `videos_for_skills` part des competences associees aux
videos, `video_candidates` part des profils trouves.
"""

from django.db.models import Q

from . import constants as c
from .visibility import rank

DASHBOARD_FEED_LIMIT = 50

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

def dashboard_feed(viewer):
    """Videos du feed vertical du tableau de bord (recruteur / admin).

    Une seule source : les `ProfileVideo` publiees et visibles du spectateur.
    L'ancien `mainapp.VideoLink` n'alimente plus le feed -- l'upload video est
    unifie sur la pile moderee, et une video envoyee par un candidat doit donc
    y apparaitre des sa publication (ce que l'ancien double circuit empechait).
    """
    from .models import ProfileVideo

    return (
        ProfileVideo.objects
        .filter(_visible_video_filter(viewer))
        .select_related("profile", "profile__user")
        .order_by("-published_at", "-id")[:DASHBOARD_FEED_LIMIT]
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

def dashboard_feed_items(viewer) -> list[dict]:
    """Feed du tableau de bord, pret a afficher.

    Chaque entree porte tout ce dont le gabarit a besoin -- lecture, identite
    de l'auteur (pseudo, nom, photo), compteurs, et l'etat de la reaction du
    spectateur -- sans que le gabarit ait a interroger la base.
    """
    from .models import ProfileVideoReaction

    videos = list(dashboard_feed(viewer))
    mine   = {}
    if viewer and getattr(viewer, "is_authenticated", False) and videos:
        mine = dict(
            ProfileVideoReaction.objects
            .filter(user = viewer, video__in = videos)
            .values_list("video_id", "reaction")
        )

    items = []
    for video in videos:
        mode, url = playback(video.source_type, video.file_url, video_id = video.id)
        profile   = video.profile
        reaction  = mine.get(video.id)
        items.append({
            "id":            video.id,
            "mode":          mode,
            "url":           url,
            "title":         video.title,
            "username":      profile.username,
            "display_name":  profile.full_name or profile.username,
            "photo_url":     profile.photo_url,
            "initials":      profile.initials,
            "liked":         reaction == ProfileVideoReaction.LIKE,
            "disliked":      reaction == ProfileVideoReaction.DISLIKE,
            "likes":         video.like_count,
            "views":         video.view_count,
        })
    return items
