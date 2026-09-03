##tests/test_security.py
"""Securite : propriete, visibilite, fuites de donnees (section 25).

Ces tests attaquent le systeme par l'API, pas par les services : c'est la
surface qu'un client hostile atteint reellement. Le frontend n'est jamais
considere comme fiable.
"""

import json

from django.test import Client, TestCase

from profils.profiles import constants as c
from profils.profiles import services
from profils.profiles.models import ProfessionalProfile
from profils.profiles.permissions import ProfileAccessDenied, assert_can_edit

from .factories import (
    add_certification, add_education, add_experience, add_project, add_skill,
    add_video, make_admin, make_profile, make_user,
)


class ApiTestCase(TestCase):
    """Base des tests d'API : un client, deux comptes, un profil de chacun."""

    def setUp(self):
        self.client = Client()
        self.owner   = make_user("proprietaire")
        self.attacker = make_user("intrus")
        self.profile  = make_profile(user = self.owner, visibility = c.VISIBILITY_PUBLIC)
        self.other    = make_profile(user = self.attacker)

    def as_owner(self):
        self.client.force_login(self.owner)

    def as_attacker(self):
        self.client.force_login(self.attacker)

    def put(self, url, payload):
        return self.client.put(url, data = json.dumps(payload),
                               content_type = "application/json")

    def post(self, url, payload):
        return self.client.post(url, data = json.dumps(payload),
                                content_type = "application/json")

    def json(self, response):
        return json.loads(response.content or b"{}")


class OwnershipTests(ApiTestCase):
    """Nul ne modifie les donnees professionnelles d'autrui."""

    def test_me_always_resolves_to_the_caller(self):
        self.as_attacker()
        self.put("/api/profiles/me/", {"headline": "Pirate"})

        self.profile.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.profile.headline, "")
        self.assertEqual(self.other.headline, "Pirate")

    def test_an_experience_of_another_profile_cannot_be_updated(self):
        experience = add_experience(self.profile, title = "Original")

        self.as_attacker()
        response = self.put(f"/api/profiles/me/experiences/{experience.pk}/",
                            {"title": "Detourne"})

        self.assertEqual(response.status_code, 404)
        experience.refresh_from_db()
        self.assertEqual(experience.title, "Original")

    def test_an_experience_of_another_profile_cannot_be_deleted(self):
        experience = add_experience(self.profile)

        self.as_attacker()
        response = self.client.delete(f"/api/profiles/me/experiences/{experience.pk}/")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.profile.experiences.filter(pk = experience.pk).exists())

    def test_every_section_is_protected_the_same_way(self):
        targets = {
            "experiences":    add_experience(self.profile).pk,
            "education":      add_education(self.profile).pk,
            "certifications": add_certification(self.profile).pk,
            "projects":       add_project(self.profile).pk,
            "videos":         add_video(self.profile).pk,
        }

        self.as_attacker()
        for section, pk in targets.items():
            response = self.client.delete(f"/api/profiles/me/{section}/{pk}/")
            self.assertEqual(response.status_code, 404, section)

    def test_a_skill_of_another_profile_cannot_be_updated(self):
        row = add_skill(self.profile, "Java", c.LEVEL_BEGINNER)

        self.as_attacker()
        response = self.put(f"/api/profiles/me/skills/{row.skill_id}/",
                            {"level": c.LEVEL_EXPERT})

        self.assertEqual(response.status_code, 404)
        row.refresh_from_db()
        self.assertEqual(row.level, c.LEVEL_BEGINNER)

    def test_writing_requires_authentication(self):
        for url in ("/api/profiles/me/", "/api/profiles/me/skills/",
                    "/api/profiles/me/privacy/"):
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_the_service_layer_refuses_a_foreign_profile(self):
        with self.assertRaises(ProfileAccessDenied):
            assert_can_edit(self.attacker, self.profile)
        with self.assertRaises(ProfileAccessDenied):
            assert_can_edit(None, self.profile)


class PrivateProfileTests(ApiTestCase):

    def test_a_private_profile_answers_404_to_a_stranger(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PRIVATE})

        self.as_attacker()
        response = self.client.get(f"/api/profiles/{self.owner.username}/")
        self.assertEqual(response.status_code, 404)

    def test_it_answers_404_rather_than_403(self):
        """Repondre "interdit" confirmerait que ce compte a un profil."""
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PRIVATE})

        self.as_attacker()
        real    = self.client.get(f"/api/profiles/{self.owner.username}/")
        missing = self.client.get("/api/profiles/personne-de-ce-nom/")
        self.assertEqual(real.status_code, missing.status_code)

    def test_the_page_answers_404_too(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PRIVATE})

        self.as_attacker()
        self.assertEqual(
            self.client.get(f"/profile/{self.owner.username}/").status_code, 404
        )

    def test_the_owner_still_reaches_it(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PRIVATE})

        self.as_owner()
        self.assertEqual(
            self.client.get(f"/api/profiles/{self.owner.username}/").status_code, 200
        )

    def test_a_registered_only_profile_is_hidden_from_anonymous(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_REGISTERED_USERS})

        self.assertEqual(
            self.client.get(f"/api/profiles/{self.owner.username}/").status_code, 404
        )
        self.as_attacker()
        self.assertEqual(
            self.client.get(f"/api/profiles/{self.owner.username}/").status_code, 200
        )


class DataLeakTests(ApiTestCase):
    """Une donnee envoyee au navigateur est une donnee divulguee."""

    def setUp(self):
        super().setUp()
        add_skill(self.profile, "Java", c.LEVEL_EXPERT, 8)
        add_experience(self.profile, title = "Poste confidentiel")
        services.update_profile(self.profile, {
            "availability_status": c.AVAILABILITY_OPEN_TO_WORK,
        })

    def test_a_hidden_section_is_absent_from_the_response(self):
        services.update_visibility(self.profile, {
            c.SECTION_EXPERIENCES: c.VISIBILITY_PRIVATE,
        })

        self.as_attacker()
        payload = self.json(self.client.get(f"/api/profiles/{self.owner.username}/"))

        self.assertNotIn("experiences", payload)
        self.assertNotIn("Poste confidentiel", json.dumps(payload))

    def test_the_privacy_settings_never_reach_a_visitor(self):
        self.as_attacker()
        payload = self.json(self.client.get(f"/api/profiles/{self.owner.username}/"))
        self.assertNotIn("privacy", payload)

    def test_a_hidden_availability_does_not_leak_through_search(self):
        services.update_visibility(self.profile, {
            c.SECTION_AVAILABILITY: c.VISIBILITY_PRIVATE,
        })

        self.as_attacker()
        payload = self.json(self.client.get("/api/profiles/search/?skill=java"))
        card = next(row for row in payload["results"]
                    if row["username"] == self.owner.username)
        self.assertNotIn("availability", card)

    def test_hidden_skills_do_not_leak_through_a_search_card(self):
        """Un profil peut etre trouvable sans etre entierement lisible."""
        services.update_visibility(self.profile, {c.SECTION_SKILLS: c.VISIBILITY_PRIVATE})

        self.as_attacker()
        payload = self.json(self.client.get("/api/profiles/search/?skill=java"))
        card = next(row for row in payload["results"]
                    if row["username"] == self.owner.username)

        self.assertNotIn("skills", card)
        self.assertEqual(card["match"]["skills"], 1)   # trouvable, mais muet

    def test_an_anonymous_visitor_gets_no_more_than_a_registered_one(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PUBLIC})
        services.update_visibility(self.profile, {
            c.SECTION_AVAILABILITY: c.VISIBILITY_REGISTERED_USERS,
        })

        anonymous = self.json(self.client.get(f"/api/profiles/{self.owner.username}/"))
        self.assertNotIn("availability", anonymous)


class SearchableBypassTests(ApiTestCase):
    """Section 28.5 : le drapeau `searchable` ne se contourne pas."""

    def setUp(self):
        super().setUp()
        services.update_search_settings(self.profile, {"searchable": False})
        add_skill(self.profile, "Java", c.LEVEL_EXPERT, 10)

    def _search(self, query = "?skill=java"):
        return self.json(self.client.get(f"/api/profiles/search/{query}"))["results"]

    def _found_usernames(self, query = "?skill=java"):
        return [row["username"] for row in self._search(query)]

    def test_it_holds_for_an_anonymous_visitor(self):
        self.assertEqual(self._search(), [])

    def test_it_holds_for_a_registered_visitor(self):
        self.as_attacker()
        self.assertEqual(self._search(), [])

    def test_it_holds_for_an_administrator(self):
        self.client.force_login(make_admin())
        self.assertEqual(self._search(), [])

    def test_no_filter_combination_brings_it_back(self):
        """Y compris les recherches larges, qui renvoient d'autres profils."""
        self.as_attacker()
        for query in ("?skill=java", "?q=proprietaire", "?available=1",
                      "?sort=recent", "?page_size=50", "?mode=OR&skills=java",
                      "?field=SOFTWARE", ""):
            self.assertNotIn(self.owner.username, self._found_usernames(query), query)

    def test_the_owner_does_not_find_themself_either(self):
        """Le reglage vaut pour tout le monde, y compris son auteur."""
        self.as_owner()
        self.assertEqual(self._search(), [])

    def test_the_profile_remains_reachable_by_its_url(self):
        self.as_attacker()
        response = self.client.get(f"/api/profiles/{self.owner.username}/")
        self.assertEqual(response.status_code, 200)


class InputTamperingTests(ApiTestCase):

    def test_computed_fields_are_ignored(self):
        self.as_owner()
        self.put("/api/profiles/me/", {
            "headline": "Titre", "total_experience_months": 9000,
        })
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_experience_months, 0)

    def test_a_skill_level_rank_cannot_be_forged(self):
        row = add_skill(self.profile, "Java", c.LEVEL_BEGINNER)

        self.as_owner()
        self.put(f"/api/profiles/me/skills/{row.skill_id}/",
                 {"level": c.LEVEL_BEGINNER, "level_rank": 99})

        row.refresh_from_db()
        self.assertEqual(row.level_rank, c.SKILL_LEVEL_RANKS[c.LEVEL_BEGINNER])

    def test_an_invalid_payload_answers_400_not_500(self):
        self.as_owner()
        for url, payload in (
            ("/api/profiles/me/", {"visibility": "SEMI_PUBLIC"}),
            ("/api/profiles/me/", {"professional_field": "ASTRONAUTE"}),
        ):
            self.assertEqual(self.put(url, payload).status_code, 400)

    def test_an_invalid_search_parameter_answers_400(self):
        response = self.client.get("/api/profiles/search/?min_level=GODLIKE")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.json(response)["code"], "invalid_field")

    def test_a_wrong_method_answers_405(self):
        self.as_owner()
        self.assertEqual(self.client.delete("/api/profiles/me/").status_code, 405)

    def test_preview_cannot_widen_what_is_shown(self):
        """`?preview=` sert a voir moins, jamais plus."""
        services.update_visibility(self.profile, {c.SECTION_SKILLS: c.VISIBILITY_PRIVATE})
        add_skill(self.profile, "Java")

        self.as_attacker()
        payload = self.json(self.client.get(
            f"/api/profiles/{self.owner.username}/?preview=registered"
        ))
        self.assertNotIn("skills", payload)


class UrlSchemeTests(ApiTestCase):
    """Un lien, une fois affiche en `<a href>`, doit rester un lien HTTP(S).

    Django echappe le texte d'un attribut, mais l'echappement n'empeche pas un
    schema `javascript:` de s'executer quand la personne clique le lien : la
    seule protection reelle est de refuser le schema a l'ecriture.
    """

    def setUp(self):
        super().setUp()
        self.as_owner()

    def _refused(self, url, payload):
        response = self.put(url, payload)
        self.assertEqual(response.status_code, 400, payload)
        self.assertEqual(self.json(response)["code"], "invalid_field")

    def test_a_javascript_scheme_link_is_refused(self):
        response = self.put("/api/profiles/me/links/", {
            "links": [{"kind": c.LINK_WEBSITE, "url": "javascript:alert(document.cookie)"}],
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.profile.links.count(), 0)

    def test_a_data_scheme_photo_is_refused(self):
        self._refused("/api/profiles/me/", {"photo_url": "data:text/html,<script>1</script>"})

    def test_project_and_certification_urls_are_validated_too(self):
        project = services.create_project(self.profile, {"title": "P"})
        self._refused(f"/api/profiles/me/projects/{project.pk}/",
                      {"url": "javascript:evil()"})

        certification = add_certification(self.profile)
        self._refused(f"/api/profiles/me/certifications/{certification.pk}/",
                      {"verification_url": "javascript:evil()"})

    def test_a_normal_https_link_is_accepted(self):
        response = self.put("/api/profiles/me/links/", {
            "links": [{"kind": c.LINK_GITHUB, "url": "https://github.com/example"}],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.profile.links.count(), 1)


class MalformedInputCrashTests(ApiTestCase):
    """Une entree malformee doit repondre 400, jamais planter en 500."""

    def test_reordering_with_a_non_numeric_id_answers_400(self):
        self.as_owner()
        add_skill(self.profile, "Java")
        response = self.post("/api/profiles/me/skills/reorder/", {"skills": ["pas-un-nombre"]})
        self.assertEqual(response.status_code, 400)

    def test_a_non_numeric_search_limit_answers_400(self):
        response = self.client.get("/api/skills/?limit=abc")
        self.assertEqual(response.status_code, 400)


class ProfileCreationSafetyTests(TestCase):

    def test_reading_a_profile_never_creates_one_for_someone_else(self):
        owner  = make_user("cible")
        make_profile(user = owner, visibility = c.VISIBILITY_PUBLIC)
        visitor = make_user("curieux")

        client = Client()
        client.force_login(visitor)
        client.get(f"/api/profiles/{owner.username}/")

        self.assertFalse(
            ProfessionalProfile.objects.filter(user = visitor).exists()
        )
