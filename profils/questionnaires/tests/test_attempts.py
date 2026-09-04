
from datetime import timedelta

from django.test  import TestCase
from django.utils import timezone

from profils.questionnaires import constants as c
from profils.questionnaires.models   import QuestionnaireAttempt
from profils.questionnaires.services import (
    AttemptError, abandon_attempt, current_attempt, expire_stale_attempts,
    finish_attempt, save_answer, start_attempt,
)

from .factories import (
    add_single_choice, add_temperature, draft_of, make_admin, make_questionnaire,
    make_user, publish,
)

class AttemptBaseTest(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.version  = draft_of(self.q)
        self.question = add_single_choice(self.version, self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()
        self.version.refresh_from_db()

    def answer_correctly(self, attempt):
        option = self.question.options.get(text = "Java")
        return save_answer(attempt, self.question.id, {"option_ids": [option.id]})

class AttemptLifecycleTests(AttemptBaseTest):

    def test_start_binds_the_attempt_to_the_exact_version(self):
        attempt = start_attempt(self.q, self.user)
        self.assertEqual(attempt.version_id, self.version.id)
        self.assertEqual(attempt.status, c.ATTEMPT_IN_PROGRESS)
        self.assertEqual(attempt.attempt_number, 1)
        self.assertFalse(attempt.is_test)

    def test_start_is_idempotent_while_an_attempt_is_open(self):
        first  = start_attempt(self.q, self.user)
        second = start_attempt(self.q, self.user)
        self.assertEqual(first.id, second.id)
        self.assertEqual(QuestionnaireAttempt.objects.filter(user = self.user).count(), 1)

    def test_resume_restores_answers_and_progress(self):
        attempt = start_attempt(self.q, self.user)
        self.answer_correctly(attempt)

        resumed = current_attempt(self.q, self.user)
        self.assertEqual(resumed.id, attempt.id)
        self.assertEqual(resumed.answered_count, 1)
        self.assertEqual(str(resumed.progress_percent), "100.00")
        self.assertEqual(resumed.answers.count(), 1)

    def test_completed_attempt_is_not_resumed(self):
        attempt = start_attempt(self.q, self.user)
        self.answer_correctly(attempt)
        finish_attempt(attempt)

        self.assertIsNone(current_attempt(self.q, self.user))

    def test_abandon(self):
        attempt = start_attempt(self.q, self.user)
        abandon_attempt(attempt)
        self.assertEqual(attempt.status, c.ATTEMPT_ABANDONED)
        self.assertIsNone(current_attempt(self.q, self.user))

    def test_answering_a_closed_attempt_is_refused(self):
        attempt = start_attempt(self.q, self.user)
        abandon_attempt(attempt)
        with self.assertRaises(AttemptError):
            self.answer_correctly(attempt)

    def test_finish_requires_mandatory_answers(self):
        attempt = start_attempt(self.q, self.user)
        with self.assertRaises(AttemptError) as ctx:
            finish_attempt(attempt)
        self.assertEqual(ctx.exception.code, "missing_required")

        finish_attempt(attempt, force = True)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, c.ATTEMPT_COMPLETED)

    def test_finish_twice_returns_the_same_result(self):
        attempt = start_attempt(self.q, self.user)
        self.answer_correctly(attempt)
        first  = finish_attempt(attempt)
        second = finish_attempt(attempt)
        self.assertEqual(first.pk, second.pk)

class AttemptQuotaTests(AttemptBaseTest):

    def complete_one(self, user):
        attempt = start_attempt(self.q, user)
        self.answer_correctly(attempt)
        return finish_attempt(attempt)

    def test_single_attempt_limit(self):
        self.q.max_attempts = 1
        self.q.save()

        self.complete_one(self.user)
        with self.assertRaises(AttemptError) as ctx:
            start_attempt(self.q, self.user)
        self.assertEqual(ctx.exception.code, "attempt_limit_reached")

    def test_maximum_of_three_attempts(self):
        self.q.max_attempts           = 3
        self.q.allow_retry_after_pass = True
        self.q.save()

        for expected in (1, 2, 3):
            attempt = start_attempt(self.q, self.user)
            self.assertEqual(attempt.attempt_number, expected)
            self.answer_correctly(attempt)
            finish_attempt(attempt)

        with self.assertRaises(AttemptError):
            start_attempt(self.q, self.user)

    def test_unlimited_attempts_by_default(self):
        self.q.allow_retry_after_pass = True
        self.q.save()
        for _ in range(4):
            attempt = start_attempt(self.q, self.user)
            self.answer_correctly(attempt)
            finish_attempt(attempt)
        self.assertEqual(QuestionnaireAttempt.objects.filter(user = self.user).count(), 4)

    def test_cooldown_between_attempts(self):
        self.q.cooldown_seconds       = 3600
        self.q.allow_retry_after_pass = True
        self.q.save()

        self.complete_one(self.user)
        with self.assertRaises(AttemptError) as ctx:
            start_attempt(self.q, self.user)
        self.assertEqual(ctx.exception.code, "cooldown_active")

    def test_retry_after_success_is_refused_by_default(self):
        self.complete_one(self.user)
        with self.assertRaises(AttemptError) as ctx:
            start_attempt(self.q, self.user)
        self.assertEqual(ctx.exception.code, "already_passed")

    def test_retry_after_failure_can_be_refused(self):
        self.q.allow_retry_after_fail = False
        self.q.save()

        attempt = start_attempt(self.q, self.user)
        wrong   = self.question.options.get(text = "COBOL")
        save_answer(attempt, self.question.id, {"option_ids": [wrong.id]})
        result = finish_attempt(attempt)
        self.assertFalse(result.passed)

        with self.assertRaises(AttemptError) as ctx:
            start_attempt(self.q, self.user)
        self.assertEqual(ctx.exception.code, "retry_after_fail_denied")

    def test_previous_attempts_are_kept(self):
        self.q.allow_retry_after_pass = True
        self.q.save()
        self.complete_one(self.user)
        self.complete_one(self.user)
        self.assertEqual(QuestionnaireAttempt.objects.filter(user = self.user).count(), 2)

class ExpirationTests(AttemptBaseTest):

    def test_attempt_expires_after_its_deadline(self):
        self.q.attempt_expiry_seconds = 7 * 24 * 3600
        self.q.save()

        attempt = start_attempt(self.q, self.user)
        self.assertIsNotNone(attempt.expires_at)

        attempt.expires_at = timezone.now() - timedelta(minutes = 1)
        attempt.save(update_fields = ["expires_at"])

        self.assertIsNone(current_attempt(self.q, self.user))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, c.ATTEMPT_EXPIRED)

    def test_expired_attempt_refuses_new_answers(self):
        attempt = start_attempt(self.q, self.user)
        attempt.expires_at = timezone.now() - timedelta(minutes = 1)
        attempt.save(update_fields = ["expires_at"])

        with self.assertRaises(AttemptError) as ctx:
            self.answer_correctly(attempt)
        self.assertIn(ctx.exception.code, ("attempt_expired", "attempt_closed"))

    def test_bulk_expiration_sweep(self):
        attempt = start_attempt(self.q, self.user)
        attempt.expires_at = timezone.now() - timedelta(days = 1)
        attempt.save(update_fields = ["expires_at"])

        self.assertEqual(expire_stale_attempts(), 1)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, c.ATTEMPT_EXPIRED)

    def test_questionnaire_availability_window(self):
        self.q.available_from  = timezone.now() + timedelta(days = 1)
        self.q.available_until = timezone.now() + timedelta(days = 2)
        self.q.save()

        from profils.questionnaires.access import AccessDenied

        with self.assertRaises(AccessDenied) as ctx:
            start_attempt(self.q, make_user("autre"))
        self.assertEqual(ctx.exception.code, "outside_availability")

    def test_version_validity_window(self):
        self.version.valid_until = timezone.now() - timedelta(days = 1)
        self.version.save()

        from profils.questionnaires.access import AccessDenied

        with self.assertRaises(AccessDenied) as ctx:
            start_attempt(self.q, make_user("autre"))
        self.assertEqual(ctx.exception.code, "version_expired")

class InvalidationTests(AttemptBaseTest):

    def test_invalidated_questionnaire_refuses_new_attempts(self):
        from profils.questionnaires.versioning import invalidate_version
        from profils.questionnaires.access     import AccessDenied

        invalidate_version(self.version, actor = self.admin, reason = "erreur")

        with self.assertRaises(AccessDenied):
            start_attempt(self.q, make_user("autre"))

    def test_invalidating_a_version_closes_open_attempts(self):
        from profils.questionnaires.versioning import invalidate_version

        attempt = start_attempt(self.q, self.user)
        invalidate_version(self.version, actor = self.admin)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, c.ATTEMPT_INVALIDATED)

class AnswerEditingRulesTests(AttemptBaseTest):

    def test_answers_locked_on_validation(self):
        self.q.answer_edit_mode = c.ANSWERS_LOCKED_ON_VALIDATE
        self.q.save()

        attempt = start_attempt(self.q, self.user)
        self.answer_correctly(attempt)

        with self.assertRaises(AttemptError) as ctx:
            self.answer_correctly(attempt)
        self.assertIn(ctx.exception.code, ("answer_locked", "answer_not_editable"))

    def test_answers_are_editable_until_the_end_by_default(self):
        attempt = start_attempt(self.q, self.user)
        java   = self.question.options.get(text = "Java")
        cobol  = self.question.options.get(text = "COBOL")

        save_answer(attempt, self.question.id, {"option_ids": [cobol.id]})
        save_answer(attempt, self.question.id, {"option_ids": [java.id]})

        answer = attempt.answers.get()
        self.assertEqual(answer.value["option_ids"], [java.id])
        self.assertEqual(answer.revision, 2)

    def test_answers_are_locked_once_the_attempt_is_finished(self):
        attempt = start_attempt(self.q, self.user)
        self.answer_correctly(attempt)
        finish_attempt(attempt)

        self.assertTrue(attempt.answers.get().locked)
        with self.assertRaises(AttemptError):
            self.answer_correctly(attempt)

class MultiQuestionProgressTests(TestCase):

    def test_progress_counts_only_visible_questions(self):
        admin = make_admin()
        user  = make_user("candidat")
        q     = make_questionnaire(admin)
        version = draft_of(q)

        first  = add_single_choice(version, admin, text = "Q1")
        add_temperature(version, admin)
        publish(q, admin)

        attempt = start_attempt(q, user)
        self.assertEqual(attempt.visible_count, 2)
        self.assertEqual(attempt.answered_count, 0)

        save_answer(attempt, first.id, {"option_ids": [first.options.first().id]})
        attempt.refresh_from_db()
        self.assertEqual(attempt.answered_count, 1)
        self.assertEqual(str(attempt.progress_percent), "50.00")
