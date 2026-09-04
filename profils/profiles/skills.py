"""Normalisation et resolution canonique des competences (section 3).

Le probleme a resoudre est celui de `Java` / `java` / `JAVA` : trois saisies,
une seule competence. Chaque nom saisi est reduit a une **cle normalisee** ;
c'est elle, et non le libelle affiche, qui porte l'unicite en base.

La normalisation traite d'abord les caracteres qui ont un sens dans les noms
techniques, avant de reduire le reste. Un `slugify` naif ecraserait `C++` et
`C` sur la meme cle, et `C#` avec eux :

    C++          -> cpp
    C#           -> csharp
    .NET         -> net
    ASP.NET      -> asp-net
    Objective-C  -> objective-c
    JAVA / java  -> java

Deux noms differents qui designent la meme competence (`NodeJS` et `Node.js`)
ne se rejoignent pas par normalisation : c'est le role de `SkillAlias`, qui
pointe une cle normalisee supplementaire vers une competence existante.

Ce module n'importe aucun modele au chargement : `models/skill.py` a besoin de
`normalize_skill_name`, et l'import inverse creerait un cycle.
"""

import re
import unicodedata

from django.core.exceptions import ValidationError

from . import constants as c

_TECHNICAL_SUBSTITUTIONS = (
    ("#", "sharp"),
    ("+", "p"),
)

_SEPARATORS = re.compile(r"[^a-z0-9]+")

def normalize_skill_name(name: str) -> str:
    """Cle canonique d'un nom de competence.

    Leve `ValidationError` si le nom ne contient rien d'exploitable : une cle
    vide ferait entrer en collision toutes les saisies aberrantes.
    """
    if not isinstance(name, str):
        raise ValidationError("le nom de la competence doit etre une chaine")

    text = unicodedata.normalize("NFKD", name.strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))

    for source, replacement in _TECHNICAL_SUBSTITUTIONS:
        text = text.replace(source, replacement)

    key = _SEPARATORS.sub("-", text).strip("-")
    if not key:
        raise ValidationError(f"nom de competence invalide: {name!r}")
    return key[:c.MAX_SKILL_NAME_LENGTH]

def clean_display_name(name: str) -> str:
    """Libelle affichable : espaces normalises, longueur bornee."""
    return re.sub(r"\s+", " ", (name or "").strip())[:c.MAX_SKILL_NAME_LENGTH]

def find_skill(name: str):
    """Competence correspondant a `name`, alias compris. `None` si inconnue."""
    from .models import Skill, SkillAlias

    key = normalize_skill_name(name)

    skill = Skill.objects.filter(slug = key).first()
    if skill is not None:
        return skill

    alias = SkillAlias.objects.filter(normalized = key).select_related("skill").first()
    return alias.skill if alias else None

def resolve_skill(name: str, *, create: bool = True, category: str = None):
    """Competence canonique pour `name`, creee au besoin.

    La creation passe par `get_or_create` sur la cle normalisee : deux requetes
    simultanees portant le meme nom aboutissent a la meme ligne plutot qu'a un
    doublon ou a une erreur d'integrite.
    """
    from .models import Skill

    skill = find_skill(name)
    if skill is not None or not create:
        return skill

    key   = normalize_skill_name(name)
    label = clean_display_name(name) or key

    skill, _ = Skill.objects.get_or_create(
        slug = key,
        defaults = {
            "name":     label,
            "category": category or c.SKILL_CATEGORY_OTHER,
        },
    )
    return skill

def resolve_skills(names, *, create: bool = True) -> list:
    """Resout une liste de noms en competences, sans doublon et dans l'ordre."""
    resolved, seen = [], set()
    for name in names or []:
        skill = resolve_skill(name, create = create)
        if skill is None or skill.pk in seen:
            continue
        seen.add(skill.pk)
        resolved.append(skill)
    return resolved

def resolve_skill_reference(reference, *, create: bool = False):
    """Competence designee par un identifiant numerique, un slug ou un nom.

    L'API accepte les trois formes : le frontend renvoie l'`id` d'une
    competence choisie dans l'autocompletion, mais une saisie libre reste
    possible.
    """
    from .models import Skill

    if reference is None or reference == "":
        return None
    if isinstance(reference, bool):
        raise ValidationError("reference de competence invalide")
    if isinstance(reference, int) or (isinstance(reference, str) and reference.isdigit()):
        return Skill.objects.filter(pk = int(reference)).first()
    return resolve_skill(str(reference), create = create)

def add_alias(skill, alias: str):
    """Rattache une orthographe supplementaire a une competence existante.

    Refuse un alias qui est deja le nom canonique d'une autre competence : la
    fusion de deux competences distinctes est une operation d'administration,
    pas un effet de bord d'un ajout d'alias.
    """
    from .models import Skill, SkillAlias

    key = normalize_skill_name(alias)
    if key == skill.slug:
        return None

    owner = Skill.objects.filter(slug = key).first()
    if owner is not None:
        raise ValidationError(f"'{alias}' est deja la competence {owner.name!r}")

    existing = SkillAlias.objects.filter(normalized = key).select_related("skill").first()
    if existing is not None:
        if existing.skill_id != skill.pk:
            raise ValidationError(f"'{alias}' est deja un alias de {existing.skill.name!r}")
        return existing

    return SkillAlias.objects.create(
        skill = skill, normalized = key, label = clean_display_name(alias),
    )
