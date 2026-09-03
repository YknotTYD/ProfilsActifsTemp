##serializers.py
"""Conversion des modeles en structures JSON.

Deux familles de fonctions, volontairement distinctes, sur le modele de
`questionnaires/serializers.py` :

  * `owner_*` : vue complete, reglages de confidentialite compris ;
  * `public_*` : vue visiteur, construite **par omission**.

La nuance compte. Une section que le visiteur n'a pas le droit de voir est
absente de la reponse, pas presente avec un drapeau `visible: false` : une
donnee envoyee au navigateur est une donnee divulguee, quel que soit ce que le
frontend en fait ensuite.
"""

from . import constants as c
from . import ranking
from .permissions import can_see_private
from .visibility import audience_of, visible_sections


def _iso(value):
    return value.isoformat() if value else None


# --------------------------------------------------------------------------- #
# Briques
# --------------------------------------------------------------------------- #

def skill_reference(skill) -> dict:
    return {
        "id":       skill.id,
        "slug":     skill.slug,
        "name":     skill.name,
        "category": skill.category,
    }


def user_skill(row) -> dict:
    return {
        "skill":            skill_reference(row.skill),
        "level":            row.level,
        "level_label":      row.level_label,
        "level_rank":       row.level_rank,
        "years_experience": row.years_experience,
        "order":            row.order,
        "added_at":         _iso(row.added_at),
        "evidence_url":     row.evidence_url,
        "certification_id": row.evidence_certification_id,
    }


def _linked_skills(entry) -> list:
    return [skill_reference(link.skill) for link in entry.skill_links.all()]


def experience(row) -> dict:
    return {
        "id":            row.id,
        "title":         row.title,
        "company":       row.company,
        "description":   row.description,
        "start_date":    _iso(row.start_date),
        "end_date":      _iso(row.end_date),
        "is_current":    row.is_current,
        "location_city": row.location_city,
        "location_country": row.location_country,
        "contract_type": row.contract_type,
        "duration_months": row.duration_months,
        "order":         row.order,
        "skills":        _linked_skills(row),
    }


def education(row) -> dict:
    return {
        "id":             row.id,
        "institution":    row.institution,
        "degree":         row.degree,
        "degree_level":   row.degree_level,
        "field_of_study": row.field_of_study,
        "description":    row.description,
        "start_date":     _iso(row.start_date),
        "end_date":       _iso(row.end_date),
        "is_current":     row.is_current,
        "diploma_url":    row.diploma_url,
        "diploma_verified": row.diploma_verified,
        "order":          row.order,
        "skills":         _linked_skills(row),
    }


def certification(row) -> dict:
    return {
        "id":               row.id,
        "name":             row.name,
        "issuer":           row.issuer,
        "issued_on":        _iso(row.issued_on),
        "expires_on":       _iso(row.expires_on),
        "is_expired":       row.is_expired,
        "credential_id":    row.credential_id,
        "verification_url": row.verification_url,
        "order":            row.order,
        "skills":           _linked_skills(row),
    }


def project(row) -> dict:
    return {
        "id":          row.id,
        "title":       row.title,
        "description": row.description,
        "role":        row.role,
        "url":         row.url,
        "started_on":  _iso(row.started_on),
        "ended_on":    _iso(row.ended_on),
        "video_id":    row.video_id,
        "order":       row.order,
        "skills":      _linked_skills(row),
    }


def language(row) -> dict:
    return {
        "id":         row.id,
        "code":       row.language.code,
        "name":       row.language.name,
        "level":      row.level,
        "level_label": row.level_label,
        "level_rank": row.level_rank,
        "order":      row.order,
    }


def link(row) -> dict:
    return {
        "id":    row.id,
        "kind":  row.kind,
        "label": row.label or row.url,
        "url":   row.url,
        "order": row.order,
    }


def video(row, *, include_moderation: bool = False) -> dict:
    """`include_moderation` n'est jamais a `True` sur une route publique :
    le motif de refus et l'identite de qui a modere ne regardent que le
    proprietaire et les administrateurs (sections 1 et "Securite").
    """
    payload = {
        "id":               row.id,
        "title":            row.title,
        "description":      row.description,
        "source_type":      row.source_type,
        "file_url":         row.file_url,
        "thumbnail_url":    row.thumbnail_url,
        "duration_seconds": row.duration_seconds,
        "status":           row.status,
        "is_presentation":  row.is_presentation,
        "visibility":       row.visibility,
        "tags":             row.tags,
        "created_at":       _iso(row.created_at),
        "published_at":     _iso(row.published_at),
        "stats": {
            "views":  row.view_count,
            "likes":  row.like_count,
            "shares": row.share_count,
        },
        "skills": _linked_skills(row),
    }
    if include_moderation:
        payload.update({
            "rejection_reason":     row.rejection_reason,
            "moderated_at":         _iso(row.moderated_at),
            "moderated_by":         row.moderated_by.username if row.moderated_by_id else None,
            "replaces":             row.replaces_id,
            "requires_user_action": row.requires_user_action,
        })
    return payload


# --------------------------------------------------------------------------- #
# Profil
# --------------------------------------------------------------------------- #

def identity(profile) -> dict:
    """Entete du profil : toujours visible des lors que la page est accessible."""
    name = profile.full_name
    return {
        "username":   profile.username,
        "full_name":  name,
        "initials":   "".join(part[0] for part in name.split()[:2]).upper(),
        "first_name": profile.user.first_name,
        "last_name":  profile.user.last_name,
        "headline":   profile.headline,
        "summary":    profile.summary,
        "photo_url":    profile.photo_url,
        "cover_url":    profile.cover_url,
        "cover_color":  profile.cover_color or c.DEFAULT_COVER_COLOR,
        "location": {
            "city":    profile.location_city,
            "region":  profile.location_region,
            "country": profile.location_country,
            "label":   profile.location_label,
        },
        "professional_field": profile.professional_field,
        "professional_field_label": dict(c.PROFESSIONAL_FIELDS).get(profile.professional_field, ""),
        "total_experience_months": profile.total_experience_months,
        "total_experience_years":  profile.total_experience_years,
        "url":        f"/profile/{profile.username}/",
        "updated_at": _iso(profile.updated_at),
    }


def availability(profile) -> dict:
    return {
        "status":       profile.availability_status,
        "status_label": dict(c.AVAILABILITY_STATUSES).get(profile.availability_status, ""),
        "is_available": profile.is_available,
        "available_from": _iso(profile.available_from),
        "contract_types": profile.contract_type_codes(),
        "work_modes":     profile.work_modes,
        "willing_to_relocate": profile.willing_to_relocate,
        "mobility_radius_km":  profile.mobility_radius_km,
        "mobility_note":       profile.mobility_note,
    }


def public_profile(profile, viewer) -> dict:
    """Profil tel que `viewer` a le droit de le voir.

    Les sections interdites ne sont pas seulement vides : elles ne figurent pas
    dans la reponse. `sections` dit lesquelles ont ete servies, pour que
    l'interface puisse afficher "section masquee par son proprietaire" sans
    avoir a deviner.
    """
    from .visibility import visible_videos

    allowed = visible_sections(viewer, profile)
    payload = {
        "profile":  identity(profile),
        "sections": allowed,
        "is_owner": audience_of(viewer, profile) >= c.AUDIENCE_OWNER,
        "visibility": profile.visibility,
    }

    if allowed[c.SECTION_SKILLS]:
        payload["skills"] = [user_skill(row) for row in profile.skills.select_related("skill")]
    if allowed[c.SECTION_EXPERIENCES]:
        payload["experiences"] = [
            experience(row) for row in
            profile.experiences.prefetch_related("skill_links__skill")
        ]
    if allowed[c.SECTION_EDUCATION]:
        payload["education"] = [
            education(row) for row in
            profile.education.prefetch_related("skill_links__skill")
        ]
    if allowed[c.SECTION_CERTIFICATIONS]:
        payload["certifications"] = [
            certification(row) for row in
            profile.certifications.prefetch_related("skill_links__skill")
        ]
    if allowed[c.SECTION_LANGUAGES]:
        payload["languages"] = [
            language(row) for row in profile.languages.select_related("language")
        ]
    if allowed[c.SECTION_PROJECTS]:
        payload["projects"] = [
            project(row) for row in profile.projects.prefetch_related("skill_links__skill")
        ]
    if allowed[c.SECTION_LINKS]:
        payload["links"] = [link(row) for row in profile.links.all()]
    if allowed[c.SECTION_AVAILABILITY]:
        payload["availability"] = availability(profile)
    if allowed[c.SECTION_VIDEOS]:
        payload["videos"] = [
            video(row) for row in
            visible_videos(viewer, profile).prefetch_related("skill_links__skill")
        ]

    return payload


def owner_profile(profile) -> dict:
    """Profil complet, du point de vue de son proprietaire."""
    payload = public_profile(profile, profile.user)
    payload["privacy"] = {
        "profile_visibility": profile.visibility,
        "sections":           profile.visibility_settings().as_dict(),
        "search":             search_settings(profile),
    }
    return payload


def search_settings(profile) -> dict:
    settings = profile.search_settings()
    return {
        "searchable":                   settings.searchable,
        "appear_in_video_feed":         settings.appear_in_video_feed,
        "show_availability_in_results": settings.show_availability_in_results,
        "contactable_by_recruiters":    settings.contactable_by_recruiters,
    }


# --------------------------------------------------------------------------- #
# Resultats de recherche (section 13)
# --------------------------------------------------------------------------- #

def search_card(profile, query, viewer = None, *, top_skills: int = 6, privileged: bool = None) -> dict:
    """Carte de resultat.

    Les memes regles de visibilite s'appliquent qu'ailleurs : une carte ne peut
    pas montrer des competences que la page du profil masquerait. Un profil est
    trouvable sans etre entierement lisible.

    `privileged` vient de `search_response`, qui le calcule une seule fois pour
    toute la page plutot que de laisser chaque carte reinterroger les roles du
    visiteur en base.
    """
    allowed = visible_sections(viewer, profile, privileged = privileged)
    settings = profile.search_settings()

    card = {
        "username":  profile.username,
        "full_name": profile.full_name,
        "initials":  "".join(part[0] for part in profile.full_name.split()[:2]).upper(),
        "headline":  profile.headline,
        "photo_url": profile.photo_url,
        "location":  profile.location_label,
        "professional_field": profile.professional_field,
        "total_experience_years": profile.total_experience_years,
        "url":       f"/profile/{profile.username}/",
        "relevance": getattr(profile, "relevance", 0),
        "match": {
            "skills":    getattr(profile, "matched_skill_count", 0),
            "requested": len(query.skill_ids),
            "languages": getattr(profile, "matched_language_count", 0),
        },
        "score_breakdown": ranking.score_breakdown(profile, query),
        # miniature du futur feed video (section 13) : la cle existe des
        # maintenant pour que la carte n'ait pas a changer de forme plus tard.
        "video_thumbnail": None,
        "has_video":       bool(getattr(profile, "has_video", 0)),
    }

    if allowed[c.SECTION_SKILLS]:
        requested = set(query.skill_ids)
        rows = list(profile.skills.all())
        # les competences demandees d'abord, puis les plus solides
        rows.sort(key = lambda row: (row.skill_id not in requested, -row.level_rank, row.order))
        card["skills"] = [user_skill(row) for row in rows[:top_skills]]
        card["skill_count"] = len(rows)

    if allowed[c.SECTION_AVAILABILITY] and settings.show_availability_in_results:
        card["availability"] = {
            "status":       profile.availability_status,
            "status_label": dict(c.AVAILABILITY_STATUSES).get(profile.availability_status, ""),
            "is_available": profile.is_available,
            "contract_types": profile.contract_type_codes(),
            "work_modes":   profile.work_modes,
        }

    return card


def search_response(result: dict, query, viewer = None) -> dict:
    # calcule une fois pour toute la page : sans ca, chaque carte relance une
    # requete de roles pour le meme visiteur (voir `search_card`).
    privileged = can_see_private(viewer)
    return {
        "results": [
            search_card(profile, query, viewer, privileged = privileged)
            for profile in result["profiles"]
        ],
        "pagination": result["pagination"],
        "query":      result["query"],
    }


# --------------------------------------------------------------------------- #
# Vocabulaire, pour l'interface
# --------------------------------------------------------------------------- #

def meta() -> dict:
    """Toutes les listes de choix, pour que le frontend n'en code aucune en dur."""
    def pairs(choices):
        return [{"value": value, "label": label} for value, label in choices]

    return {
        "skill_levels":     pairs(c.SKILL_LEVELS),
        "skill_categories": pairs(c.SKILL_CATEGORIES),
        "fields":           pairs(c.PROFESSIONAL_FIELDS),
        "availability":     pairs(c.AVAILABILITY_STATUSES),
        "contract_types":   pairs(c.CONTRACT_TYPES),
        "work_modes":       pairs(c.WORK_MODES),
        "visibilities":     pairs(c.VISIBILITIES),
        "sections":         pairs(c.PROFILE_SECTIONS),
        "language_levels":  pairs(c.LANGUAGE_LEVELS),
        "degree_levels":    pairs(c.DEGREE_LEVELS),
        "link_kinds":       pairs(c.LINK_KINDS),
        "video_statuses":   pairs(c.VIDEO_STATUSES),
        "match_modes":      pairs(c.MATCH_MODES),
        "sort_options":     pairs(c.SORT_OPTIONS),
        "page_size":        {"default": c.DEFAULT_PAGE_SIZE, "max": c.MAX_PAGE_SIZE},
    }
