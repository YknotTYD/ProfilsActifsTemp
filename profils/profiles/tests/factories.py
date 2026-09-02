##tests/factories.py
"""Fabriques partagees par les tests des profils."""

from datetime import date

from django.contrib.auth.models import User

from profils.profiles import constants as c
from profils.profiles import services
from profils.profiles.models import Language, ProfessionalProfile


def make_user(username = "user", **kwargs) -> User:
    """Utilisateur sans mot de passe utilisable.

    Le hachage d'un mot de passe coute plus cher que tout le reste d'un test :
    les tests d'API se connectent avec `force_login`, qui n'en a pas besoin.
    """
    return User.objects.create_user(username, None, None, **kwargs)


def make_admin(username = "admin") -> User:
    return User.objects.create_user(
        username, None, None, is_superuser = True, is_staff = True
    )


def make_profile(username = "candidat", *, user = None, skills = (), **kwargs):
    """Profil pret a etre trouve : visible et recherchable par defaut."""
    user = user or make_user(username)
    if "first_name" in kwargs or "last_name" in kwargs:
        user.first_name = kwargs.pop("first_name", "")
        user.last_name  = kwargs.pop("last_name", "")
        user.save()

    contract_types = kwargs.pop("contract_types", None)
    searchable     = kwargs.pop("searchable", True)

    profile = ProfessionalProfile.for_user(user)
    for field, value in {
        "visibility":          c.VISIBILITY_PUBLIC,
        "availability_status": c.AVAILABILITY_OPEN_TO_WORK,
        **kwargs,
    }.items():
        setattr(profile, field, value)
    profile.save()

    if contract_types is not None:
        services.set_contract_types(profile, contract_types)
    if not searchable:
        services.update_search_settings(profile, {"searchable": False})

    for entry in skills:
        add_skill(profile, *entry) if isinstance(entry, tuple) else add_skill(profile, entry)

    return profile


def add_skill(profile, name = "Java", level = c.LEVEL_INTERMEDIATE, years = None):
    return services.add_skill(profile, {
        "name": name, "level": level, "years_experience": years,
    })


def add_experience(profile, *, title = "Developpeur", company = "ACME",
                   start = date(2020, 1, 1), end = date(2022, 1, 1),
                   current = False, skills = ()):
    return services.create_experience(profile, {
        "title": title, "company": company,
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end and not current else None,
        "is_current": current,
        "skills": list(skills),
    })


def add_education(profile, *, institution = "Epitech", degree = "Master",
                  level = c.DEGREE_BAC_5, start = date(2018, 9, 1),
                  end = date(2023, 6, 30), skills = (), **kwargs):
    return services.create_education(profile, {
        "institution": institution, "degree": degree, "degree_level": level,
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        "skills": list(skills), **kwargs,
    })


def add_certification(profile, *, name = "AWS Solutions Architect",
                      issuer = "Amazon", skills = (), **kwargs):
    return services.create_certification(profile, {
        "name": name, "issuer": issuer, "skills": list(skills), **kwargs,
    })


def add_project(profile, *, title = "API Rust", skills = (), **kwargs):
    return services.create_project(profile, {
        "title": title, "skills": list(skills), **kwargs,
    })


def add_language(profile, code = "fr", level = c.CEFR_C2):
    return services.set_language(profile, {"language": code, "level": level})


def add_video(profile, *, title = "Je developpe une API Rust",
              status = c.VIDEO_PUBLISHED, skills = (), **kwargs):
    return services.create_video(profile, {
        "title": title, "status": status, "skills": list(skills), **kwargs,
    })


def language(code = "fr", name = "Francais") -> Language:
    row, _ = Language.objects.get_or_create(code = code, defaults = {"name": name})
    return row
