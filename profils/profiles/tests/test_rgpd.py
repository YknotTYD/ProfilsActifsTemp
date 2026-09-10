##tests/test_rgpd.py
"""Retrait du catalogue (RGPD art. 21) et journal de consultation (art. 15)."""

import json
from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from profils.mainapp.models import Role, VideoLink
from profils.mainapp.views import get_videos
from profils.profiles import constants as c
from profils.profiles import services
from profils.profiles.models import ProfileConsultation
from profils.profiles.search import ProfileQuery, search as run_search

from .factories import add_skill, make_profile, make_user


def make_recruiter(username = "recruteur", organisation = "Bureau Perrault"):
    user = make_user(username)
    Role.objects.create(user = user, role = "Recruiter", organisation = organisation)
    Group.objects.get_or_create(name = "recruiter")[0].user_set.add(user)
    return user


# --------------------------------------------------------------------------- #
# Retrait du catalogue — RGPD art. 21
# --------------------------------------------------------------------------- #

class WithdrawalTests(TestCase):

    def setUp(self):
        self.profile = make_profile("retire", visibility = c.VISIBILITY_PUBLIC)
        add_skill(self.profile, "Rust")
        self.owner  = self.profile.user
        self.client = Client()

    def _withdraw(self):
        services.withdraw_profile(self.profile)
        self.profile.refresh_from_db()

    def test_a_withdrawn_profile_disappears_from_search(self):
        self.assertEqual(
            [p.username for p in run_search(ProfileQuery.from_params({"skill": "rust"}), None)["profiles"]],
            ["retire"],
        )
        self._withdraw()
        self.assertEqual(
            list(run_search(ProfileQuery.from_params({"skill": "rust"}), None)["profiles"]), [],
        )

    def test_an_admin_search_does_not_bypass_the_withdrawal(self):
        self._withdraw()
        admin = make_user("staff", is_staff = True, is_superuser = True)
        self.assertEqual(
            list(run_search(ProfileQuery.from_params({"skill": "rust"}), admin)["profiles"]), [],
        )

    def test_a_withdrawn_profile_disappears_from_the_recruiter_feed(self):
        VideoLink.objects.create(user = self.owner, url = "https://youtu.be/x", status = "APPROVED")
        request = RequestFactory().get("/")
        request.user = make_recruiter()
        self.assertTrue(any(v["candidate"]["profile_url"].endswith("/retire/") for v in get_videos(request)))
        self._withdraw()
        self.assertFalse(any(v["candidate"]["profile_url"].endswith("/retire/") for v in get_videos(request)))

    def test_a_direct_link_to_a_withdrawn_profile_shows_the_neutral_404(self):
        self._withdraw()
        response = self.client.get(f"/profile/{self.owner.username}/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Cette page n'existe pas", status_code = 404)
        # aucun message specifique au retrait, qui trahirait l'inscription
        self.assertNotContains(response, "compte en retrait", status_code = 404)
        self.assertNotContains(response, "mis son compte", status_code = 404)

    def test_withdrawn_private_and_unknown_answer_identically(self):
        """Meme reponse pour retire / prive / inexistant : comparer deux
        reponses ne doit pas reveler qu'une personne etait inscrite."""
        import re

        def body(path):
            response = self.client.get(path)
            # le jeton CSRF et le hash de version des CSS varient a chaque
            # reponse : on les neutralise, tout le reste doit etre identique.
            html = re.sub(rb'content="[^"]{20,}"', b'content="X"', response.content)
            html = re.sub(rb'\?v=\d+', b'?v=X', html)
            return response.status_code, html

        self._withdraw()
        other = make_profile("prive", visibility = c.VISIBILITY_PRIVATE)

        withdrawn = body(f"/profile/{self.owner.username}/")
        private   = body(f"/profile/{other.username}/")
        unknown   = body("/profile/personne-de-ce-nom-la/")

        self.assertEqual(withdrawn, unknown)
        self.assertEqual(withdrawn, private)

    def test_the_owner_still_sees_their_profile_with_a_banner(self):
        self._withdraw()
        self.client.force_login(self.owner)
        response = self.client.get(f"/profile/{self.owner.username}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "retiré du catalogue")

    def test_the_api_also_refuses_a_withdrawn_profile(self):
        self._withdraw()
        self.assertEqual(
            self.client.get(f"/api/profiles/{self.owner.username}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/profiles/{self.owner.username}/videos/").status_code, 404,
        )

    def test_the_withdrawal_is_reversible_by_its_owner(self):
        self.client.force_login(self.owner)
        self.client.post("/api/profiles/me/withdrawal/", data = json.dumps({"action": "withdraw"}),
                         content_type = "application/json")
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_withdrawn)

        self.client.post("/api/profiles/me/withdrawal/", data = json.dumps({"action": "restore"}),
                         content_type = "application/json")
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_withdrawn)
        self.assertEqual(
            [p.username for p in run_search(ProfileQuery.from_params({"skill": "rust"}), None)["profiles"]],
            ["retire"],
        )


# --------------------------------------------------------------------------- #
# Journal de consultation — RGPD art. 15
# --------------------------------------------------------------------------- #

class ConsultationLogTests(TestCase):

    def setUp(self):
        self.profile = make_profile("consulte", visibility = c.VISIBILITY_PUBLIC)
        self.owner   = self.profile.user
        self.client  = Client()

    def _visit(self, user = None):
        cl = Client()
        if user is not None:
            cl.force_login(user)
        return cl.get(f"/profile/{self.owner.username}/")

    def test_a_recruiter_visit_is_logged_with_the_organisation_only(self):
        self._visit(make_recruiter(organisation = "Fonderie du Val"))
        row = ProfileConsultation.objects.get(profile = self.profile)
        self.assertEqual(row.organisation, "Fonderie du Val")

    def test_the_log_stores_no_ip_no_user_agent_no_account(self):
        fields = {f.name for f in ProfileConsultation._meta.get_fields()}
        self.assertEqual(fields, {"id", "profile", "organisation", "created_at"})

    def test_an_anonymous_visit_is_not_logged(self):
        self._visit(None)
        self.assertFalse(ProfileConsultation.objects.exists())

    def test_the_owner_visiting_their_own_page_is_not_logged(self):
        self._visit(self.owner)
        self.assertFalse(ProfileConsultation.objects.exists())

    def test_a_plain_registered_user_is_not_logged(self):
        self._visit(make_user("simple"))
        self.assertFalse(ProfileConsultation.objects.exists())

    def test_two_close_visits_by_the_same_organisation_count_once(self):
        recruiter = make_recruiter(organisation = "Meme Boite")
        self._visit(recruiter)
        self._visit(recruiter)
        self.assertEqual(ProfileConsultation.objects.filter(profile = self.profile).count(), 1)

    def test_a_visit_outside_the_dedup_window_is_logged_again(self):
        recruiter = make_recruiter(organisation = "Meme Boite")
        self._visit(recruiter)
        ProfileConsultation.objects.filter(profile = self.profile).update(
            created_at = timezone.now() - timedelta(minutes = c.CONSULTATION_DEDUP_MINUTES + 1),
        )
        self._visit(recruiter)
        self.assertEqual(ProfileConsultation.objects.filter(profile = self.profile).count(), 2)

    def test_a_recruiter_without_an_organisation_shows_a_neutral_label(self):
        self._visit(make_recruiter("sans_orga", organisation = ""))
        row = ProfileConsultation.objects.get(profile = self.profile)
        self.assertEqual(row.organisation, c.CONSULTATION_UNKNOWN_ORGANISATION)

    def test_the_journal_page_requires_authentication(self):
        self.assertEqual(Client().get("/profiles/me/consultations/").status_code, 302)

    def test_the_journal_page_lists_organisations_and_states_its_limits(self):
        self._visit(make_recruiter(organisation = "Fonderie du Val"))
        self.client.force_login(self.owner)
        response = self.client.get("/profiles/me/consultations/")
        self.assertContains(response, "Fonderie du Val")
        self.assertContains(response, "décompte exhaustif")
        self.assertContains(response, "Jamais le nom")
