##ranking.py
"""Score de pertinence des resultats de recherche (section 14).

Le score est une expression SQL annotee sur la requete : le tri et la
pagination se font donc en base, sur l'ensemble des profils correspondants, et
non sur une page deja tronquee. C'est la difference entre "les 20 premiers
resultats classes" et "20 resultats au hasard, classes entre eux".

Chaque composante est calculee par une **sous-requete** plutot que par une
jointure agregee. Une requete qui joint a la fois les competences et les
langues verrait chaque somme multipliee par le nombre de lignes de l'autre
relation ; la sous-requete est insensible a cet effet d'eventail.

Les poids vivent dans `constants.RANKING_WEIGHTS`. Ajouter un critere revient a
ecrire une composante de plus et a lui donner un poids : la fonction
`relevance_expression` n'a pas a etre reecrite.
"""

from django.db.models import (
    Case, Count, Exists, F, IntegerField, OuterRef, Subquery, Sum, Value, When,
)
from django.db.models.functions import Coalesce, Least

from . import constants as c


def _skill_subquery(aggregate, skill_ids, min_rank: int, min_years: int = None):
    """Agregat sur les competences retenues d'un profil, en sous-requete."""
    from .models import UserSkill

    rows = UserSkill.objects.filter(profile = OuterRef("pk"), skill_id__in = skill_ids)
    if min_rank:
        rows = rows.filter(level_rank__gte = min_rank)
    if min_years:
        rows = rows.filter(years_experience__gte = min_years)

    return Coalesce(
        Subquery(
            rows.values("profile").annotate(value = aggregate).values("value")[:1],
            output_field = IntegerField(),
        ),
        Value(0),
        output_field = IntegerField(),
    )


def _language_subquery(language_ids, min_rank: int):
    from .models import UserLanguage

    rows = UserLanguage.objects.filter(
        profile = OuterRef("pk"), language_id__in = language_ids, level_rank__gte = min_rank,
    )
    return Coalesce(
        Subquery(
            rows.values("profile").annotate(value = Count("id")).values("value")[:1],
            output_field = IntegerField(),
        ),
        Value(0),
        output_field = IntegerField(),
    )


def relevance_annotations(query) -> dict:
    """Composantes du score, annotables telles quelles sur un queryset.

    Elles sont exposees individuellement et pas seulement agregees : une carte
    de resultat peut afficher "3 competences sur 4" sans requete de plus, et un
    reglage de poids se verifie composante par composante.
    """
    from .models import ProfileVideo

    skill_ids = list(query.skill_ids)
    min_rank  = c.skill_level_rank(query.min_level) if query.min_level else 0

    annotations = {
        "matched_skill_count": (
            _skill_subquery(Count("id"), skill_ids, min_rank, query.min_years)
            if skill_ids else Value(0, output_field = IntegerField())
        ),
        "matched_skill_level": (
            _skill_subquery(Sum("level_rank"), skill_ids, min_rank, query.min_years)
            if skill_ids else Value(0, output_field = IntegerField())
        ),
        "matched_skill_years": (
            _skill_subquery(
                Sum(Coalesce("years_experience", Value(0))), skill_ids, min_rank, query.min_years
            ) if skill_ids else Value(0, output_field = IntegerField())
        ),
        "matched_language_count": (
            _language_subquery(query.language_ids, c.language_level_rank(query.min_language_level))
            if query.language_ids else Value(0, output_field = IntegerField())
        ),
        "availability_bonus": Case(
            When(availability_status__in = c.AVAILABLE_STATUSES, then = Value(1)),
            default = Value(0), output_field = IntegerField(),
        ),
        "field_bonus": (
            Case(
                When(professional_field = query.field, then = Value(1)),
                default = Value(0), output_field = IntegerField(),
            ) if query.field else Value(0, output_field = IntegerField())
        ),
        "experience_years": Least(
            F("total_experience_months") / Value(12),
            Value(c.RANKING_CAPS["total_experience"]),
            output_field = IntegerField(),
        ),
        "has_video": Case(
            When(
                Exists(
                    ProfileVideo.objects.filter(
                        profile = OuterRef("pk"), status = c.VIDEO_PUBLISHED,
                    )
                ),
                then = Value(1),
            ),
            default = Value(0), output_field = IntegerField(),
        ),
    }

    # plafonne les annees de competence apres coup : `Least` sur une
    # sous-requete reste une expression, donc utilisable ici.
    annotations["capped_skill_years"] = Least(
        annotations["matched_skill_years"],
        Value(c.RANKING_CAPS["skill_years"]),
        output_field = IntegerField(),
    )
    return annotations


def relevance_expression(weights: dict = None):
    """Combinaison ponderee des composantes annotees par `relevance_annotations`."""
    weights = {**c.RANKING_WEIGHTS, **(weights or {})}

    return (
        F("matched_skill_count")    * Value(weights["skill_match"])
        + F("matched_skill_level")  * Value(weights["skill_level"])
        + F("capped_skill_years")   * Value(weights["skill_years"])
        + F("experience_years")     * Value(weights["total_experience"])
        + F("availability_bonus")   * Value(weights["availability"])
        + F("field_bonus")          * Value(weights["field_match"])
        + F("matched_language_count") * Value(weights["language_match"])
        + F("has_video")            * Value(weights["has_video"])
    )


def annotate_relevance(queryset, query):
    """Annote `relevance` et ses composantes sur un queryset de profils."""
    annotations = relevance_annotations(query)
    return queryset.annotate(**annotations).annotate(
        relevance = relevance_expression(query.weights)
    )


def score_breakdown(profile, query) -> dict:
    """Detail du score d'un profil annote, pour expliquer un classement.

    Sert aux tests et au deboguage : un classement que personne ne peut
    expliquer ne peut pas etre ameliore.
    """
    weights = {**c.RANKING_WEIGHTS, **(query.weights or {})}
    parts = {
        "skill_match":      getattr(profile, "matched_skill_count", 0)    * weights["skill_match"],
        "skill_level":      getattr(profile, "matched_skill_level", 0)    * weights["skill_level"],
        "skill_years":      getattr(profile, "capped_skill_years", 0)     * weights["skill_years"],
        "total_experience": getattr(profile, "experience_years", 0)       * weights["total_experience"],
        "availability":     getattr(profile, "availability_bonus", 0)     * weights["availability"],
        "field_match":      getattr(profile, "field_bonus", 0)            * weights["field_match"],
        "language_match":   getattr(profile, "matched_language_count", 0) * weights["language_match"],
        "has_video":        getattr(profile, "has_video", 0)              * weights["has_video"],
    }
    parts["total"] = sum(parts.values())
    return parts
