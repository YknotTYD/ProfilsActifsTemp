import json

from django.contrib.auth.models import User
from django.test import Client, TestCase

from profils.notifications import types as notification_types
from profils.notifications.models import Notification

from profils.profiles.tests.factories import add_video, make_profile

from . import constants
from .models import Role, VideoLink

class NavbarConsistencyTests(TestCase):
    """La barre de navigation est la meme sur toutes les pages (context
    processor `navigation`), et distingue l'administrateur."""

    PAGES = ("/", "/profiles/", "/questionnaires/", "/messages/", "/profile/")

    def _body(self, client, path):
        return client.get(path, follow = True).content.decode()

    def test_an_admin_sees_the_admin_menu_on_every_page(self):
        admin = User.objects.create_user("adm", None, None, is_superuser = True, is_staff = True)
        client = Client(); client.force_login(admin)
        for path in self.PAGES:
            body = self._body(client, path)
            self.assertIn("topbar", body, path)
            self.assertIn("Administration", body, path)
            self.assertIn("/profiles/admin/videos/", body, path)

    def test_a_plain_user_never_sees_the_admin_menu(self):
        user = User.objects.create_user("js", None, None)
        Role.objects.create(user = user, role = "JobSeeker")
        client = Client(); client.force_login(user)
        for path in self.PAGES:
            self.assertNotIn("Administration", self._body(client, path), path)

    def test_an_anonymous_visitor_gets_the_sign_in_actions(self):
        body = Client().get("/").content.decode()
        self.assertIn("Se connecter", body)
        self.assertNotIn("notif-bell", body)

class ReactionNotificationTests(TestCase):
    """Section 5 : "like recu", "dislike recu"."""

    def setUp(self):
        self.owner = User.objects.create_user("proprietaire", None, None)
        self.reactor = User.objects.create_user("reacteur", None, None)
        self.video = VideoLink.objects.create(user = self.owner, url = "https://exemple.test/v.mp4")
        self.client = Client()
        self.client.force_login(self.reactor)

    def _react(self, reaction):
        return self.client.post(
            "/api/react/", data = json.dumps({"video_id": self.video.id, "reaction": reaction}),
            content_type = "application/json",
        )

    def test_a_like_notifies_the_owner(self):
        self._react("like")
        notif = Notification.objects.get(recipient = self.owner)
        self.assertEqual(notif.type, notification_types.VIDEO_LIKED)

    def test_a_dislike_notifies_the_owner(self):
        self._react("dislike")
        notif = Notification.objects.get(recipient = self.owner)
        self.assertEqual(notif.type, notification_types.VIDEO_DISLIKED)

    def test_removing_a_reaction_does_not_notify_again(self):
        self._react("like")
        self._react("like")
        self.assertEqual(Notification.objects.filter(recipient = self.owner).count(), 1)

    def test_reacting_to_ones_own_video_does_not_notify(self):
        self.client.force_login(self.owner)
        self._react("like")
        self.assertFalse(Notification.objects.filter(recipient = self.owner).exists())

class CandidateGridTests(TestCase):
    """Points 3.2 et 3.4 : une grille paginee, une lecture sur clic.

    Le feed vertical plein ecran est retire. Ce qui le remplace tient en deux
    promesses verifiables depuis le HTML rendu : vingt profils par page, et
    aucune video qui demarre toute seule.
    """

    PAGE_SIZE = constants.CANDIDATE_GRID_PAGE_SIZE

    def setUp(self):
        self.recruiter = User.objects.create_user("recruteur", None, None)
        Role.objects.create(user = self.recruiter, role = "Recruiter")
        self.client = Client()
        self.client.force_login(self.recruiter)

    def _make_videos(self, count):
        """`count` profils, chacun avec une video de presentation publiee.

        La grille lit `profiles.ProfileVideo` via `_visible_video_filter`
        (pipeline unifie) : un profil public et recherchable, avec une video
        `PUBLISHED`, est exactement ce qu'elle affiche.
        """
        for i in range(count):
            add_video(make_profile(f"candidat{i:03d}"), title = f"Video {i:03d}")

    def _cards(self, response):
        return response.content.decode().count("data-cgrid-player")

    def test_a_page_holds_at_most_twenty_profiles(self):
        self._make_videos(self.PAGE_SIZE + 5)
        self.assertEqual(self._cards(self.client.get("/")), self.PAGE_SIZE)

    def test_the_next_page_holds_the_rest(self):
        self._make_videos(self.PAGE_SIZE + 5)
        self.assertEqual(self._cards(self.client.get("/?page=2")), 5)

    def test_a_single_page_shows_no_pagination(self):
        self._make_videos(3)
        body = self.client.get("/").content.decode()
        self.assertEqual(self._cards(self.client.get("/")), 3)
        self.assertNotIn("cgrid-pagination", body)

    def test_a_page_number_out_of_range_falls_back_instead_of_failing(self):
        """Un vieux lien `?page=99` doit rendre une page, jamais une erreur."""
        self._make_videos(self.PAGE_SIZE + 5)
        for page in ("99", "0", "abc", ""):
            response = self.client.get("/", {"page": page})
            self.assertEqual(response.status_code, 200, page)
            self.assertGreater(self._cards(response), 0, page)

    def test_no_video_starts_on_its_own(self):
        """Lecture a la demande : la page rendue ne porte aucun demarrage.

        Ni attribut `autoplay`, ni parametre d'URL d'integration : le lecteur
        n'existe qu'apres le clic, construit par `candidates_grid.js`.
        """
        self._make_videos(3)

        body = self.client.get("/").content.decode()

        self.assertIn("data-cgrid-player", body)
        for forbidden in ("autoplay", "<video", "<iframe", "loop", "muted"):
            self.assertNotIn(forbidden, body, forbidden)

    def test_a_job_seeker_gets_no_grid(self):
        self._make_videos(3)
        seeker = User.objects.create_user("chercheur", None, None)
        Role.objects.create(user = seeker, role = "JobSeeker")
        client = Client(); client.force_login(seeker)

        self.assertNotIn("data-cgrid-player", client.get("/").content.decode())

    def test_the_empty_state_replaces_the_grid(self):
        body = self.client.get("/").content.decode()
        self.assertNotIn("cgrid-list", body)
        self.assertIn("Aucune vidéo pour le moment", body)


class AccessibilityTests(TestCase):
    """Points RGAA structurels : lien d'evitement, landmark principal,
    declaration d'accessibilite liee depuis le pied de page."""

    PAGES = ("/", "/login/", "/register/", "/cgu/", "/accessibilite/")

    def test_every_page_carries_a_skip_link_to_the_main_landmark(self):
        for path in self.PAGES:
            body = self.client.get(path).content.decode()
            self.assertIn('class="skip-link" href="#main-content"', body, path)
            self.assertIn('id="main-content"', body, path)

    def test_authenticated_pages_also_carry_the_main_landmark(self):
        user = User.objects.create_user("js", None, None)
        Role.objects.create(user = user, role = "JobSeeker")
        client = Client(); client.force_login(user)
        for path in ("/", "/profiles/", "/questionnaires/", "/messages/", "/profile/"):
            body = client.get(path, follow = True).content.decode()
            self.assertIn('id="main-content"', body, path)

    def test_accessibility_statement_is_reachable_and_linked_in_the_footer(self):
        response = self.client.get("/accessibilite/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Déclaration d'accessibilité")
        self.assertContains(response, "RGAA")
        home = self.client.get("/").content.decode()
        self.assertIn('href="/accessibilite/"', home)
