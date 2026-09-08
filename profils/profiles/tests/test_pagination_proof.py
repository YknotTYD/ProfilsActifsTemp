"""Commande `prove_pagination` : la preuve doit prouver, et savoir echouer.

Un script de verification qui reussit toujours ne verifie rien. La moitie de ce
fichier teste donc le chemin d'echec : listes divergentes, doublon, profil
oublie, total qui ne colle pas.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from profils.profiles import constants as c
from profils.profiles.management.commands.prove_pagination import Command
from profils.profiles.models import ProfessionalProfile
from profils.profiles.search import base_queryset

from .factories import make_profile, make_user

class ProvePaginationTests(TestCase):

    def setUp(self):
        for index in range(25):
            make_profile(f"profil-{index:02d}")
        ProfessionalProfile.objects.update(updated_at = "2026-09-08 08:00:00+00:00")

        self.directory = Path(tempfile.mkdtemp())

    def run_command(self, **options) -> Path:
        call_command(
            "prove_pagination", output_dir = str(self.directory),
            stdout = StringIO(), **options,
        )
        return self.directory

    def read_ids(self, name: str) -> list[int]:
        return [
            int(line) for line in (self.directory / name).read_text().splitlines() if line
        ]

    def test_the_three_files_are_written(self):
        self.run_command()
        for name in ("ids-passage-1.txt", "ids-passage-2.txt", "comparaison.txt"):
            self.assertTrue((self.directory / name).exists(), name)

    def test_both_passes_record_the_same_ids_in_the_same_order(self):
        self.run_command()
        self.assertEqual(self.read_ids("ids-passage-1.txt"),
                         self.read_ids("ids-passage-2.txt"))

    def test_the_walk_covers_every_visible_profile_exactly_once(self):
        self.run_command()
        ids = self.read_ids("ids-passage-1.txt")

        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            set(ids), set(base_queryset(AnonymousUser()).values_list("pk", flat = True))
        )

    def test_the_walk_spans_several_pages(self):
        """Sinon le test ne prouve rien de la pagination, seulement d'une page."""
        self.run_command(page_size = 10)
        self.assertEqual(len(self.read_ids("ids-passage-1.txt")), 25)

    def test_the_report_states_both_counts(self):
        """Le nombre de profils en base et le nombre de profils visibles.

        Ils different des qu'un profil est prive ou non recherchable : le
        rapport doit donner les deux, sans quoi l'ecart passe pour une perte.
        """
        make_profile("invisible", searchable = False)
        self.run_command()
        report = (self.directory / "comparaison.txt").read_text()

        self.assertIn("Profils en base                        : 26", report)
        self.assertIn("Profils visibles de ce visiteur        : 25", report)

    def test_an_unknown_user_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command(user = "personne")

    def test_a_known_user_is_accepted(self):
        make_user("recruteuse")
        self.run_command(user = "recruteuse")
        self.assertEqual(len(self.read_ids("ids-passage-1.txt")), 25)

    def test_every_sort_is_deterministic(self):
        for sort, _ in c.SORT_OPTIONS:
            with self.subTest(sort = sort):
                self.run_command(sort = sort)
                self.assertEqual(self.read_ids("ids-passage-1.txt"),
                                 self.read_ids("ids-passage-2.txt"))

class FailureDetectionTests(TestCase):
    """`_check` doit voir les pannes qu'il est cense voir."""

    def setUp(self):
        self.profiles = [make_profile(f"profil-{index}") for index in range(3)]
        self.ids      = sorted(profile.pk for profile in self.profiles)
        self.viewer   = AnonymousUser()
        self.check    = Command()._check

    def test_a_clean_walk_reports_nothing(self):
        self.assertEqual(self.check(self.ids, self.ids, 3, 3, self.viewer), [])

    def test_two_different_orders_are_caught(self):
        failures = self.check(self.ids, list(reversed(self.ids)), 3, 3, self.viewer)
        self.assertIn("meme liste", " ".join(failures))

    def test_a_duplicate_is_caught(self):
        duplicated = [self.ids[0]] + self.ids
        failures   = self.check(duplicated, duplicated, 4, 4, self.viewer)
        self.assertIn("plusieurs fois", " ".join(failures))

    def test_a_missing_profile_is_caught(self):
        truncated = self.ids[:-1]
        failures  = self.check(truncated, truncated, 2, 2, self.viewer)
        self.assertIn("aucune page", " ".join(failures))

    def test_a_total_that_does_not_match_is_caught(self):
        failures = self.check(self.ids, self.ids, 4, 4, self.viewer)
        self.assertIn("annonces par la pagination", " ".join(failures))

    def test_a_total_that_changes_between_passes_is_caught(self):
        failures = self.check(self.ids, self.ids, 3, 4, self.viewer)
        self.assertIn("total annonce a change", " ".join(failures))

class ExitCodeTests(TestCase):
    """Une verification en echec doit arreter la commande, pas la decorer.

    Le determinisme reel ne se met pas en panne sur commande : le contrat
    verifie ici est celui entre `_check` et `handle`, seul endroit ou un echec
    peut etre avale silencieusement.
    """

    def setUp(self):
        make_profile("profil")
        self.directory = Path(tempfile.mkdtemp())

    def run_command(self):
        call_command(
            "prove_pagination", output_dir = str(self.directory), stdout = StringIO(),
        )

    @patch.object(Command, "_check", return_value = ["panne simulee"])
    def test_a_failed_check_raises(self, _check):
        with self.assertRaises(CommandError):
            self.run_command()

    @patch.object(Command, "_check", return_value = ["panne simulee"])
    def test_the_report_is_written_even_when_the_command_fails(self, _check):
        with self.assertRaises(CommandError):
            self.run_command()

        report = (self.directory / "comparaison.txt").read_text()
        self.assertIn("ECHEC", report)
        self.assertIn("panne simulee", report)
