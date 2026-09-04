"""Ecritures metier sur un profil professionnel.

Toute la logique vit ici ; `api.py` n'est qu'une couche de transport. Deux
regles gouvernent le module :

  * **aucune charge utile n'est appliquee en bloc**. Chaque ecriture passe par
    une liste blanche de champs et par un nettoyage par type. Un `**payload`
    sur un modele laisserait un client fixer `total_experience_months` ou
    `level_rank`, qui sont des valeurs calculees ;
  * **les valeurs derivees sont recalculees a l'ecriture**. Ajouter ou
    supprimer une experience met a jour `total_experience_months`, sur lequel
    s'appuient le filtre et le classement de la recherche.

Les controles de propriete sont dans `permissions.py` et sont appeles par
l'API avant d'arriver ici.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db              import IntegrityError, transaction
from django.utils.dateparse import parse_date

from profils.questionnaires.http import BadRequest

from . import constants as c
from . import moderation
from .models import (
    Certification, CertificationSkill, Education, EducationSkill, Language,
    ProfessionalProfile, ProfileContractType, ProfileLink, Project, ProjectSkill,
    ProfileVideo, ProfileVideoSkill, UserLanguage, UserSkill, WorkExperience,
    WorkExperienceSkill,
)
from .skills import resolve_skill, resolve_skill_reference

def _text(payload, key, *, maximum: int = 255, required: bool = False, default = "") -> str:
    if key not in payload or payload[key] is None:
        if required:
            raise BadRequest(f"champ manquant: {key}", "missing_field")
        return default
    value = str(payload[key]).strip()
    if required and not value:
        raise BadRequest(f"champ vide: {key}", "missing_field")
    return value[:maximum]

def _choice(payload, key, choices, *, default = "", required: bool = False):
    allowed = dict(choices)
    if key not in payload or payload[key] in (None, ""):
        if required:
            raise BadRequest(f"champ manquant: {key}", "missing_field")
        return default
    value = str(payload[key])
    if value not in allowed:
        raise BadRequest(f"valeur invalide pour {key}: {value!r}", "invalid_field")
    return value

def _bool(payload, key, default: bool = False) -> bool:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)

def _date(payload, key, *, required: bool = False):
    if key not in payload or payload[key] in (None, ""):
        if required:
            raise BadRequest(f"champ manquant: {key}", "missing_field")
        return None
    value = payload[key]
    parsed = parse_date(value) if isinstance(value, str) else value
    if parsed is None:
        raise BadRequest(f"date invalide pour {key}: {value!r}", "invalid_field")
    return parsed

_validate_url = URLValidator(schemes = ["http", "https"])

def _url(payload, key, *, maximum: int = 1024, required: bool = False, default = "") -> str:
    value = _text(payload, key, maximum = maximum, required = required, default = default)
    if value:
        try:
            _validate_url(value)
        except DjangoValidationError:
            raise BadRequest(f"URL invalide pour {key}: {value!r}", "invalid_field")
    return value

def _int(payload, key, *, minimum: int = 0, maximum: int = None, default = None):
    if key not in payload or payload[key] in (None, ""):
        return default
    try:
        number = int(payload[key])
    except (TypeError, ValueError):
        raise BadRequest(f"nombre invalide pour {key}", "invalid_field")
    if number < minimum:
        raise BadRequest(f"{key} doit valoir au moins {minimum}", "invalid_field")
    if maximum is not None and number > maximum:
        raise BadRequest(f"{key} ne peut pas depasser {maximum}", "invalid_field")
    return number

def _apply(instance, payload, fields: dict):
    """Recopie sur `instance` les seuls champs declares dans `fields`.

    `fields` associe un nom de champ a la fonction qui en extrait la valeur.
    Une cle absente de la charge utile laisse la valeur en place, ce qui rend
    les mises a jour partielles sures.
    """
    for name, reader in fields.items():
        if name in payload:
            setattr(instance, name, reader(payload))
    return instance

def get_profile(user) -> ProfessionalProfile:
    return ProfessionalProfile.for_user(user)

def profile_by_username(username: str):
    return (
        ProfessionalProfile.objects
        .select_related("user", "visibility_config", "search_config")
        .filter(user__username = username)
        .first()
    )

_PROFILE_FIELDS = {
    "headline":            lambda p: _text(p, "headline", maximum = 160),
    "summary":             lambda p: _text(p, "summary", maximum = 5000),
    "photo_url":           lambda p: _url(p, "photo_url", maximum = 1024),
    "cover_url":           lambda p: _url(p, "cover_url", maximum = 1024),
    "cover_color":         lambda p: _choice(p, "cover_color", c.COVER_COLORS,
                                             default = c.DEFAULT_COVER_COLOR),
    "location_city":       lambda p: _text(p, "location_city", maximum = 120),
    "location_region":     lambda p: _text(p, "location_region", maximum = 120),
    "location_country":    lambda p: _text(p, "location_country", maximum = 2).upper(),
    "professional_field":  lambda p: _choice(p, "professional_field", c.PROFESSIONAL_FIELDS),
    "availability_status": lambda p: _choice(p, "availability_status", c.AVAILABILITY_STATUSES,
                                             default = c.AVAILABILITY_NOT_LOOKING),
    "available_from":      lambda p: _date(p, "available_from"),
    "open_to_remote":      lambda p: _bool(p, "open_to_remote"),
    "open_to_hybrid":      lambda p: _bool(p, "open_to_hybrid"),
    "open_to_onsite":      lambda p: _bool(p, "open_to_onsite"),
    "willing_to_relocate": lambda p: _bool(p, "willing_to_relocate"),
    "mobility_radius_km":  lambda p: _int(p, "mobility_radius_km", maximum = 20000),
    "mobility_note":       lambda p: _text(p, "mobility_note", maximum = 240),
    "visibility":          lambda p: _choice(p, "visibility", c.VISIBILITIES,
                                             default = c.VISIBILITY_REGISTERED_USERS),
}

@transaction.atomic
def update_profile(profile: ProfessionalProfile, payload: dict) -> ProfessionalProfile:
    """Met a jour les informations generales, la disponibilite et la mobilite."""
    _apply(profile, payload, _PROFILE_FIELDS)
    profile.save()

    user, changed = profile.user, []
    if "first_name" in payload:
        user.first_name = _text(payload, "first_name", maximum = 150)
        changed.append("first_name")
    if "last_name" in payload:
        user.last_name = _text(payload, "last_name", maximum = 150)
        changed.append("last_name")
    if changed:
        user.save(update_fields = changed)

    if "contract_types" in payload:
        set_contract_types(profile, payload["contract_types"])
    return profile

@transaction.atomic
def set_contract_types(profile: ProfessionalProfile, codes) -> list[str]:
    """Remplace la liste des contrats recherches."""
    allowed = dict(c.CONTRACT_TYPES)
    wanted  = []
    for code in codes or []:
        code = str(code)
        if code not in allowed:
            raise BadRequest(f"type de contrat invalide: {code!r}", "invalid_field")
        if code not in wanted:
            wanted.append(code)

    profile.contract_types.exclude(contract_type__in = wanted).delete()
    existing = set(profile.contract_types.values_list("contract_type", flat = True))
    ProfileContractType.objects.bulk_create(
        [ProfileContractType(profile = profile, contract_type = code)
         for code in wanted if code not in existing]
    )
    return wanted

@transaction.atomic
def update_visibility(profile: ProfessionalProfile, payload: dict):
    """Regle la visibilite section par section."""
    settings = profile.visibility_settings()
    for section, _ in c.PROFILE_SECTIONS:
        if section in payload:
            field = c.SECTION_VISIBILITY_FIELDS[section]
            setattr(settings, field, _choice(payload, section, c.VISIBILITIES,
                                             default = c.VISIBILITY_PUBLIC))
    settings.profile = profile
    settings.save()
    return settings

@transaction.atomic
def update_search_settings(profile: ProfessionalProfile, payload: dict):
    """Regle l'apparition dans les resultats de recherche."""
    settings = profile.search_settings()
    for field in ("searchable", "appear_in_video_feed",
                  "show_availability_in_results", "contactable_by_recruiters"):
        if field in payload:
            setattr(settings, field, _bool(payload, field, getattr(settings, field)))
    settings.profile = profile
    settings.save()
    return settings

@transaction.atomic
def set_links(profile: ProfessionalProfile, items) -> list:
    """Remplace l'ensemble des liens professionnels."""
    profile.links.all().delete()
    links = []
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            raise BadRequest("chaque lien doit etre un objet", "invalid_field")
        url = _url(item, "url", maximum = 1024, required = True)
        links.append(ProfileLink(
            profile = profile,
            kind    = _choice(item, "kind", c.LINK_KINDS, default = c.LINK_OTHER),
            label   = _text(item, "label", maximum = 120),
            url     = url,
            order   = _int(item, "order", default = index),
        ))
    ProfileLink.objects.bulk_create(links)
    return list(profile.links.all())

@transaction.atomic
def add_skill(profile: ProfessionalProfile, payload: dict) -> UserSkill:
    """Ajoute une competence au profil, ou met a jour celle deja presente.

    Reajouter `java` a un profil qui declare deja `Java` ne cree pas de
    doublon : la resolution canonique ramene la meme competence, et la
    contrainte d'unicite (profil, competence) fait le reste. Reajouter une
    competence deja possedee est une mise a jour, pas un ajout : le plafond de
    competences ne doit donc jamais bloquer ce cas, meme un profil deja au
    plafond.
    """
    skill = _skill_from_payload(payload)

    existing = UserSkill.objects.filter(profile = profile, skill = skill).first()
    if existing is not None:
        return update_skill(existing, payload)

    if profile.skills.count() >= c.MAX_SKILLS_PER_PROFILE:
        raise BadRequest(
            f"un profil ne peut pas declarer plus de {c.MAX_SKILLS_PER_PROFILE} competences",
            "too_many_skills",
        )

    level = _choice(payload, "level", c.SKILL_LEVELS, default = c.LEVEL_BEGINNER)
    years = _int(payload, "years_experience", maximum = c.MAX_YEARS_EXPERIENCE)

    try:
        with transaction.atomic():
            return UserSkill.objects.create(
                profile = profile, skill = skill, level = level, years_experience = years,
                order = _int(payload, "order", default = profile.skills.count()),
                evidence_url = _url(payload, "evidence_url", maximum = 1024),
            )
    except IntegrityError:
        return update_skill(UserSkill.objects.get(profile = profile, skill = skill), payload)

def _skill_from_payload(payload: dict):
    reference = payload.get("skill_id") or payload.get("skill") or payload.get("name")
    if reference in (None, ""):
        raise BadRequest("champ manquant: skill", "missing_field")

    if isinstance(reference, str) and not reference.isdigit():
        return resolve_skill(reference, create = True,
                             category = payload.get("category"))

    skill = resolve_skill_reference(reference)
    if skill is None:
        raise BadRequest(f"competence introuvable: {reference!r}", "not_found")
    return skill

@transaction.atomic
def update_skill(user_skill: UserSkill, payload: dict) -> UserSkill:
    _apply(user_skill, payload, {
        "level":            lambda p: _choice(p, "level", c.SKILL_LEVELS,
                                              default = user_skill.level),
        "years_experience": lambda p: _int(p, "years_experience",
                                           maximum = c.MAX_YEARS_EXPERIENCE),
        "order":            lambda p: _int(p, "order", default = user_skill.order),
        "evidence_url":     lambda p: _url(p, "evidence_url", maximum = 1024),
    })

    if "certification_id" in payload:
        certification = None
        if payload["certification_id"]:
            certification = Certification.objects.filter(
                pk = payload["certification_id"], profile = user_skill.profile_id,
            ).first()
            if certification is None:
                raise BadRequest("certification introuvable", "not_found")
        user_skill.evidence_certification = certification

    user_skill.save()
    return user_skill

def remove_skill(user_skill: UserSkill):
    user_skill.delete()

@transaction.atomic
def reorder_skills(profile: ProfessionalProfile, skill_ids) -> list:
    """Fixe l'ordre d'affichage des competences."""
    rows = {row.skill_id: row for row in profile.skills.all()}
    for index, skill_id in enumerate(skill_ids or []):
        try:
            skill_id = int(skill_id)
        except (TypeError, ValueError):
            raise BadRequest(f"identifiant de competence invalide: {skill_id!r}", "invalid_field")
        row = rows.get(skill_id)
        if row is not None:
            row.order = index
            row.save(update_fields = ["order"])
    return list(profile.skills.all())

def set_entry_skills(entry, link_model, field_name: str, references):
    """Remplace les competences associees a une experience, formation, etc.

    Passe par le referentiel : une competence citee dans une experience est la
    meme ligne `Skill` que celle du profil, ce dont depend la recherche.
    """
    if references is None:
        return
    link_model.objects.filter(**{field_name: entry}).delete()

    links, seen = [], set()
    for index, reference in enumerate(references):
        skill = (
            resolve_skill(reference, create = True)
            if isinstance(reference, str) and not reference.isdigit()
            else resolve_skill_reference(reference)
        )
        if skill is None or skill.pk in seen:
            continue
        seen.add(skill.pk)
        links.append(link_model(**{field_name: entry}, skill = skill, order = index))
    link_model.objects.bulk_create(links)

_EXPERIENCE_FIELDS = {
    "title":            lambda p: _text(p, "title", maximum = 160, required = True),
    "company":          lambda p: _text(p, "company", maximum = 160, required = True),
    "description":      lambda p: _text(p, "description", maximum = 5000),
    "location_city":    lambda p: _text(p, "location_city", maximum = 120),
    "location_country": lambda p: _text(p, "location_country", maximum = 2).upper(),
    "contract_type":    lambda p: _choice(p, "contract_type", c.CONTRACT_TYPES),
    "start_date":       lambda p: _date(p, "start_date", required = True),
    "end_date":         lambda p: _date(p, "end_date"),
    "is_current":       lambda p: _bool(p, "is_current"),
    "order":            lambda p: _int(p, "order", default = 0),
}

@transaction.atomic
def create_experience(profile: ProfessionalProfile, payload: dict) -> WorkExperience:
    experience = WorkExperience(
        profile    = profile,
        title      = _text(payload, "title", maximum = 160, required = True),
        company    = _text(payload, "company", maximum = 160, required = True),
        start_date = _date(payload, "start_date", required = True),
    )
    _apply(experience, payload, _EXPERIENCE_FIELDS)
    experience.save()

    set_entry_skills(experience, WorkExperienceSkill, "experience", payload.get("skills"))
    profile.recompute_experience()
    return experience

@transaction.atomic
def update_experience(experience: WorkExperience, payload: dict) -> WorkExperience:
    _apply(experience, payload, _EXPERIENCE_FIELDS)
    experience.save()
    if "skills" in payload:
        set_entry_skills(experience, WorkExperienceSkill, "experience", payload["skills"])
    experience.profile.recompute_experience()
    return experience

@transaction.atomic
def delete_experience(experience: WorkExperience):
    profile = experience.profile
    experience.delete()
    profile.recompute_experience()

_EDUCATION_FIELDS = {
    "institution":    lambda p: _text(p, "institution", maximum = 160, required = True),
    "degree":         lambda p: _text(p, "degree", maximum = 160),
    "degree_level":   lambda p: _choice(p, "degree_level", c.DEGREE_LEVELS),
    "field_of_study": lambda p: _text(p, "field_of_study", maximum = 160),
    "description":    lambda p: _text(p, "description", maximum = 5000),
    "diploma_url":    lambda p: _url(p, "diploma_url", maximum = 1024),
    "start_date":     lambda p: _date(p, "start_date", required = True),
    "end_date":       lambda p: _date(p, "end_date"),
    "is_current":     lambda p: _bool(p, "is_current"),
    "order":          lambda p: _int(p, "order", default = 0),
}

@transaction.atomic
def create_education(profile: ProfessionalProfile, payload: dict) -> Education:
    education = Education(
        profile     = profile,
        institution = _text(payload, "institution", maximum = 160, required = True),
        start_date  = _date(payload, "start_date", required = True),
    )
    _apply(education, payload, _EDUCATION_FIELDS)
    education.save()
    set_entry_skills(education, EducationSkill, "education", payload.get("skills"))
    return education

@transaction.atomic
def update_education(education: Education, payload: dict) -> Education:
    _apply(education, payload, _EDUCATION_FIELDS)
    education.save()
    if "skills" in payload:
        set_entry_skills(education, EducationSkill, "education", payload["skills"])
    return education

def delete_education(education: Education):
    education.delete()

_CERTIFICATION_FIELDS = {
    "name":             lambda p: _text(p, "name", maximum = 160, required = True),
    "issuer":           lambda p: _text(p, "issuer", maximum = 160),
    "issued_on":        lambda p: _date(p, "issued_on"),
    "expires_on":       lambda p: _date(p, "expires_on"),
    "credential_id":    lambda p: _text(p, "credential_id", maximum = 160),
    "verification_url": lambda p: _url(p, "verification_url", maximum = 1024),
    "order":            lambda p: _int(p, "order", default = 0),
}

@transaction.atomic
def create_certification(profile: ProfessionalProfile, payload: dict) -> Certification:
    certification = Certification(
        profile = profile, name = _text(payload, "name", maximum = 160, required = True),
    )
    _apply(certification, payload, _CERTIFICATION_FIELDS)
    certification.save()
    set_entry_skills(certification, CertificationSkill, "certification", payload.get("skills"))
    return certification

@transaction.atomic
def update_certification(certification: Certification, payload: dict) -> Certification:
    _apply(certification, payload, _CERTIFICATION_FIELDS)
    certification.save()
    if "skills" in payload:
        set_entry_skills(certification, CertificationSkill, "certification", payload["skills"])
    return certification

def delete_certification(certification: Certification):
    certification.delete()

_PROJECT_FIELDS = {
    "title":       lambda p: _text(p, "title", maximum = 160, required = True),
    "description": lambda p: _text(p, "description", maximum = 5000),
    "role":        lambda p: _text(p, "role", maximum = 160),
    "url":         lambda p: _url(p, "url", maximum = 1024),
    "started_on":  lambda p: _date(p, "started_on"),
    "ended_on":    lambda p: _date(p, "ended_on"),
    "order":       lambda p: _int(p, "order", default = 0),
}

@transaction.atomic
def create_project(profile: ProfessionalProfile, payload: dict) -> Project:
    project = Project(profile = profile,
                      title = _text(payload, "title", maximum = 160, required = True))
    _apply(project, payload, _PROJECT_FIELDS)
    _attach_project_video(project, payload)
    project.save()
    set_entry_skills(project, ProjectSkill, "project", payload.get("skills"))
    return project

@transaction.atomic
def update_project(project: Project, payload: dict) -> Project:
    _apply(project, payload, _PROJECT_FIELDS)
    _attach_project_video(project, payload)
    project.save()
    if "skills" in payload:
        set_entry_skills(project, ProjectSkill, "project", payload["skills"])
    return project

def _attach_project_video(project: Project, payload: dict):
    """Rattache une video de presentation, si elle appartient bien au profil."""
    if "video_id" not in payload:
        return
    video = None
    if payload["video_id"]:
        video = ProfileVideo.objects.filter(
            pk = payload["video_id"], profile = project.profile_id,
        ).first()
        if video is None:
            raise BadRequest("video introuvable", "not_found")
    project.video = video

def delete_project(project: Project):
    project.delete()

@transaction.atomic
def set_language(profile: ProfessionalProfile, payload: dict) -> UserLanguage:
    code = _text(payload, "language", maximum = 8, required = True).lower()
    language = Language.objects.filter(code = code).first()
    if language is None:
        language = Language.objects.filter(name__iexact = code).first()
    if language is None:
        raise BadRequest(f"langue inconnue: {code!r}", "not_found")

    level = _choice(payload, "level", c.LANGUAGE_LEVELS, default = c.CEFR_B1)
    row, created = UserLanguage.objects.get_or_create(
        profile = profile, language = language,
        defaults = {"level": level, "order": _int(payload, "order",
                                                  default = profile.languages.count())},
    )
    if not created:
        row.level = level
        if "order" in payload:
            row.order = _int(payload, "order", default = row.order)
        row.save()
    return row

def remove_language(row: UserLanguage):
    row.delete()

_VIDEO_FIELDS = {
    "title":            lambda p: _text(p, "title", maximum = 160, required = True),
    "description":      lambda p: _text(p, "description", maximum = 5000),
    "thumbnail_url":    lambda p: _url(p, "thumbnail_url", maximum = 1024),
    "duration_seconds": lambda p: _int(p, "duration_seconds", maximum = 60 * 60),
    "visibility":       lambda p: _choice(p, "visibility", c.VISIBILITIES,
                                          default = c.VISIBILITY_PUBLIC),
}

def _clean_video_url(value: str, *, required: bool = False) -> str:
    """Meme validation qu'un champ de formulaire (`_url`), pour un lien recu
    a part -- soumission, re-soumission, remplacement.
    """
    return _url({"file_url": value}, "file_url", maximum = 1024, required = required)

def create_video(profile: ProfessionalProfile, payload: dict) -> ProfileVideo:
    """Primitive interne : cree une fiche video sans passer par la moderation.

    Reservee aux appels de confiance (scripts, tests) -- jamais a une route
    HTTP directement accessible a un utilisateur, puisqu'elle n'entre pas la
    video en file d'attente. `submit_video_link` est le point d'entree reel
    (section 1).
    """
    video = ProfileVideo(profile = profile,
                         title = _text(payload, "title", maximum = 160, required = True))
    _apply(video, payload, _VIDEO_FIELDS)
    if "status" in payload:
        video.status = _choice(payload, "status", c.VIDEO_STATUSES, default = c.VIDEO_DRAFT)
    if "file_url" in payload:
        video.file_url = _url(payload, "file_url", maximum = 1024)
    video.tags = _tags(payload)
    video.save()
    set_entry_skills(video, ProfileVideoSkill, "video", payload.get("skills"))
    return video

def update_video(video: ProfileVideo, payload: dict) -> ProfileVideo:
    """Modifie les metadonnees d'une video (titre, description, visibilite...).

    Ne touche ni au statut ni au lien de lecture : voir `moderation.
    transition_video` pour le premier, `replace_video_link` pour le second,
    qui doit repasser par la moderation une fois la video publiee.
    """
    _apply(video, payload, _VIDEO_FIELDS)
    if "tags" in payload:
        video.tags = _tags(payload)
    video.save()
    if "skills" in payload:
        set_entry_skills(video, ProfileVideoSkill, "video", payload["skills"])
    return video

def _tags(payload: dict) -> list:
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",")]
    return [str(tag).strip()[:40] for tag in tags if str(tag).strip()][:20]

def delete_video(video: ProfileVideo, *, actor: str = c.ACTOR_OWNER, user = None):
    """Suppression logique (section 1) : une video referencee par un projet
    ne doit pas disparaitre sous ses pieds, et la suppression doit rester
    tracee dans l'historique de moderation comme n'importe quel changement de
    statut.
    """
    moderation.transition_video(video, c.VIDEO_DELETED, actor = actor, user = user)

def submit_video_link(profile: ProfessionalProfile, payload: dict) -> ProfileVideo:
    """Soumet une nouvelle video par lien externe (section 1).

    Entre directement en file de moderation (`PENDING`) : il n'y a pas de
    fichier a "traiter" pour un lien, donc pas de passage par `DRAFT` ni
    `PROCESSING` -- ces deux statuts restent reserves a l'upload par fichier,
    construit separement (voir `constants.ENABLED_VIDEO_SOURCES`).

    Toute video soumise ici est une candidate a la video de presentation du
    profil (section 2) ; le projet ne distingue pas encore d'autre categorie
    de video, meme si le modele le permettrait deja (evolutivite, section 8).
    """
    video = ProfileVideo(
        profile         = profile,
        title           = _text(payload, "title", maximum = 160, required = True),
        description     = _text(payload, "description", maximum = 5000),
        source_type     = c.VIDEO_SOURCE_LINK,
        file_url        = _url(payload, "file_url", maximum = 1024, required = True),
        thumbnail_url   = _url(payload, "thumbnail_url", maximum = 1024),
        duration_seconds = _int(payload, "duration_seconds", maximum = 60 * 60),
        visibility      = _choice(payload, "visibility", c.VISIBILITIES,
                                  default = c.VISIBILITY_PUBLIC),
        is_presentation = True,
        status          = c.VIDEO_PENDING,
    )

    replaces_id = payload.get("replaces")
    if replaces_id:
        current = ProfileVideo.objects.filter(
            pk = replaces_id, profile = profile,
            is_presentation = True, status = c.VIDEO_PUBLISHED,
        ).first()
        if current is None:
            raise BadRequest(
                "la video de presentation a remplacer est introuvable", "replaces_not_found",
            )
        video.replaces = current

    video.tags = _tags(payload)
    video.save()
    set_entry_skills(video, ProfileVideoSkill, "video", payload.get("skills"))
    return video

def resubmit_video(video: ProfileVideo, *, user, new_file_url: str = None) -> ProfileVideo:
    """Nouvelle soumission apres un refus (section 1).

    Un lien de remplacement est optionnel : l'utilisateur peut vouloir
    re-soumettre la meme video (motif juge injustement refuse) comme changer
    de lien avant de re-tenter sa chance.
    """
    if new_file_url:
        video.file_url = _clean_video_url(new_file_url)
        video.save(update_fields = ["file_url"])
    return moderation.transition_video(video, c.VIDEO_PENDING, actor = c.ACTOR_OWNER, user = user)

def replace_video_link(video: ProfileVideo, new_file_url: str, *, user) -> ProfileVideo:
    """Change le lien d'une video deja en ligne (section "Securite") :
    renvoie systematiquement en moderation.

    Sans ce garde-fou, faire valider une video anodine puis remplacer le lien
    contournerait la moderation en une seule requete -- exactement ce que la
    specification interdit ("une video refusee ne doit jamais etre accessible
    publiquement" vaut aussi pour une video jamais revue du tout).
    """
    video.file_url = _clean_video_url(new_file_url)
    video.save(update_fields = ["file_url"])
    if video.status == c.VIDEO_PUBLISHED:
        moderation.transition_video(video, c.VIDEO_PENDING, actor = c.ACTOR_OWNER, user = user)
    return video

@transaction.atomic
def publish_presentation_video(video: ProfileVideo, *, user) -> ProfileVideo:
    """Publication explicite d'une video de presentation validee (section 2).

    Une validation administrateur ne publie jamais toute seule : c'est ce
    geste, et lui seul, qui rend la video visible au public. Si une
    presentation etait deja en ligne, elle est retiree dans la meme
    transaction -- et *avant* que la nouvelle passe publiee, jamais apres :
    les deux ne doivent jamais etre publiees en meme temps, y compris le
    temps d'une transaction (voir la contrainte sur `ProfileVideo`).
    """
    if not video.is_presentation:
        raise BadRequest("cette video n'est pas une video de presentation", "not_presentation")

    previous = ProfileVideo.objects.filter(
        profile = video.profile, is_presentation = True, status = c.VIDEO_PUBLISHED,
    ).exclude(pk = video.pk).first()

    if previous is not None:
        moderation.transition_video(
            previous, c.VIDEO_HIDDEN, actor = c.ACTOR_OWNER, user = user,
            reason = "remplacee par une nouvelle video de presentation",
        )

    moderation.transition_video(video, c.VIDEO_PUBLISHED, actor = c.ACTOR_OWNER, user = user)
    return video

def approve_video(video: ProfileVideo, *, user) -> ProfileVideo:
    """Validation administrateur (section 1) : ne publie jamais la video."""
    return moderation.transition_video(video, c.VIDEO_APPROVED, actor = c.ACTOR_ADMIN, user = user)

def reject_video(video: ProfileVideo, reason: str, *, user) -> ProfileVideo:
    """Refus administrateur (section 1) : le motif est obligatoire, verifie
    par `moderation.transition_video` lui-meme.
    """
    return moderation.transition_video(
        video, c.VIDEO_REJECTED, actor = c.ACTOR_ADMIN, user = user, reason = reason,
    )

# TODO: "No real magic-byte file validation — you're trusting the client-reported content_type, which can be spoofed or occasionally wrong/generic depending on browser/OS. Fine for a school project; not fine for anything adversarial.""

def process_video_file(video):
    reasons = []

    if video.file_content_type not in c.ALLOWED_VIDEO_CONTENT_TYPES:
        reasons.append(f"Format non supporté : {video.file_content_type}")


    if video.file_size and video.file_size > c.MAX_VIDEO_FILE_SIZE:
        reasons.append("Fichier trop volumineux")

    if reasons:
        moderation.transition_video(
            video, c.VIDEO_REJECTED, actor=c.ACTOR_SYSTEM, reason="; ".join(reasons)
        )
        return video

    moderation.transition_video(video, c.VIDEO_PENDING, actor=c.ACTOR_SYSTEM)
    return video

def submit_video_file(profile, file, title, description=""):
    video = ProfileVideo(
        profile=profile,
        title=title,
        description=description,
        source_type=c.VIDEO_SOURCE_FILE,
        status=c.VIDEO_DRAFT,
        is_presentation=True,
        file_content_type=file.content_type,
        file_size=file.size,
        file_blob=file.read(),
    )

    current = ProfileVideo.objects.filter(
        profile=profile, is_presentation=True, status=c.VIDEO_PUBLISHED,
    ).first()
    if current is not None:
        video.replaces = current

    video.save()
    moderation.transition_video(video, c.VIDEO_PROCESSING, actor=c.ACTOR_OWNER, user=profile.user)
    process_video_file(video)
    return video
