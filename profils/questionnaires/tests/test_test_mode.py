##tests/test_test_mode.py
"""Mode TEST (section 24) : ne doit polluer ni les statistiques ni les badges."""

from django.test import TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.access     import AccessDenied
from profils.questionnaires.models     import QuestionnaireAttempt, QuestionnaireResult, UserBadge
from profils.questionnaires.services   import finish_attempt, save_answer, start_attempt
from profils.questionnaires.versioning import publish_version, set_version_test

from .factories import (
    add_single_choice, draft_of, make_admin, make_badge, make_questionnaire, make_user, publish,
)


class TestModeTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.version  = draft_of(self.q)
        self.question = add_single_choice(self.version, self.admin)
        self.java = self.question.options.get(text = "Java")

    def to_test_mode(self):
        set_version_test(self.version, actor = self.admin)
        self.q.refresh_from_db()
        self.version.refresh_from_db()

    def run_test_attempt(self):
        attempt = start_attempt(self.q, self.admin, test = True)
        save_answer(attempt, self.question.id, {"option_ids": [self.java.id]})
        return attempt, finish_attempt(attempt)

    def test_a_test_version_is_frozen(self):
        self.to_test_mode()
        self.assertEqual(self.version.status, c.STATUS_TEST)
        self.assertFalse(self.version.is_editable)

    def test_a_questionnaire_in_test_mode_is_not_public(self):
        self.to_test_mode()
        with self.assertRaises(AccessDenied) as ctx:
            start_attempt(self.q, self.user)
        self.assertEqual(ctx.exception.code, "questionnaire_not_published")

    def test_a_regular_user_cannot_run_a_test_attempt(self):
        self.to_test_mode()
        with self.assertRaises(AccessDenied) as ctx:
            start_attempt(self.q, self.user, test = True)
        self.assertEqual(ctx.exception.code, "test_forbidden")

    def test_an_administrator_can_test_before_publication(self):
        self.to_test_mode()
        attempt = start_attempt(self.q, self.admin, test = True)
        self.assertTrue(attempt.is_test)
        self.assertEqual(attempt.version_id, self.version.id)

    def test_test_attempts_are_flagged_and_separated(self):
        self.to_test_mode()
        attempt, result = self.run_test_attempt()

        self.assertTrue(attempt.is_test)
        self.assertTrue(result.is_test)
        self.assertEqual(QuestionnaireAttempt.objects.filter(is_test = False).count(), 0)
        self.assertEqual(QuestionnaireResult.objects.filter(is_test = False).count(), 0)

    def test_test_results_stay_out_of_real_statistics(self):
        self.to_test_mode()
        self.run_test_attempt()

        publish_version(self.version, actor = self.admin)
        self.q.refresh_from_db()

        real_attempt = start_attempt(self.q, self.user)
        save_answer(real_attempt, self.question.id, {"option_ids": [self.java.id]})
        finish_attempt(real_attempt)

        self.assertEqual(QuestionnaireResult.objects.filter(is_test = False).count(), 1)
        self.assertEqual(QuestionnaireResult.objects.filter(is_test = True).count(), 1)
        self.assertEqual(
            QuestionnaireResult.objects.filter(is_test = False).first().user_id, self.user.id)

    def test_a_test_attempt_never_awards_a_real_badge(self):
        make_badge("REUSSITE", criteria = {"type": "questionnaire_passed"})
        self.to_test_mode()

        _, result = self.run_test_attempt()

        self.assertTrue(result.passed)
        self.assertEqual(UserBadge.objects.count(), 0)

    def test_a_real_attempt_does_award_the_badge(self):
        make_badge("REUSSITE", criteria = {"type": "questionnaire_passed"})
        publish(self.q, self.admin)
        self.q.refresh_from_db()

        attempt = start_attempt(self.q, self.user)
        save_answer(attempt, self.question.id, {"option_ids": [self.java.id]})
        finish_attempt(attempt)

        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 1)

    def test_test_attempts_do_not_consume_the_real_quota(self):
        self.q.max_attempts = 1
        self.q.save()
        self.to_test_mode()
        self.run_test_attempt()

        publish_version(self.version, actor = self.admin)
        self.q.refresh_from_db()

        attempt = start_attempt(self.q, self.admin)
        self.assertFalse(attempt.is_test)
        self.assertEqual(attempt.attempt_number, 1)

    def test_a_test_attempt_and_a_real_attempt_coexist(self):
        publish(self.q, self.admin)
        self.q.refresh_from_db()

        real = start_attempt(self.q, self.admin, test = False)
        test = start_attempt(self.q, self.admin, test = True)

        self.assertNotEqual(real.id, test.id)
        self.assertFalse(real.is_test)
        self.assertTrue(test.is_test)

    def test_the_full_test_then_publish_workflow(self):
        """TEST -> verifier -> modifier -> nouvelle version -> tester -> publier."""
        from profils.questionnaires.editing    import update_question
        from profils.questionnaires.versioning import editable_version

        self.to_test_mode()
        self.run_test_attempt()

        second = editable_version(self.q, actor = self.admin)
        self.assertEqual(second.version_number, 2)
        update_question(second.questions.first(), {"text": "Enonce corrige"}, actor = self.admin)

        set_version_test(second, actor = self.admin)
        publish_version(second, actor = self.admin)

        self.q.refresh_from_db()
        self.assertEqual(self.q.status, c.STATUS_PUBLISHED)
        self.assertEqual(self.q.current_version_id, second.id)

        attempt = start_attempt(self.q, self.user)
        self.assertEqual(attempt.version_id, second.id)
        self.assertFalse(attempt.is_test)
