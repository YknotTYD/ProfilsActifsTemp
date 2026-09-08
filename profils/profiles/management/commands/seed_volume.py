"""Jeu de donnees volumetrique pour les tests de charge.

    python manage.py seed_volume                    # 500 profils, 300 avec video
    python manage.py seed_volume --profiles 50 --with-video 30
    python manage.py seed_volume --keep             # ajoute sans effacer

La commande est relancable sur une base vide par quelqu'un qui n'en est pas
l'auteur : elle cree elle-meme le compte d'administration dont elle a besoin
pour moderer, et elle efface son propre lot avant de le regenerer. Elle ne
touche a aucun compte qu'elle n'a pas cree : tous portent le prefixe
`charge-`.

**Les videos passent par l'interface de soumission, pas par une insertion
directe en base.** Chacune parcourt le vrai cycle de moderation :

    submit_video_link  ->  PENDING
    approve_video      ->  APPROVED   (geste administrateur)
    publish_presentation_video -> PUBLISHED  (geste du proprietaire)

C'est plus lent qu'un `bulk_create`, et c'est le but : un jeu de donnees qui
contourne le code de l'application ne mesure rien de l'application. Les
evenements de moderation, les notifications et les contraintes d'unicite sont
donc produits comme en production.

Le tirage est deterministe (`--seed`) : deux executions avec la meme graine
produisent le meme jeu de donnees, ce qui permet de comparer deux campagnes de
charge entre elles.
"""

import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from profils.mainapp.models import Role
from profils.profiles import constants as c
from profils.profiles import services as profile_services

PREFIX       = "charge-"
ADMIN_USERNAME = "charge-moderateur"
PASSWORD     = "Charge1234!"

FIELDS = [value for value, _ in c.PROFESSIONAL_FIELDS]

CITIES = [
    "Paris", "Lyon", "Marseille", "Toulouse", "Nantes", "Bordeaux", "Lille",
    "Nancy", "Strasbourg", "Rennes", "Montpellier", "Nice",
]

SKILLS = [
    "Python", "Django", "JavaScript", "React", "SQL", "PostgreSQL", "Docker",
    "Kubernetes", "Git", "Linux", "Java", "Go", "Rust", "TypeScript", "AWS",
    "Terraform", "Figma", "Excel", "Photoshop", "Scrum",
]

LEVELS = [value for value, _ in c.SKILL_LEVELS]

AVAILABILITIES = [value for value, _ in c.AVAILABILITY_STATUSES]

CONTRACTS = [value for value, _ in c.CONTRACT_TYPES]

LANGUAGES = ["en", "es", "de", "it"]

CLIPS = [
    "https://www.youtube.com/embed/aqz-KE-bpKQ",
    "https://www.youtube.com/embed/eRsGyueVLvQ",
    "https://www.youtube.com/embed/R6MlUcmOul8",
    "https://www.youtube.com/embed/TLkA0RELQ1g",
]

class Command(BaseCommand):
    help = "Peuple la base d'un jeu de donnees volumetrique pour les tests de charge."

    def add_arguments(self, parser):
        parser.add_argument(
            "--profiles", type = int, default = 500,
            help = "Nombre de profils a creer (defaut : 500).",
        )
        parser.add_argument(
            "--with-video", type = int, default = 300,
            help = "Nombre de ces profils qui recoivent une video (defaut : 300).",
        )
        parser.add_argument(
            "--seed", type = int, default = 20260908,
            help = "Graine du tirage, pour un jeu de donnees reproductible.",
        )
        parser.add_argument(
            "--keep", action = "store_true",
            help = "Ajoute au lot existant au lieu de l'effacer d'abord.",
        )

    def handle(self, *args, **options):
        count  = options["profiles"]
        videos = options["with_video"]

        if videos > count:
            raise CommandError(
                f"--with-video ({videos}) ne peut pas depasser --profiles ({count})"
            )

        self.random = random.Random(options["seed"])

        with transaction.atomic():
            start = self._next_index() if options["keep"] else self._reset()
            moderator = self._moderator()
            created   = self._create_profiles(start, count, videos, moderator)

        self._summary(created, videos, options["seed"])

    def _reset(self) -> int:
        deleted, _ = User.objects.filter(username__startswith = PREFIX).delete()
        if deleted:
            self.stdout.write(f"Lot precedent supprime ({deleted} lignes).")
        return 0

    def _next_index(self) -> int:
        """Premier numero libre, pour que `--keep` ajoute sans entrer en collision.

        Les noms d'utilisateur du lot sont numerotes : repartir de zero sur un
        lot deja present ferait echouer la creation sur la contrainte d'unicite.
        """
        taken = [
            int(name[len(PREFIX):])
            for name in User.objects.filter(username__startswith = PREFIX)
                            .values_list("username", flat = True)
            if name[len(PREFIX):].isdigit()
        ]
        return max(taken) + 1 if taken else 0

    def _moderator(self) -> User:
        """Administrateur dedie au lot, cree si besoin.

        Les videos doivent etre validees par un acteur `ADMIN` : sans compte de
        moderation, la commande ne serait pas relancable sur une base vide.
        """
        moderator = User.objects.filter(username = ADMIN_USERNAME).first()
        if moderator is None:
            moderator = User.objects.create_user(
                ADMIN_USERNAME, None, PASSWORD, is_staff = True, is_superuser = True,
            )
            Role.objects.create(user = moderator, role = "Admin")
        return moderator

    def _create_profiles(self, start: int, count: int, videos: int, moderator: User) -> int:
        """Cree les profils, et une video pour les `videos` premiers.

        L'ordre importe : les profils qui portent une video sont les premiers
        crees, donc les plus anciens. Un tri par date de mise a jour ne les
        remonte pas artificiellement en tete du catalogue, ce qui evite de
        mesurer une page qui ne ressemblerait a aucune autre.
        """
        for offset, index in enumerate(range(start, start + count)):
            user    = self._create_user(index)
            profile = self._seed_profile(user, index)

            if offset < videos:
                self._submit_and_publish_video(profile, user, index, moderator)

            if (offset + 1) % 50 == 0:
                self.stdout.write(f"  {offset + 1} / {count} profils")

        return count

    def _create_user(self, index: int) -> User:
        user = User.objects.create_user(
            f"{PREFIX}{index:04d}", None, PASSWORD,
            first_name = f"Candidat{index:04d}", last_name = "Charge",
        )
        Role.objects.create(user = user, role = "JobSeeker")
        return user

    def _seed_profile(self, user: User, index: int):
        """Profil complet, passe par la couche de services comme n'importe quel
        profil rempli depuis l'interface.
        """
        profile = profile_services.get_profile(user)
        field   = self.random.choice(FIELDS)

        profile_services.update_profile(profile, {
            "headline":  f"{field} - profil de charge {index:04d}",
            "summary":   "Profil genere pour les tests de charge. "
                         "Il n'a pas vocation a etre consulte par un recruteur.",
            "location_city":    self.random.choice(CITIES),
            "location_country": "FR",
            "professional_field":  field,
            "availability_status": self.random.choice(AVAILABILITIES),
            "contract_types":      self.random.sample(CONTRACTS, k = self.random.randint(1, 3)),
            "open_to_remote": self.random.random() < 0.5,
            "open_to_hybrid": self.random.random() < 0.5,
            "open_to_onsite": self.random.random() < 0.5,
            "visibility": c.VISIBILITY_PUBLIC,
        })
        profile_services.update_search_settings(profile, {"searchable": True})

        for name in self.random.sample(SKILLS, k = self.random.randint(3, 8)):
            profile_services.add_skill(profile, {
                "name": name,
                "level": self.random.choice(LEVELS),
                "years_experience": self.random.randint(0, 12),
            })

        for code in self.random.sample(LANGUAGES, k = self.random.randint(1, 2)):
            profile_services.set_language(profile, {
                "language": code, "level": self.random.choice([v for v, _ in c.LANGUAGE_LEVELS]),
            })

        return profile

    def _submit_and_publish_video(self, profile, user: User, index: int, moderator: User):
        """Soumission, validation, publication : le cycle complet.

        Aucune de ces trois etapes n'est court-circuitee. `create_video`, la
        primitive interne qui ecrit directement une fiche publiee, n'est
        volontairement pas utilisee ici.
        """
        video = profile_services.submit_video_link(profile, {
            "title":       f"Presentation de Candidat{index:04d}",
            "description": "Video generee pour les tests de charge.",
            "file_url":    CLIPS[index % len(CLIPS)],
            "visibility":  c.VISIBILITY_PUBLIC,
        })
        profile_services.approve_video(video, user = moderator)
        profile_services.publish_presentation_video(video, user = user)

    def _summary(self, created: int, videos: int, seed: int):
        from profils.profiles.models import ProfessionalProfile, ProfileVideo

        published = ProfileVideo.objects.filter(
            status = c.VIDEO_PUBLISHED, profile__user__username__startswith = PREFIX,
        ).count()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"{created} profils crees, {published} videos publiees (graine {seed})."
        ))
        self.stdout.write(
            f"Total en base : {ProfessionalProfile.objects.count()} profils, "
            f"{ProfileVideo.objects.filter(status = c.VIDEO_PUBLISHED).count()} videos publiees."
        )
        if published != videos:
            self.stdout.write(self.style.WARNING(
                f"Attendu {videos} videos publiees, obtenu {published}."
            ))
