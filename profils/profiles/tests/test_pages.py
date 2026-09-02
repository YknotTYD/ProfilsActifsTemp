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
    add_skill, add_video, make_profile, make_user,
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
        for text in ("Java", "Developpeur", "Certifications", "Projets", "Videos", "GitHub"):
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
