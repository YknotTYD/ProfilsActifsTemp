##tests/test_badges.py
"""Badges (section 21) : modele, relations et API prets, affichage non branche."""

from django.test import Client, TestCase

from profils.questionnaires.badges import user_badges
from profils.questionnaires.models import UserBadge
from profils.questionnaires.services import finish_attempt, save_answer, start_attempt

from .factories import (
    add_single_choice, draft_of, make_admin, make_badge, make_questionnaire, make_user, publish,
)


class BadgeModelTests(TestCase):

    def test_a_badge_is_unique_per_user(self):
        badge = make_badge("UNIQUE")
        user  = make_user("titulaire")
        UserBadge.objects.create(user = user, badge = badge)

        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UserBadge.objects.create(user = user, badge = badge)

    def test_relations_are_navigable_in_both_directions(self):
        badge = make_badge("REL")
        user  = make_user("titulaire")
        UserBadge.objects.create(user = user, badge = badge)

        self.assertEqual(user.badges.count(), 1)
        self.assertEqual(badge.holders.count(), 1)


class BadgeAwardTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.question = add_single_choice(draft_of(self.q), self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()
        self.java  = self.question.options.get(text = "Java")
        self.cobol = self.question.options.get(text = "COBOL")

    def play(self, option, user = None):
        attempt = start_attempt(self.q, user or self.user)
        save_answer(attempt, self.question.id, {"option_ids": [option.id]})
        return finish_attempt(attempt)

    def test_passed_criterion(self):
        make_badge("PASSED", criteria = {"type": "questionnaire_passed", "questionnaire": self.q.id})
        self.play(self.java)
        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 1)

    def test_failure_awards_nothing(self):
        make_badge("PASSED", criteria = {"type": "questionnaire_passed", "questionnaire": self.q.id})
        self.play(self.cobol)
        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 0)

    def test_minimum_percentage_criterion(self):
        make_badge("EXCELLENCE", criteria = {
            "type": "min_percentage", "questionnaire": self.q.id, "percentage": 90})
        self.play(self.java)
        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 1)

    def test_criterion_bound_to_another_questionnaire_is_ignored(self):
        other = make_questionnaire(self.admin, title = "Autre")
        make_badge("AUTRE", criteria = {"type": "questionnaire_passed", "questionnaire": other.id})
        self.play(self.java)
        self.assertEqual(UserBadge.objects.count(), 0)

    def test_an_inactive_badge_is_never_awarded(self):
        make_badge("INACTIF", active = False,
                   criteria = {"type": "questionnaire_passed", "questionnaire": self.q.id})
        self.play(self.java)
        self.assertEqual(UserBadge.objects.count(), 0)

    def test_a_badge_is_not_awarded_twice(self):
        make_badge("PASSED", criteria = {"type": "questionnaire_passed", "questionnaire": self.q.id})
        self.q.allow_retry_after_pass = True
        self.q.save()

        self.play(self.java)
        self.play(self.java)
        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 1)

    def test_the_award_records_its_source(self):
        make_badge("PASSED", criteria = {"type": "questionnaire_passed", "questionnaire": self.q.id})
        result = self.play(self.java)

        held = UserBadge.objects.get(user = self.user)
        self.assertEqual(held.source_result_id, result.pk)
        self.assertEqual(held.source, "QUESTIONNAIRE_RESULT")
        self.assertFalse(held.is_test)

    def test_a_multi_questionnaire_criterion(self):
        second = make_questionnaire(self.admin, title = "Second")
        q2 = add_single_choice(draft_of(second), self.admin)
        publish(second, self.admin)
        second.refresh_from_db()

        make_badge("SERIE", criteria = {
            "type": "questionnaires_passed", "questionnaires": [self.q.id, second.id]})

        self.play(self.java)
        self.assertEqual(UserBadge.objects.count(), 0)

        attempt = start_attempt(second, self.user)
        save_answer(attempt, q2.id, {"option_ids": [q2.options.get(text = "Java").id]})
        finish_attempt(attempt)
        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 1)


class BadgeApiTests(TestCase):

    def setUp(self):
        self.user  = make_user("titulaire")
        self.other = make_user("autre")
        self.admin = make_admin()
        self.badge = make_badge("BASIC_COMPLETED", name = "Bases acquises")
        UserBadge.objects.create(user = self.user, badge = self.badge)

    def test_a_user_reads_their_own_badges(self):
        client = Client()
        client.force_login(self.user)

        response = client.get(f"/api/users/{self.user.id}/badges/")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["user"], "titulaire")
        self.assertEqual(len(payload["badges"]), 1)
        self.assertEqual(payload["badges"][0]["code"], "BASIC_COMPLETED")

    def test_another_user_is_refused(self):
        client = Client()
        client.force_login(self.other)
        self.assertEqual(client.get(f"/api/users/{self.user.id}/badges/").status_code, 403)

    def test_an_administrator_may_read_any_badges(self):
        client = Client()
        client.force_login(self.admin)
        self.assertEqual(client.get(f"/api/users/{self.user.id}/badges/").status_code, 200)

    def test_anonymous_access_is_refused(self):
        self.assertEqual(Client().get(f"/api/users/{self.user.id}/badges/").status_code, 401)

    def test_the_serialised_payload_carries_everything_needed(self):
        payload = user_badges(self.user)[0]
        for key in ("code", "name", "description", "icon", "level", "awarded_at", "source"):
            self.assertIn(key, payload)
