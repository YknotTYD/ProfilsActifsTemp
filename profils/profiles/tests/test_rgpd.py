##tests/test_rgpd.py
"""Retrait du catalogue (RGPD art. 21) et journal de consultation (art. 15)."""

from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.utils import timezone

from profils.mainapp.models import Role
from profils.profiles import constants as c
from profils.profiles import services
from profils.profiles.models import ProfileConsultation
from profils.profiles.search import ProfileQuery, search as run_search

from .factories import add_skill, add_video, make_profile, make_user


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
        services.set_catalogue_withdrawal(self.profile, True)
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

    def test_a_withdrawn_profile_disappears_from_the_video_feed(self):
        add_video(self.profile, status = c.VIDEO_PUBLISHED, file_url = "https://youtu.be/x")
        from profils.profiles.feed import dashboard_feed
        recruiter = make_recruiter()
        self.assertTrue(any(v.profile_id == self.profile.pk for v in dashboard_feed(recruiter)))
        self._withdraw()
        self.assertFalse(any(v.profile_id == self.profile.pk for v in dashboard_feed(recruiter)))

    def test_a_direct_link_to_a_withdrawn_profile_shows_a_sober_page(self):
        self._withdraw()
        response = self.client.get(f"/profile/{self.owner.username}/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "n'est pas disponible", status_code = 404)
        # ne revele ni le nom, ni le pseudo
        self.assertNotContains(response, self.owner.username, status_code = 404)

    def test_withdrawn_private_and_unknown_all_answer_identically(self):
        import re

        def body(path):
            response = self.client.get(path)
            # le jeton CSRF est aleatoire a chaque reponse : on le neutralise
            # avant comparaison, tout le reste doit etre identique.
            html = re.sub(rb'content="[^"]{20,}"', b'content="X"', response.content)
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

    def test_the_withdrawal_is_reversible_by_its_owner(self):
        self.client.force_login(self.owner)
        self.client.put("/api/profiles/me/privacy/", data = '{"withdrawn": true}',
                        content_type = "application/json")
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_withdrawn)

        self.client.put("/api/profiles/me/privacy/", data = '{"withdrawn": false}',
                        content_type = "application/json")
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_withdrawn)
        # le profil est de nouveau trouvable
        self.assertEqual(
            [p.username for p in run_search(ProfileQuery.from_params({"skill": "rust"}), None)["profiles"]],
            ["retire"],
        )

    def test_re_withdrawing_keeps_the_first_date(self):
        self._withdraw()
        first = self.profile.withdrawn_at
        services.set_catalogue_withdrawal(self.profile, True)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.withdrawn_at, first)


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

    def test_the_journal_page_is_visible_only_to_its_owner(self):
        self.assertEqual(Client().get("/profiles/me/consultations/").status_code, 302)

    def test_the_journal_page_lists_organisations_and_states_its_limits(self):
        self._visit(make_recruiter(organisation = "Fonderie du Val"))
        self.client.force_login(self.owner)
        response = self.client.get("/profiles/me/consultations/")
        self.assertContains(response, "Fonderie du Val")
        self.assertContains(response, "decompte exhaustif")
        self.assertContains(response, "Jamais le nom")
