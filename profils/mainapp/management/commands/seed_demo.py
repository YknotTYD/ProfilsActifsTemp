##management/commands/seed_demo.py
"""Cree un compte de demonstration par type d'utilisateur.

Utilise par le workflow de build (voir .github/workflows/build.yml) pour que
l'artefact publie contienne des comptes de demonstration deja remplis, un par
role (Admin, Recruiter, JobSeeker). Idempotent : peut etre relance sans
dupliquer les comptes.
"""

import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from profils.mainapp.models import Role
from profils.profiles import constants as pc
from profils.profiles.models import ProfessionalProfile

DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo1234!")

DEMO_ACCOUNTS = (
    {
        "role": "Admin",
        "username": "demo.admin",
        "first_name": "Alex",
        "last_name": "Admin",
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "role": "Recruiter",
        "username": "demo.recruteur",
        "first_name": "Camille",
        "last_name": "Recruteur",
        "profile": {
            "headline": "Recruteuse tech chez Nova Partners",
            "summary": "Je recrute des profils tech pour des scale-ups francaises.",
            "location_city": "Paris",
            "location_country": "FR",
            "professional_field": pc.FIELD_HR,
            "availability_status": pc.AVAILABILITY_NOT_LOOKING,
            "visibility": pc.VISIBILITY_PUBLIC,
        },
    },
    {
        "role": "JobSeeker",
        "username": "demo.candidat",
        "first_name": "Sacha",
        "last_name": "Candidat",
        "profile": {
            "headline": "Developpeuse backend Python/Django",
            "summary": "5 ans d'experience en developpement web, a la recherche d'un CDI.",
            "location_city": "Lyon",
            "location_country": "FR",
            "professional_field": pc.FIELD_SOFTWARE,
            "availability_status": pc.AVAILABILITY_OPEN_TO_WORK,
            "open_to_remote": True,
            "open_to_hybrid": True,
            "visibility": pc.VISIBILITY_PUBLIC,
        },
    },
)


class Command(BaseCommand):
    help = "Cree ou met a jour un compte de demonstration par role (Admin, Recruiter, JobSeeker)."

    def handle(self, *args, **options):
        for account in DEMO_ACCOUNTS:
            user, created = User.objects.get_or_create(username=account["username"])
            user.first_name = account["first_name"]
            user.last_name = account["last_name"]
            user.is_staff = account.get("is_staff", False)
            user.is_superuser = account.get("is_superuser", False)
            user.set_password(DEMO_PASSWORD)
            user.save()

            Role.objects.get_or_create(user=user, role=account["role"])

            if "profile" in account:
                profile = ProfessionalProfile.for_user(user)
                for field, value in account["profile"].items():
                    setattr(profile, field, value)
                profile.save()

            action = "cree" if created else "mis a jour"
            self.stdout.write(self.style.SUCCESS(
                f"compte demo {action} : {user.username} ({account['role']})"
            ))

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Identifiants de demonstration :"))
        for account in DEMO_ACCOUNTS:
            self.stdout.write(
                f"  {account['role']:<10} -> username={account['username']}  password={DEMO_PASSWORD}"
            )
