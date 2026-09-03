##search.py
"""Moteur de recherche de profils (sections 12 a 14).

Tout se passe en base. Les filtres sont des `WHERE`, le score est une
expression annotee, le tri et la pagination sont un `ORDER BY` et un `LIMIT` :
a aucun moment l'ensemble des profils n'est ramene en memoire pour etre trie
ou filtre ensuite. C'est ce qui permet a la recherche de tenir avec beaucoup de
profils, et c'est ce que la section 28 demande explicitement.

Deux garde-fous appliques avant tout le reste, dans `base_queryset` :

  * un profil non `searchable` n'apparait jamais, pour personne, y compris
    pour un administrateur : le drapeau est un choix de l'utilisateur, pas une
    permission ;
  * la visibilite du profil est comparee a l'audience du visiteur.

Combinaison des competences : en `AND`, un `.filter()` par competence, ce qui
produit une jointure distincte par competence et exige donc qu'elles soient
toutes presentes. En `OR`, un seul `__in`.
"""

from django.core.paginator import Paginator

from profils.questionnaires.http import BadRequest

from . import constants as c
from . import ranking
from .skills import find_skill


class ProfileQuery:
    """Criteres de recherche valides.

    Le constructeur n'accepte que des valeurs deja verifiees ; `from_params`
    est le seul point d'entree depuis une requete HTTP. Rien de ce que le
    client envoie n'est repris tel quel.
    """

    def __init__(self, **kwargs):
        self.skill_ids      = kwargs.get("skill_ids") or []
        self.unknown_skills = kwargs.get("unknown_skills") or []
        self.skills_mode    = kwargs.get("skills_mode") or c.MATCH_MODE_AND
        self.min_level      = kwargs.get("min_level")
        self.min_years      = kwargs.get("min_years")

        self.field    = kwargs.get("field")
        self.country  = kwargs.get("country") or ""
        self.city     = kwargs.get("city") or ""
        self.text     = kwargs.get("text") or ""

        self.availability   = kwargs.get("availability") or []
        self.available_only = bool(kwargs.get("available_only"))
        self.contracts      = kwargs.get("contracts") or []
        self.work_modes     = kwargs.get("work_modes") or []

        self.language_ids        = kwargs.get("language_ids") or []
        self.min_language_level  = kwargs.get("min_language_level")
        self.min_degree_level    = kwargs.get("min_degree_level")
        self.education_field     = kwargs.get("education_field") or ""
        self.min_experience_years = kwargs.get("min_experience_years")

        self.sort      = kwargs.get("sort") or c.SORT_RELEVANCE
        self.page      = kwargs.get("page") or 1
        self.page_size = kwargs.get("page_size") or c.DEFAULT_PAGE_SIZE
        self.weights   = kwargs.get("weights") or {}

    # ------------------------------------------------------------------ #

    @classmethod
    def from_params(cls, params) -> "ProfileQuery":
        """Construit une requete a partir des parametres GET.

        Accepte les deux ecritures courantes : `?skill=java&skill=docker` et
        `?skills=java,docker`.
        """
        skill_ids, unknown = _resolve_skills(_multi(params, "skill", "skills"))
        language_ids       = _resolve_languages(_multi(params, "language", "languages"))

        return cls(
            skill_ids      = skill_ids,
            unknown_skills = unknown,
            skills_mode    = _choice(params.get("mode"), dict(c.MATCH_MODES), "mode",
                                     default = c.MATCH_MODE_AND),
            min_level      = _choice(params.get("min_level"), dict(c.SKILL_LEVELS), "min_level"),
            min_years      = _positive_int(params.get("min_years"), "min_years",
                                           maximum = c.MAX_YEARS_EXPERIENCE),

            field   = _choice(params.get("field"), dict(c.PROFESSIONAL_FIELDS), "field"),
            country = (params.get("country") or "").strip().upper()[:2],
            city    = (params.get("city") or "").strip()[:120],
            text    = (params.get("q") or "").strip()[:160],

            availability   = _choices(_multi(params, "availability"),
                                      dict(c.AVAILABILITY_STATUSES), "availability"),
            available_only = _flag(params.get("available")),
            contracts      = _choices(_multi(params, "contract", "contracts"),
                                      dict(c.CONTRACT_TYPES), "contract"),
            work_modes     = _choices(_multi(params, "work_mode", "work_modes"),
                                      dict(c.WORK_MODES), "work_mode"),

            language_ids       = language_ids,
            min_language_level = _choice(params.get("min_language_level"),
                                         dict(c.LANGUAGE_LEVELS), "min_language_level"),
            min_degree_level   = _choice(params.get("min_degree_level"),
                                         dict(c.DEGREE_LEVELS), "min_degree_level"),
            education_field    = (params.get("education_field") or "").strip()[:160],
            min_experience_years = _positive_int(params.get("min_experience_years"),
                                                 "min_experience_years",
                                                 maximum = c.MAX_YEARS_EXPERIENCE),

            sort      = _choice(params.get("sort"), dict(c.SORT_OPTIONS), "sort",
                                default = c.SORT_RELEVANCE),
            page      = _positive_int(params.get("page"), "page", default = 1, minimum = 1),
            page_size = min(
                _positive_int(params.get("page_size"), "page_size",
                              default = c.DEFAULT_PAGE_SIZE, minimum = 1),
                c.MAX_PAGE_SIZE,
            ),
        )

    def as_dict(self) -> dict:
        """Rappel des criteres retenus, tels que le serveur les a compris."""
        return {
            "skills":     self.skill_ids,
            "unknown_skills": self.unknown_skills,
            "mode":       self.skills_mode,
            "min_level":  self.min_level,
            "min_years":  self.min_years,
            "field":      self.field,
            "country":    self.country,
            "city":       self.city,
            "q":          self.text,
            "availability":   self.availability,
            "available":      self.available_only,
            "contracts":      self.contracts,
            "work_modes":     self.work_modes,
            "languages":      self.language_ids,
            "min_language_level":   self.min_language_level,
            "min_degree_level":     self.min_degree_level,
            "education_field":      self.education_field,
            "min_experience_years": self.min_experience_years,
            "sort":       self.sort,
            "page":       self.page,
            "page_size":  self.page_size,
        }


# --------------------------------------------------------------------------- #
# Lecture des parametres
# --------------------------------------------------------------------------- #

def _multi(params, *keys) -> list[str]:
    """Valeurs d'un parametre repete ou separe par des virgules."""
    values = []
    for key in keys:
        raw = params.getlist(key) if hasattr(params, "getlist") else params.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = [raw]
        for item in raw:
            values.extend(part.strip() for part in str(item).split(",") if part.strip())
    seen, unique = set(), []
    for value in values:
        if value.lower() not in seen:
            seen.add(value.lower())
            unique.append(value)
    return unique


def _choice(value, allowed: dict, label: str, default = None):
    if value in (None, ""):
        return default
    if value not in allowed:
        raise BadRequest(f"valeur invalide pour {label}: {value!r}", "invalid_field")
    return value


def _choices(values, allowed: dict, label: str) -> list:
    return [_choice(value, allowed, label) for value in values]


def _positive_int(value, label: str, *, default = None, minimum: int = 0, maximum: int = None):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise BadRequest(f"valeur invalide pour {label}: {value!r}", "invalid_field")
    if number < minimum:
        raise BadRequest(f"{label} doit valoir au moins {minimum}", "invalid_field")
    return min(number, maximum) if maximum is not None else number


def _flag(value) -> bool:
    return str(value).lower() in ("1", "true", "yes", "on") if value is not None else False


def _resolve_skills(references) -> tuple[list, list]:
    """Traduit des identifiants, slugs ou noms en identifiants de competence.

    Une competence inconnue n'est pas une erreur : elle est simplement
    introuvable. Elle est renvoyee a part pour que l'interface puisse le dire
    plutot que d'afficher zero resultat sans explication.
    """
    from .models import Skill

    ids, unknown = [], []
    for reference in references:
        if str(reference).isdigit():
            skill = Skill.objects.filter(pk = int(reference)).first()
        else:
            skill = find_skill(reference) if reference else None
        if skill is None:
            unknown.append(str(reference))
        elif skill.pk not in ids:
            ids.append(skill.pk)
    return ids, unknown


def _resolve_languages(references) -> list:
    from .models import Language

    ids = []
    for reference in references:
        if str(reference).isdigit():
            language = Language.objects.filter(pk = int(reference)).first()
        else:
            language = Language.objects.filter(code = str(reference).lower()).first()
        if language is not None and language.pk not in ids:
            ids.append(language.pk)
    return ids


# --------------------------------------------------------------------------- #
# Requete
# --------------------------------------------------------------------------- #

def base_queryset(viewer):
    """Profils qu'un visiteur a le droit de trouver.

    Le `searchable = True` est ici et nulle part ailleurs : c'est la seule
    facon de garantir qu'aucun chemin de recherche ne l'oublie. Il n'y a
    volontairement pas de derogation pour les administrateurs.

    La recherche de candidats n'a de sens que pour des demandeurs d'emploi :
    un recruteur ou un administrateur qui se serait cree un profil (pour
    tester, ou parce que rien ne l'en empeche) n'a rien a faire dans les
    resultats d'une recherche de candidats.
    """
    from django.db.models import Q

    from .models import ProfessionalProfile
    from .visibility import rank

    audience = c.AUDIENCE_REGISTERED if (viewer and viewer.is_authenticated) \
               else c.AUDIENCE_ANONYMOUS
    allowed  = [value for value, _ in c.VISIBILITIES if audience >= rank(value)]

    return (
        ProfessionalProfile.objects
        .filter(search_config__searchable = True, visibility__in = allowed)
        .exclude(
            Q(user__is_staff = True) | Q(user__is_superuser = True)
            | Q(user__role__role__in = ("Recruiter", "Admin"))
        )
        .select_related("user", "search_config", "visibility_config")
    )


def apply_filters(queryset, query: ProfileQuery):
    """Applique les criteres, sans toucher au classement."""
    from django.db.models import Q

    min_rank = c.skill_level_rank(query.min_level) if query.min_level else 0

    if query.skills_mode == c.MATCH_MODE_AND and query.unknown_skills:
        # En AND, toutes les competences demandees doivent etre presentes. Une
        # competence absente du referentiel n'est portee par personne : le
        # resultat est vide, meme si les autres competences, elles, existent.
        # (En OR, une competence inconnue est simplement ignoree.)
        return queryset.none()

    if query.skill_ids:
        if query.skills_mode == c.MATCH_MODE_AND:
            # un filtre par competence : Django cree une jointure distincte a
            # chaque appel, ce qui exige la presence de toutes les competences.
            for skill_id in query.skill_ids:
                conditions = {"skills__skill_id": skill_id}
                if min_rank:
                    conditions["skills__level_rank__gte"] = min_rank
                if query.min_years:
                    conditions["skills__years_experience__gte"] = query.min_years
                queryset = queryset.filter(**conditions)
        else:
            conditions = {"skills__skill_id__in": query.skill_ids}
            if min_rank:
                conditions["skills__level_rank__gte"] = min_rank
            if query.min_years:
                conditions["skills__years_experience__gte"] = query.min_years
            queryset = queryset.filter(**conditions).distinct()

    if query.field:
        queryset = queryset.filter(professional_field = query.field)
    if query.country:
        queryset = queryset.filter(location_country = query.country)
    if query.city:
        queryset = queryset.filter(location_city__icontains = query.city)

    if query.available_only:
        queryset = queryset.filter(availability_status__in = c.AVAILABLE_STATUSES)
    if query.availability:
        queryset = queryset.filter(availability_status__in = query.availability)

    if query.contracts:
        queryset = queryset.filter(
            contract_types__contract_type__in = query.contracts
        ).distinct()

    for mode in query.work_modes:
        queryset = queryset.filter(**{c.WORK_MODE_FIELDS[mode]: True})

    if query.min_experience_years:
        queryset = queryset.filter(
            total_experience_months__gte = query.min_experience_years * 12
        )

    if query.language_ids:
        language_rank = c.language_level_rank(query.min_language_level) \
                        if query.min_language_level else 0
        for language_id in query.language_ids:
            conditions = {"languages__language_id": language_id}
            if language_rank:
                conditions["languages__level_rank__gte"] = language_rank
            queryset = queryset.filter(**conditions)

    if query.min_degree_level:
        wanted = c.degree_level_rank(query.min_degree_level)
        accepted = [
            value for value, _ in c.DEGREE_LEVELS if c.degree_level_rank(value) >= wanted
        ]
        queryset = queryset.filter(education__degree_level__in = accepted).distinct()

    if query.education_field:
        queryset = queryset.filter(
            Q(education__field_of_study__icontains = query.education_field)
            | Q(education__degree__icontains = query.education_field)
        ).distinct()

    if query.text:
        queryset = queryset.filter(
            Q(user__username__icontains  = query.text)
            | Q(user__first_name__icontains = query.text)
            | Q(user__last_name__icontains  = query.text)
            | Q(headline__icontains = query.text)
            | Q(summary__icontains  = query.text)
        )

    return queryset


#: tri applique apres le classement ; l'identifiant ferme le tri pour que la
#: pagination reste stable entre deux pages a score egal
_SORTS = {
    c.SORT_RELEVANCE:  ("-relevance", "-total_experience_months", "-updated_at", "pk"),
    c.SORT_EXPERIENCE: ("-total_experience_months", "-relevance", "pk"),
    c.SORT_RECENT:     ("-updated_at", "pk"),
    c.SORT_NAME:       ("user__last_name", "user__first_name", "user__username", "pk"),
}


def search(query: ProfileQuery, viewer = None) -> dict:
    """Execute la recherche et renvoie une page de resultats classes."""
    queryset = apply_filters(base_queryset(viewer), query)
    queryset = ranking.annotate_relevance(queryset, query)
    queryset = queryset.order_by(*_SORTS[query.sort])
    queryset = queryset.prefetch_related("skills__skill", "contract_types")

    paginator = Paginator(queryset, query.page_size)
    page      = paginator.get_page(min(query.page, max(paginator.num_pages, 1)))

    return {
        "profiles":   list(page.object_list),
        "pagination": {
            "page":       page.number,
            "page_size":  query.page_size,
            "total":      paginator.count,
            "pages":      paginator.num_pages,
            "has_next":   page.has_next(),
            "has_previous": page.has_previous(),
        },
        "query": query.as_dict(),
    }
