"""Commande `seed_volume` : le jeu de donnees doit passer par l'application.

Le point verifie ici n'est pas le nombre de lignes, facile a obtenir, mais le
chemin qu'elles ont emprunte. Un jeu de donnees ecrit directement en base
contournerait la moderation, ne produirait aucun evenement d'historique, et ne
mesurerait donc rien du code que la campagne de charge est censee eprouver.
"""

from io import StringIO

from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from profils.profiles import constants as c
from profils.profiles.models import ProfessionalProfile, ProfileVideo, VideoModerationEvent
from profils.profiles.search import base_queryset

PREFIX = "charge-"

class SeedVolumeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        call_command("seed_volume", profiles = 6, with_video = 4, stdout = StringIO())

    def profiles(self):
        return ProfessionalProfile.objects.filter(user__username__startswith = PREFIX)

    def test_the_requested_number_of_profiles_is_created(self):
        self.assertEqual(self.profiles().count(), 6)

    def test_the_requested_number_of_videos_is_published(self):
        published = ProfileVideo.objects.filter(
            status = c.VIDEO_PUBLISHED, profile__user__username__startswith = PREFIX,
        )
        self.assertEqual(published.count(), 4)

    def test_every_video_went_through_the_full_moderation_cycle(self):
        """Soumission, validation, publication : trois etapes, trois evenements.

        C'est la verification qui distingue ce jeu de donnees d'un
        `bulk_create` : une video ecrite directement en base n'a pas
        d'historique de moderation.
        """
        for video in ProfileVideo.objects.filter(
            profile__user__username__startswith = PREFIX,
        ):
            statuses = list(
                VideoModerationEvent.objects
                .filter(video = video).order_by("id").values_list("new_status", flat = True)
            )
            self.assertEqual(
                statuses, [c.VIDEO_APPROVED, c.VIDEO_PUBLISHED], video.title,
            )

    def test_the_videos_are_submitted_as_links_not_written_as_files(self):
        for video in ProfileVideo.objects.filter(
            profile__user__username__startswith = PREFIX,
        ):
            self.assertEqual(video.source_type, c.VIDEO_SOURCE_LINK)
            self.assertTrue(video.file_url)

    def test_the_profiles_are_findable_by_a_recruiter(self):
        """Un profil que la recherche ne trouve pas ne charge rien du tout."""
        visible = base_queryset(AnonymousUser()).filter(
            user__username__startswith = PREFIX,
        )
        self.assertEqual(visible.count(), 6)

    def test_the_profiles_carry_skills_and_languages(self):
        for profile in self.profiles():
            self.assertGreaterEqual(profile.skills.count(), 3)
            self.assertGreaterEqual(profile.languages.count(), 1)

    def test_a_moderator_account_is_created_so_the_command_runs_on_an_empty_base(self):
        self.assertTrue(User.objects.filter(username = "charge-moderateur").exists())

class ReRunTests(TestCase):
    """La commande doit etre relancable, et ne rien toucher hors de son lot."""

    def seed(self, **options):
        call_command("seed_volume", stdout = StringIO(), **options)

    def test_a_second_run_replaces_the_batch_instead_of_stacking_it(self):
        self.seed(profiles = 4, with_video = 2)
        self.seed(profiles = 4, with_video = 2)

        self.assertEqual(
            User.objects.filter(username__startswith = PREFIX)
                .exclude(username = "charge-moderateur").count(),
            4,
        )

    def test_keep_adds_to_the_existing_batch(self):
        self.seed(profiles = 3, with_video = 1)
        self.seed(profiles = 3, with_video = 1, keep = True)

        self.assertEqual(
            ProfessionalProfile.objects.filter(user__username__startswith = PREFIX).count(),
            6,
        )

    def test_accounts_outside_the_batch_are_never_touched(self):
        User.objects.create_user("recruteuse", None, None)
        self.seed(profiles = 2, with_video = 1)
        self.seed(profiles = 2, with_video = 1)

        self.assertTrue(User.objects.filter(username = "recruteuse").exists())

    def test_the_same_seed_produces_the_same_data(self):
        self.seed(profiles = 5, with_video = 2, seed = 1234)
        first = list(
            ProfessionalProfile.objects
            .filter(user__username__startswith = PREFIX)
            .order_by("user__username")
            .values_list("professional_field", "location_city", "availability_status")
        )

        self.seed(profiles = 5, with_video = 2, seed = 1234)
        second = list(
            ProfessionalProfile.objects
            .filter(user__username__startswith = PREFIX)
            .order_by("user__username")
            .values_list("professional_field", "location_city", "availability_status")
        )

        self.assertEqual(first, second)

    def test_more_videos_than_profiles_is_refused(self):
        with self.assertRaises(CommandError):
            self.seed(profiles = 2, with_video = 5)
