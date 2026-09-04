"""Application des regles de visibilite (section 11).

Trois reglages independants, qui repondent a trois questions distinctes :

    profil.visibility            qui peut ouvrir la page du profil ?
    ProfileVisibility.<section>  qui voit cette section une fois la page ouverte ?
    ProfileSearchSettings.searchable  le profil apparait-il dans les resultats ?

La regle qui evite les mauvaises surprises : **la visibilite effective d'une
section est la plus restrictive des deux**. Regler ses competences sur PUBLIC
ne les sort pas d'un profil PRIVATE. Sans cet arbitrage, rendre son profil
prive laisserait fuir toutes les sections restees ouvertes.

Tout passe par ce module. Aucune vue, aucun serialiseur ne decide seul.
"""

from . import constants as c
from .permissions import ProfileAccessDenied, can_see_private, owns

class PreviewViewer:
    """Visiteur simule, pour la previsualisation du profil public (section 22).

    Il ne represente personne : il repond seulement "quelle audience", et
    `audience_of` le reconnait avant toute autre regle. Son audience est
    plafonnee a celle d'un utilisateur inscrit, si bien qu'une
    previsualisation ne peut que restreindre ce qui est montre, jamais
    l'elargir.
    """

    def __init__(self, audience: int):
        self.audience = min(audience, c.AUDIENCE_REGISTERED)

    @property
    def is_authenticated(self) -> bool:
        return self.audience >= c.AUDIENCE_REGISTERED

def audience_of(viewer, profile, *, privileged: bool = None) -> int:
    """Audience du visiteur vis-a-vis de ce profil.

    Un administrateur autorise a consulter les profils prives est traite comme
    le proprietaire : c'est un choix explicite, pas un effet de bord.

    `privileged` court-circuite `can_see_private(viewer)`, qui ne depend que du
    visiteur et interroge ses roles en base : sur une page de resultats, il est
    calcule une seule fois par l'appelant et repasse ici a chaque profil plutot
    que d'etre recalcule une fois par ligne (voir `serializers.search_response`).
    """
    if isinstance(viewer, PreviewViewer):
        return viewer.audience
    if privileged is None:
        privileged = can_see_private(viewer)
    if owns(viewer, profile) or privileged:
        return c.AUDIENCE_OWNER
    if viewer and viewer.is_authenticated:
        return c.AUDIENCE_REGISTERED
    return c.AUDIENCE_ANONYMOUS

def rank(visibility: str) -> int:
    return c.VISIBILITY_RANKS.get(visibility, c.VISIBILITY_RANKS[c.VISIBILITY_PRIVATE])

def can_view_profile(viewer, profile) -> bool:
    """Le visiteur peut-il ouvrir cette page de profil ?"""
    if profile is None:
        return False
    return audience_of(viewer, profile) >= rank(profile.visibility)

def assert_can_view(viewer, profile):
    """Leve `ProfileAccessDenied` si la page n'est pas consultable.

    Un profil prive renvoie 404 et non 403 : repondre "interdit" confirmerait
    au passage que ce nom d'utilisateur possede un profil.
    """
    if not can_view_profile(viewer, profile):
        raise ProfileAccessDenied("profil introuvable", "not_found", 404)

def effective_section_visibility(profile, section: str) -> str:
    """Visibilite reellement appliquee a une section."""
    declared = profile.visibility_settings().of(section)
    return declared if rank(declared) >= rank(profile.visibility) else profile.visibility

def can_view_section(viewer, profile, section: str) -> bool:
    return audience_of(viewer, profile) >= rank(effective_section_visibility(profile, section))

def visible_sections(viewer, profile, *, privileged: bool = None) -> dict:
    """Carte section -> booleen, calculee une seule fois par rendu."""
    audience = audience_of(viewer, profile, privileged = privileged)
    return {
        section: audience >= rank(effective_section_visibility(profile, section))
        for section, _ in c.PROFILE_SECTIONS
    }

def can_view_video(viewer, video) -> bool:
    """Une video se voit si sa section, son statut et sa propre visibilite le permettent."""
    profile  = video.profile
    audience = audience_of(viewer, profile)

    if audience < rank(effective_section_visibility(profile, c.SECTION_VIDEOS)):
        return False
    if audience < rank(video.visibility):
        return False
    if video.is_published:
        return True
    return audience >= c.AUDIENCE_OWNER

def visible_videos(viewer, profile):
    """Videos de `profile` que `viewer` a le droit de voir.

    Le filtrage se fait en base ; la liste n'est pas ramenee puis triee en
    Python. Un visiteur ne recoit que des videos publiees, le proprietaire
    recoit tout ce qui n'est pas supprime.
    """
    from .models import ProfileVideo

    audience = audience_of(viewer, profile)
    if audience < rank(effective_section_visibility(profile, c.SECTION_VIDEOS)):
        return ProfileVideo.objects.none()

    queryset = profile.videos.exclude(status = c.VIDEO_DELETED)
    if audience >= c.AUDIENCE_OWNER:
        return queryset

    allowed = [
        value for value, _ in c.VISIBILITIES if audience >= rank(value)
    ]
    return queryset.filter(status__in = c.VISIBLE_VIDEO_STATUSES, visibility__in = allowed)
