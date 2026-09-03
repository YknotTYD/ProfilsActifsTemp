##tests/test_pages.py
"""Rendu des pages : la page de profil est lisible sans JavaScript.

Ces tests ne verifient pas l'ergonomie, seulement que le HTML se produit sans
erreur et que ce qu'il contient respecte les memes regles de visibilite que
l'API : ce sont deux chemins de rendu differents pour les memes donnees, et
les deux doivent obeir a la meme regle.
"""

from django.test import Client, TestCase

from profils.profiles import constants as c
from profils.profiles import services

from .factories import (
    add_certification, add_education, add_experience, add_language, add_project,
    add_skill, add_video, make_admin, make_profile, make_user,
)


class ProfilePageTests(TestCase):

    def setUp(self):
        self.owner   = make_user("rendu")
        self.profile = make_profile(user = self.owner, visibility = c.VISIBILITY_PUBLIC)
        self.client  = Client()

    def test_a_minimal_profile_renders(self):
        response = self.client.get(f"/profile/{self.owner.username}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.owner.username)

    def test_a_fully_populated_profile_renders(self):
        add_skill(self.profile, "Java", c.LEVEL_EXPERT, 5)
        add_experience(self.profile, title = "Developpeur", skills = ["Java"])
        add_education(self.profile, skills = ["Java"])
        add_certification(self.profile, skills = ["Java"])
        add_project(self.profile, skills = ["Java"])
        add_language(self.profile, "fr", c.CEFR_NATIVE)
        add_video(self.profile, skills = ["Java"])
        services.set_links(self.profile, [{"kind": c.LINK_GITHUB, "url": "https://github.com/x"}])
        services.update_profile(self.profile, {
            "headline": "Developpeur backend", "summary": "Sept ans d'experience.",
            "availability_status": c.AVAILABILITY_OPEN_TO_WORK,
            "contract_types": [c.CONTRACT_CDI],
        })

        response = self.client.get(f"/profile/{self.owner.username}/")
        self.assertEqual(response.status_code, 200)
        for text in ("Java", "Developpeur", "Certifications", "Projets", "Video de presentation", "GitHub"):
            self.assertContains(response, text, msg_prefix = text)

    def test_a_hidden_section_produces_no_html_at_all(self):
        add_experience(self.profile, title = "Poste secret")
        services.update_visibility(self.profile, {c.SECTION_EXPERIENCES: c.VISIBILITY_PRIVATE})

        response = self.client.get(f"/profile/{self.owner.username}/")
        self.assertNotContains(response, "Poste secret")

    def test_a_private_profile_returns_404_as_html(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PRIVATE})
        response = self.client.get(f"/profile/{self.owner.username}/")
        self.assertEqual(response.status_code, 404)

    def test_an_unknown_username_returns_404(self):
        response = self.client.get("/profile/personne-de-ce-nom/")
        self.assertEqual(response.status_code, 404)

    def test_the_owner_preview_renders_as_a_visitor_would_see_it(self):
        add_skill(self.profile, "Java")
        services.update_visibility(self.profile, {c.SECTION_SKILLS: c.VISIBILITY_PRIVATE})

        self.client.force_login(self.owner)
        response = self.client.get(f"/profile/{self.owner.username}/?preview=public")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Java")

    def test_empty_video_section_renders_a_placeholder(self):
        response = self.client.get(f"/profile/{self.owner.username}/")
        self.assertContains(response, "pas encore publie de video")


class SearchPageTests(TestCase):

    def test_the_search_page_renders(self):
        response = Client().get("/profiles/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rechercher des profils")

    def test_it_renders_with_query_parameters(self):
        response = Client().get("/profiles/?skill=java&min_level=ADVANCED&sort=experience")
        self.assertEqual(response.status_code, 200)

    def test_an_invalid_query_parameter_does_not_crash_the_page(self):
        response = Client().get("/profiles/?min_level=GODLIKE")
        self.assertEqual(response.status_code, 200)

    def test_a_skill_in_the_url_is_resolved_to_its_name_for_the_token(self):
        """Le JS hydrate ses jetons depuis ce JSON : sans lui un lien partage perd son filtre."""
        skill = add_skill(make_profile("porteur"), "Rust").skill

        response = Client().get(f"/profiles/?skill={skill.slug}")
        self.assertContains(response, '"name": "Rust"')
        self.assertContains(response, f'"id": {skill.id}')


class EditorPageTests(TestCase):

    def test_requires_authentication(self):
        response = Client().get("/profiles/edit/")
        self.assertEqual(response.status_code, 302)

    def test_renders_for_a_logged_in_user(self):
        user = make_user("editeur")
        client = Client()
        client.force_login(user)
        response = client.get("/profiles/edit/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modifier mon profil")


class MyVideoPageTests(TestCase):
    """`/profiles/me/video/` : une seule video de presentation a la fois."""

    def setUp(self):
        self.profile = make_profile("candidat")
        self.owner   = self.profile.user
        self.admin   = make_admin()
        self.client  = Client()
        self.client.force_login(self.owner)

    def test_requires_authentication(self):
        response = Client().get("/profiles/me/video/")
        self.assertEqual(response.status_code, 302)

    def test_renders_the_empty_state(self):
        response = self.client.get("/profiles/me/video/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pas encore de video de presentation")

    def test_submitting_a_link_creates_a_pending_video(self):
        response = self.client.post("/profiles/me/video/", {
            "action": "submit", "title": "Ma video", "file_url": "https://exemple.test/v.mp4",
        })
        self.assertRedirects(response, "/profiles/me/video/")

        from profils.profiles.models import ProfileVideo
        video = ProfileVideo.objects.get(profile = self.profile)
        self.assertEqual(video.status, "PENDING")

    def test_an_empty_link_shows_an_error_instead_of_crashing(self):
        response = self.client.post("/profiles/me/video/", {
            "action": "submit", "title": "Ma video", "file_url": "",
        }, follow = True)
        self.assertEqual(response.status_code, 200)

        from profils.profiles.models import ProfileVideo
        self.assertFalse(ProfileVideo.objects.filter(profile = self.profile).exists())

    def test_the_full_lifecycle_shows_the_old_video_until_confirmation(self):
        from profils.profiles import services

        old = services.submit_video_link(self.profile, {
            "title": "Ancienne", "file_url": "https://exemple.test/old.mp4",
        })
        services.approve_video(old, user = self.admin)
        services.publish_presentation_video(old, user = self.owner)

        response = self.client.get("/profiles/me/video/")
        self.assertContains(response, "Ancienne")

        self.client.post("/profiles/me/video/", {
            "action": "submit", "title": "Nouvelle", "file_url": "https://exemple.test/new.mp4",
        })
        response = self.client.get("/profiles/me/video/")
        self.assertContains(response, "Ancienne")
        self.assertContains(response, "Nouvelle")

        new = old.replaced_by.get()
        services.approve_video(new, user = self.admin)

        response = self.client.get("/profiles/me/video/")
        self.assertContains(response, "Ancienne")
        self.assertContains(response, "Publier et remplacer")

        self.client.post("/profiles/me/video/", {"action": "publish"})
        response = self.client.get("/profiles/me/video/")
        self.assertContains(response, "Nouvelle")
        self.assertNotContains(response, "Ancienne")


class AdminVideosPageTests(TestCase):
    """`/profiles/admin/videos/` : la meme garde que la console questionnaires."""

    def test_requires_authentication(self):
        response = Client().get("/profiles/admin/videos/")
        self.assertEqual(response.status_code, 302)

    def test_a_regular_user_gets_404_not_403(self):
        client = Client()
        client.force_login(make_user("candidat"))
        response = client.get("/profiles/admin/videos/")
        self.assertEqual(response.status_code, 404)

    def test_an_admin_can_open_it(self):
        client = Client()
        client.force_login(make_admin())
        response = client.get("/profiles/admin/videos/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Moderation des videos de profil")


class RedirectTests(TestCase):

    def test_profile_root_redirects_to_my_profile_when_authenticated(self):
        user = make_user("moi")
        client = Client()
        client.force_login(user)
        response = client.get("/profile/")
        self.assertRedirects(response, f"/profile/{user.username}/")

    def test_profile_root_requires_authentication(self):
        response = Client().get("/profile/")
        self.assertEqual(response.status_code, 302)
