##matching.py
"""Preparation du rapprochement candidat / offre (section 26).

**Le matching n'est pas implemente ici**, et c'est voulu : il n'y a pas encore
de modele d'offre d'emploi dans le projet. Ce module prepare les deux moities
du futur rapprochement :

    profil candidat  <-- meme vocabulaire -->  offre d'emploi

`profile_features` extrait d'un profil le vecteur de caracteristiques
comparables (competences et niveaux, experience, localisation, contrats,
diplome, disponibilite). `query_from_offer` fait le chemin inverse : il traduit
les exigences d'une offre en `ProfileQuery`, c'est-a-dire dans la structure que
le moteur de recherche sait deja filtrer et classer.

C'est la l'interet de la preparation : le jour ou les offres existent, le
score de correspondance n'est pas un moteur de plus a ecrire, c'est
`ranking.relevance_expression` avec d'autres poids.
"""

from . import constants as c


def profile_features(profile) -> dict:
    """Caracteristiques comparables d'un profil.

    Volontairement plate et sans objet Django : c'est une photographie
    exploitable telle quelle par un futur calcul de score, un export ou un
    test.
    """
    skills = {
        row.skill.slug: {
            "skill_id":   row.skill_id,
            "name":       row.skill.name,
            "level":      row.level,
            "level_rank": row.level_rank,
            "years":      row.years_experience or 0,
        }
        for row in profile.skills.select_related("skill")
    }

    languages = {
        row.language.code: {"level": row.level, "level_rank": row.level_rank}
        for row in profile.languages.select_related("language")
    }

    degree_ranks = [
        c.degree_level_rank(row.degree_level)
        for row in profile.education.all() if row.degree_level
    ]

    return {
        "username":  profile.username,
        "skills":    skills,
        "languages": languages,
        "experience_months": profile.total_experience_months,
        "highest_degree_rank": max(degree_ranks) if degree_ranks else 0,
        "field":     profile.professional_field,
        "location":  {
            "city":    profile.location_city,
            "country": profile.location_country,
            "relocate": profile.willing_to_relocate,
            "radius_km": profile.mobility_radius_km,
        },
        "contract_types": profile.contract_type_codes(),
        "work_modes":     profile.work_modes,
        "availability":   profile.availability_status,
        "available_from": profile.available_from.isoformat() if profile.available_from else None,
        "is_available":   profile.is_available,
    }


def query_from_offer(offer: dict):
    """Traduit les exigences d'une offre en requete de recherche de profils.

    `offer` est un dictionnaire, pas un modele : les offres n'existent pas
    encore. Sa forme est celle que prendra naturellement une offre :

        {"skills": ["Java", "Docker"], "min_level": "INTERMEDIATE",
         "contract": "CDI", "field": "SOFTWARE", "country": "FR",
         "min_experience_years": 3, "languages": ["fr", "en"]}

    Le resultat se passe a `search.search()` sans adaptation.
    """
    from .search import ProfileQuery, _resolve_languages, _resolve_skills

    skill_ids, unknown = _resolve_skills(offer.get("skills") or [])

    return ProfileQuery(
        skill_ids      = skill_ids,
        unknown_skills = unknown,
        skills_mode    = offer.get("mode") or c.MATCH_MODE_AND,
        min_level      = offer.get("min_level"),
        min_years      = offer.get("min_years"),
        field          = offer.get("field"),
        country        = offer.get("country") or "",
        city           = offer.get("city") or "",
        contracts      = [offer["contract"]] if offer.get("contract") else (offer.get("contracts") or []),
        work_modes     = offer.get("work_modes") or [],
        available_only = offer.get("available_only", True),
        language_ids       = _resolve_languages(offer.get("languages") or []),
        min_language_level = offer.get("min_language_level"),
        min_degree_level   = offer.get("min_degree_level"),
        min_experience_years = offer.get("min_experience_years"),
    )
