##tests/test_profile.py
"""Profil : creation, modification, consultation, visibilite (sections 2, 10, 11)."""

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from profils.profiles import constants as c
from profils.profiles import serializers, services
from profils.profiles.models import ProfessionalProfile, ProfileSearchSettings, ProfileVisibility
from profils.profiles.visibility import (
    PreviewViewer, can_view_profile, can_view_section, effective_section_visibility,
)

from .factories import add_skill, make_admin, make_profile, make_user


class CreationTests(TestCase):

    def test_a_profile_is_created_on_first_access(self):
        user = make_user("nouveau")
        self.assertFalse(ProfessionalProfile.objects.filter(user = user).exists())

        profile = services.get_profile(user)
        self.assertEqual(profile.user_id, user.id)
        self.assertEqual(profile.username, "nouveau")

    def test_settings_rows_are_created_with_the_profile(self):
        """Un profil sans reglages serait invisible en recherche : ils suivent."""
        profile = services.get_profile(make_user("regle"))

        self.assertTrue(ProfileVisibility.objects.filter(profile = profile).exists())
        self.assertTrue(ProfileSearchSettings.objects.filter(profile = profile).exists())
        self.assertTrue(profile.searchable)

    def test_get_profile_is_idempotent(self):
        user = make_user("stable")
        self.assertEqual(services.get_profile(user).pk, services.get_profile(user).pk)
        self.assertEqual(ProfessionalProfile.objects.filter(user = user).count(), 1)


class UpdateTests(TestCase):

    def setUp(self):
        self.profile = make_profile("candidat")

    def test_update_general_information(self):
        services.update_profile(self.profile, {
            "headline": "Developpeur backend Java",
            "summary":  "Sept ans de services distribues.",
            "first_name": "Camille",
            "last_name":  "Durand",
            "location_city": "Nantes",
            "location_country": "fr",
            "professional_field": c.FIELD_SOFTWARE,
        })
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.headline, "Developpeur backend Java")
        self.assertEqual(self.profile.location_country, "FR")
        self.assertEqual(self.profile.full_name, "Camille Durand")
        self.assertEqual(self.profile.location_label, "Nantes, FR")

    def test_update_availability_and_contracts(self):
        services.update_profile(self.profile, {
            "availability_status": c.AVAILABILITY_OPEN_TO_WORK,
            "available_from": "2026-01-15",
            "open_to_remote": True,
            "open_to_hybrid": True,
            "willing_to_relocate": True,
            "contract_types": [c.CONTRACT_CDI, c.CONTRACT_FREELANCE],
        })
        self.profile.refresh_from_db()

        self.assertTrue(self.profile.is_available)
        self.assertEqual(self.profile.available_from.isoformat(), "2026-01-15")
        self.assertEqual(sorted(self.profile.contract_type_codes()),
                         [c.CONTRACT_CDI, c.CONTRACT_FREELANCE])
        self.assertEqual(sorted(self.profile.work_modes),
                         sorted([c.WORK_MODE_REMOTE, c.WORK_MODE_HYBRID]))

    def test_contract_types_are_replaced_not_accumulated(self):
        services.set_contract_types(self.profile, [c.CONTRACT_CDI, c.CONTRACT_CDD])
        services.set_contract_types(self.profile, [c.CONTRACT_FREELANCE])
        self.assertEqual(self.profile.contract_type_codes(), [c.CONTRACT_FREELANCE])

    def test_a_partial_update_leaves_other_fields_alone(self):
        services.update_profile(self.profile, {"headline": "Titre"})
        services.update_profile(self.profile, {"summary": "Presentation"})
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.headline, "Titre")
        self.assertEqual(self.profile.summary, "Presentation")

    def test_computed_fields_cannot_be_written_by_the_client(self):
        """`total_experience_months` est calcule : une charge utile ne le fixe pas."""
        services.update_profile(self.profile, {
            "headline": "Titre", "total_experience_months": 9999,
        })
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_experience_months, 0)

    def test_an_invalid_choice_is_refused(self):
        from profils.questionnaires.http import BadRequest

        with self.assertRaises(BadRequest):
            services.update_profile(self.profile, {"professional_field": "ASTRONAUTE"})
        with self.assertRaises(BadRequest):
            services.update_profile(self.profile, {"visibility": "SEMI_PUBLIC"})

    def test_links_are_replaced_as_a_whole(self):
        services.set_links(self.profile, [
            {"kind": c.LINK_GITHUB, "url": "https://github.com/x"},
            {"kind": c.LINK_PORTFOLIO, "url": "https://x.dev", "label": "Portfolio"},
        ])
        self.assertEqual(self.profile.links.count(), 2)

        services.set_links(self.profile, [{"kind": c.LINK_WEBSITE, "url": "https://y.dev"}])
        self.assertEqual(self.profile.links.count(), 1)


class VisibilityTests(TestCase):

    def setUp(self):
        self.owner   = make_user("proprietaire")
        self.profile = make_profile(user = self.owner)
        self.other   = make_user("autre")
        add_skill(self.profile, "Java")

    def test_public_profile_is_visible_to_everyone(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PUBLIC})
        for viewer in (AnonymousUser(), self.other, self.owner):
            self.assertTrue(can_view_profile(viewer, self.profile))

    def test_registered_only_profile_hides_from_anonymous(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_REGISTERED_USERS})
        self.assertFalse(can_view_profile(AnonymousUser(), self.profile))
        self.assertTrue(can_view_profile(self.other, self.profile))

    def test_private_profile_is_visible_to_its_owner_only(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PRIVATE})
        self.assertFalse(can_view_profile(AnonymousUser(), self.profile))
        self.assertFalse(can_view_profile(self.other, self.profile))
        self.assertTrue(can_view_profile(self.owner, self.profile))

    def test_a_section_cannot_be_more_open_than_its_profile(self):
        """Regler ses competences sur PUBLIC ne les sort pas d'un profil prive."""
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PRIVATE})
        services.update_visibility(self.profile, {c.SECTION_SKILLS: c.VISIBILITY_PUBLIC})
        self.profile.refresh_from_db()

        self.assertEqual(
            effective_section_visibility(self.profile, c.SECTION_SKILLS),
            c.VISIBILITY_PRIVATE,
        )
        self.assertFalse(can_view_section(self.other, self.profile, c.SECTION_SKILLS))

    def test_a_section_can_be_more_restrictive_than_its_profile(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PUBLIC})
        services.update_visibility(self.profile, {c.SECTION_SKILLS: c.VISIBILITY_PRIVATE})
        self.profile.refresh_from_db()

        self.assertTrue(can_view_profile(self.other, self.profile))
        self.assertFalse(can_view_section(self.other, self.profile, c.SECTION_SKILLS))
        self.assertTrue(can_view_section(self.owner, self.profile, c.SECTION_SKILLS))

    def test_sections_are_configured_independently(self):
        services.update_visibility(self.profile, {
            c.SECTION_SKILLS:       c.VISIBILITY_PUBLIC,
            c.SECTION_EXPERIENCES:  c.VISIBILITY_PRIVATE,
            c.SECTION_AVAILABILITY: c.VISIBILITY_REGISTERED_USERS,
        })
        self.profile.refresh_from_db()

        self.assertTrue(can_view_section(self.other, self.profile, c.SECTION_SKILLS))
        self.assertFalse(can_view_section(self.other, self.profile, c.SECTION_EXPERIENCES))
        self.assertTrue(can_view_section(self.other, self.profile, c.SECTION_AVAILABILITY))
        self.assertFalse(can_view_section(AnonymousUser(), self.profile, c.SECTION_AVAILABILITY))

    def test_visibility_and_searchable_are_independent(self):
        """Un profil peut etre public et refuser d'apparaitre dans les recherches."""
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PUBLIC})
        services.update_search_settings(self.profile, {"searchable": False})
        self.profile.refresh_from_db()

        self.assertTrue(can_view_profile(AnonymousUser(), self.profile))
        self.assertFalse(self.profile.searchable)

    def test_an_unknown_visibility_value_is_treated_as_private(self):
        from profils.profiles.visibility import rank

        self.assertEqual(rank("N_IMPORTE_QUOI"), c.VISIBILITY_RANKS[c.VISIBILITY_PRIVATE])


class SerializationTests(TestCase):

    def setUp(self):
        self.owner   = make_user("serialise")
        self.profile = make_profile(user = self.owner, visibility = c.VISIBILITY_PUBLIC)
        self.other   = make_user("visiteur")
        add_skill(self.profile, "Java", c.LEVEL_ADVANCED, 3)

    def test_a_hidden_section_is_absent_from_the_payload(self):
        """Absente, pas presente avec un drapeau : une donnee envoyee est divulguee."""
        services.update_visibility(self.profile, {c.SECTION_SKILLS: c.VISIBILITY_PRIVATE})
        self.profile.refresh_from_db()

        payload = serializers.public_profile(self.profile, self.other)
        self.assertNotIn("skills", payload)
        self.assertFalse(payload["sections"][c.SECTION_SKILLS])

        owner_payload = serializers.public_profile(self.profile, self.owner)
        self.assertIn("skills", owner_payload)

    def test_owner_payload_carries_the_privacy_settings(self):
        payload = serializers.owner_profile(self.profile)
        self.assertIn("privacy", payload)
        self.assertIn("sections", payload["privacy"])
        self.assertTrue(payload["privacy"]["search"]["searchable"])

    def test_visitor_payload_never_carries_the_privacy_settings(self):
        payload = serializers.public_profile(self.profile, self.other)
        self.assertNotIn("privacy", payload)

    def test_preview_shows_the_owner_what_a_visitor_sees(self):
        services.update_visibility(self.profile, {c.SECTION_SKILLS: c.VISIBILITY_PRIVATE})
        self.profile.refresh_from_db()

        as_owner  = serializers.public_profile(self.profile, self.owner)
        as_public = serializers.public_profile(self.profile, PreviewViewer(c.AUDIENCE_ANONYMOUS))

        self.assertIn("skills", as_owner)
        self.assertNotIn("skills", as_public)

    def test_preview_can_only_restrict(self):
        """Un aperçu ne doit jamais ouvrir plus que l'audience simulee."""
        viewer = PreviewViewer(c.AUDIENCE_OWNER)
        self.assertEqual(viewer.audience, c.AUDIENCE_REGISTERED)

    def test_admin_may_read_a_private_profile(self):
        services.update_profile(self.profile, {"visibility": c.VISIBILITY_PRIVATE})
        self.profile.refresh_from_db()
        self.assertTrue(can_view_profile(make_admin(), self.profile))
