"""Report des reponses lors de la publication d'une nouvelle version."""

from decimal import Decimal

from django.test import Client, TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.carryover  import carry_over, preview
from profils.questionnaires.editing    import create_question, delete_question, update_question
from profils.questionnaires.models     import (
    QuestionnaireAttempt, QuestionnaireResult, UserAnswer,
)
from profils.questionnaires.services   import (
    AttemptError, finish_attempt, save_answer, start_attempt,
)
from profils.questionnaires.versioning import editable_version, publish_version

from .factories import add_single_choice, draft_of, make_admin, make_questionnaire, make_user

class CarryOverTestCase(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.alice = make_user("alice")
        self.bob   = make_user("bob")

        self.q  = make_questionnaire(self.admin, title = "Quiz")
        self.v1 = draft_of(self.q)
        self.choice = add_single_choice(self.v1, self.admin, text = "Langage ?")
        self.number = create_question(self.v1, {
            "type": c.TYPE_INTEGER, "text": "2 + 2 ?",
            "expected_config": {"rules": [{"type": "exact", "value": 4}]},
        }, actor = self.admin)
        publish_version(self.v1, actor = self.admin)
        self.q.refresh_from_db()

    def play(self, user, *, option = "Java", value = 4, finish = True):
        attempt = start_attempt(self.q, user)
        save_answer(attempt, self.choice.id,
                    {"option_ids": [self.choice.options.get(text = option).id]})
        if value is not None:
            save_answer(attempt, self.number.id, value)
        return finish_attempt(attempt) if finish else attempt

    def new_version(self):
        self.q.refresh_from_db()
        return editable_version(self.q, actor = self.admin)

    def attempt_on(self, user, version):
        return QuestionnaireAttempt.objects.filter(user = user, version = version).first()

class CompletedAttemptTests(CarryOverTestCase):

    def test_the_old_result_is_never_touched(self):
        result = self.play(self.alice)
        before = (result.pk, result.score, result.percentage, result.version_id)

        version = self.new_version()
        publish_version(version, actor = self.admin)

        result.refresh_from_db()
        self.assertEqual((result.pk, result.score, result.percentage, result.version_id), before)
        self.assertEqual(result.version_id, self.v1.id)

    def test_a_successor_attempt_is_created_with_the_previous_answers(self):
        original = self.play(self.alice).attempt
        version  = self.new_version()
        publish_version(version, actor = self.admin)

        successor = self.attempt_on(self.alice, version)
        self.assertIsNotNone(successor)
        self.assertNotEqual(successor.pk, original.pk)
        self.assertEqual(successor.carried_from_id, original.pk)
        self.assertEqual(successor.answers.count(), 2)
        self.assertTrue(all(a.carried for a in successor.answers.all()))

    def test_option_answers_are_remapped_by_stable_key(self):
        """Les identifiants d'options changent d'une version a l'autre."""
        self.play(self.alice)
        version = self.new_version()
        publish_version(version, actor = self.admin)

        clone     = version.questions.get(stable_key = self.choice.stable_key)
        successor = self.attempt_on(self.alice, version)
        answer    = successor.answers.get(question = clone)

        expected = clone.options.get(text = "Java").id
        self.assertEqual(answer.value["option_ids"], [expected])
        self.assertNotEqual(expected, self.choice.options.get(text = "Java").id)
        self.assertEqual(answer.selections.get().option_stable_key,
                         self.choice.options.get(text = "Java").stable_key)

    def test_without_new_questions_the_score_is_recomputed_at_once(self):
        first = self.play(self.alice)

        version = self.new_version()
        publish_version(version, actor = self.admin)

        successor = self.attempt_on(self.alice, version)
        self.assertEqual(successor.status, c.ATTEMPT_COMPLETED)

        results = QuestionnaireResult.objects.filter(user = self.alice).order_by("computed_at")
        self.assertEqual(results.count(), 2)
        self.assertEqual(results.first().pk, first.pk)
        self.assertEqual(results.last().version_id, version.id)

    def test_a_scoring_change_produces_a_different_new_score(self):
        first = self.play(self.alice)
        self.assertEqual(first.max_score, Decimal("2.000"))

        version = self.new_version()
        target  = version.questions.get(stable_key = self.number.stable_key)
        update_question(target, {"scoring_config": {**target.scoring, "weight": 3}},
                        actor = self.admin)
        publish_version(version, actor = self.admin)

        latest = QuestionnaireResult.objects.filter(user = self.alice).order_by("-computed_at").first()
        self.assertEqual(latest.max_score, Decimal("4.000"))
        first.refresh_from_db()
        self.assertEqual(first.max_score, Decimal("2.000"))

    def test_a_new_question_leaves_the_attempt_pending(self):
        self.play(self.alice)

        version = self.new_version()
        create_question(version, {"type": c.TYPE_YES_NO, "text": "Avez-vous aime ?"},
                        actor = self.admin)
        publish_version(version, actor = self.admin)

        successor = self.attempt_on(self.alice, version)
        self.assertEqual(successor.status, c.ATTEMPT_IN_PROGRESS)
        self.assertEqual(successor.answered_count, 2)
        self.assertEqual(successor.visible_count, 3)
        self.assertEqual(QuestionnaireResult.objects.filter(user = self.alice).count(), 1)

    def test_the_participant_finds_their_answers_and_completes_the_new_question(self):
        self.play(self.alice)
        version = self.new_version()
        added = create_question(version, {"type": c.TYPE_YES_NO, "text": "Avez-vous aime ?"},
                                actor = self.admin)
        publish_version(version, actor = self.admin)
        self.q.refresh_from_db()

        from profils.questionnaires.services import current_attempt

        resumed = current_attempt(self.q, self.alice)
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.version_id, version.id)
        self.assertEqual(resumed.answers.count(), 2)

        save_answer(resumed, added.id, {"option_ids": [added.options.get(value = "yes").id]})
        result = finish_attempt(resumed)

        self.assertEqual(QuestionnaireResult.objects.filter(user = self.alice).count(), 2)
        self.assertEqual(result.version_id, version.id)

    def test_a_new_optional_question_still_allows_immediate_rescoring(self):
        self.play(self.alice)
        version = self.new_version()
        create_question(version, {"type": c.TYPE_YES_NO, "text": "Remarque ?",
                                  "required": False}, actor = self.admin)
        publish_version(version, actor = self.admin)

        self.assertEqual(self.attempt_on(self.alice, version).status, c.ATTEMPT_COMPLETED)

    def test_an_answer_whose_question_disappeared_is_dropped(self):
        self.play(self.alice)
        version = self.new_version()
        delete_question(version.questions.get(stable_key = self.number.stable_key),
                        actor = self.admin)
        publish_version(version, actor = self.admin)

        successor = self.attempt_on(self.alice, version)
        self.assertEqual(successor.answers.count(), 1)
        self.assertEqual(version.carry_over_report["dropped_answers"], 1)

    def test_an_answer_outside_the_new_bounds_is_dropped(self):
        self.play(self.alice, value = 4)
        version = self.new_version()
        target  = version.questions.get(stable_key = self.number.stable_key)
        update_question(target, {"config": {"min": 10, "max": 20}}, actor = self.admin)
        publish_version(version, actor = self.admin)

        successor = self.attempt_on(self.alice, version)
        self.assertEqual(successor.answers.count(), 1)
        self.assertEqual(version.carry_over_report["dropped_answers"], 1)

    def test_every_participant_is_carried_over(self):
        self.play(self.alice, option = "Java")
        self.play(self.bob, option = "COBOL")

        version = self.new_version()
        publish_version(version, actor = self.admin)

        self.assertEqual(version.carry_over_report["participants"], 2)
        self.assertEqual(version.carry_over_report["rescored"], 2)
        for user, percent in ((self.alice, "100.00"), (self.bob, "50.00")):
            latest = QuestionnaireResult.objects.filter(user = user).order_by("-computed_at").first()
            self.assertEqual(str(latest.percentage), percent, user.username)

class InProgressAttemptTests(CarryOverTestCase):

    def test_an_open_attempt_moves_to_the_new_version_in_place(self):
        attempt = self.play(self.alice, value = None, finish = False)
        original_id = attempt.pk

        version = self.new_version()
        publish_version(version, actor = self.admin)

        attempt.refresh_from_db()
        self.assertEqual(attempt.pk, original_id)
        self.assertEqual(attempt.version_id, version.id)
        self.assertEqual(attempt.status, c.ATTEMPT_IN_PROGRESS)
        self.assertEqual(attempt.answers.count(), 1)
        self.assertIsNone(attempt.carried_from_id)

    def test_the_moved_attempt_keeps_answering_on_the_new_version(self):
        attempt = self.play(self.alice, value = None, finish = False)
        version = self.new_version()
        publish_version(version, actor = self.admin)
        attempt.refresh_from_db()

        clone = version.questions.get(stable_key = self.number.stable_key)
        save_answer(attempt, clone.id, 4)
        result = finish_attempt(attempt)

        self.assertEqual(result.version_id, version.id)
        self.assertEqual(str(result.percentage), "100.00")

    def test_answers_point_at_the_new_version_questions(self):
        attempt = self.play(self.alice, value = None, finish = False)
        version = self.new_version()
        publish_version(version, actor = self.admin)

        for answer in attempt.answers.all():
            self.assertEqual(answer.question.version_id, version.id)

    def test_no_second_open_attempt_is_ever_created(self):
        self.play(self.alice)
        start_attempt(self.q, self.bob)

        version = self.new_version()
        publish_version(version, actor = self.admin)

        for user in (self.alice, self.bob):
            self.assertLessEqual(
                QuestionnaireAttempt.objects.filter(
                    user = user, status = c.ATTEMPT_IN_PROGRESS).count(), 1, user.username)

class ArchivedVersionTests(CarryOverTestCase):
    """Une version archivee par une publication ne doit pas pieger les participants."""

    def test_an_open_attempt_survives_the_archiving_of_its_version(self):
        attempt = self.play(self.alice, value = None, finish = False)

        version = self.new_version()
        publish_version(version, actor = self.admin, carry_over = False)

        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, c.STATUS_ARCHIVED)
        self.assertTrue(self.v1.allows_continuation)

        attempt.refresh_from_db()
        save_answer(attempt, self.number.id, 4)
        self.assertIsNotNone(finish_attempt(attempt))

    def test_a_disabled_version_does_block_the_attempt(self):
        attempt = self.play(self.alice, value = None, finish = False)
        self.v1.status = c.STATUS_DISABLED
        self.v1.save(update_fields = ["status"])

        attempt.refresh_from_db()
        with self.assertRaises(AttemptError) as ctx:
            save_answer(attempt, self.number.id, 4)
        self.assertEqual(ctx.exception.code, "version_closed")

class CarryOverSettingsTests(CarryOverTestCase):

    def test_the_setting_can_switch_the_behaviour_off(self):
        self.q.carry_over_answers = False
        self.q.save(update_fields = ["carry_over_answers"])
        self.play(self.alice)

        version = self.new_version()
        publish_version(version, actor = self.admin)

        self.assertIsNone(version.carry_over_report)
        self.assertIsNone(self.attempt_on(self.alice, version))

    def test_publish_can_override_the_setting(self):
        self.play(self.alice)
        version = self.new_version()
        publish_version(version, actor = self.admin, carry_over = False)
        self.assertIsNone(self.attempt_on(self.alice, version))

    def test_a_carried_attempt_does_not_consume_the_quota(self):
        self.q.max_attempts = 1
        self.q.save(update_fields = ["max_attempts"])
        self.play(self.alice)

        version = self.new_version()
        create_question(version, {"type": c.TYPE_YES_NO, "text": "Nouvelle ?"}, actor = self.admin)
        publish_version(version, actor = self.admin)

        successor = self.attempt_on(self.alice, version)
        self.assertEqual(successor.status, c.ATTEMPT_IN_PROGRESS)

        added = version.questions.get(text = "Nouvelle ?")
        save_answer(successor, added.id, {"option_ids": [added.options.first().id]})
        self.assertIsNotNone(finish_attempt(successor))

    def test_test_attempts_are_never_carried_over(self):
        from profils.questionnaires.versioning import set_version_test

        self.play(self.alice)
        version = self.new_version()
        set_version_test(version, actor = self.admin)
        self.q.refresh_from_db()

        test_attempt = start_attempt(self.q, self.admin, test = True)
        self.assertTrue(test_attempt.is_test)

        third = editable_version(self.q, actor = self.admin)
        publish_version(third, actor = self.admin)

        self.assertFalse(
            QuestionnaireAttempt.objects.filter(version = third, is_test = True).exists())

    def test_publishing_twice_does_not_duplicate_the_successor(self):
        self.play(self.alice)
        version = self.new_version()
        publish_version(version, actor = self.admin)
        first = QuestionnaireAttempt.objects.filter(user = self.alice, version = version).count()

        carry_over(self.q, version, actor = self.admin)
        self.assertEqual(
            QuestionnaireAttempt.objects.filter(user = self.alice, version = version).count(), first)

class PreviewTests(CarryOverTestCase):

    def test_the_preview_writes_nothing(self):
        self.play(self.alice)
        version = self.new_version()

        before = (QuestionnaireAttempt.objects.count(), UserAnswer.objects.count(),
                  QuestionnaireResult.objects.count())
        preview(self.q, version)
        self.assertEqual((QuestionnaireAttempt.objects.count(), UserAnswer.objects.count(),
                          QuestionnaireResult.objects.count()), before)

    def test_the_preview_matches_what_happens(self):
        self.play(self.alice)
        self.play(self.bob, option = "COBOL")
        version = self.new_version()
        create_question(version, {"type": c.TYPE_YES_NO, "text": "Nouvelle ?"}, actor = self.admin)

        estimate = preview(self.q, version)
        self.assertEqual(estimate["participants"], 2)
        self.assertEqual(estimate["pending"], 2)
        self.assertEqual(estimate["new_questions"], ["Nouvelle ?"])

        publish_version(version, actor = self.admin)
        report = version.carry_over_report
        self.assertEqual(report["participants"], estimate["participants"])
        self.assertEqual(report["pending"], estimate["pending"])

    def test_the_preview_is_empty_without_participants(self):
        version = self.new_version()
        self.assertEqual(preview(self.q, version)["participants"], 0)

class CarryOverApiTests(CarryOverTestCase):

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.admin)

    def test_the_impact_endpoint_describes_the_publication(self):
        self.play(self.alice)
        version = self.new_version()
        create_question(version, {"type": c.TYPE_YES_NO, "text": "Nouvelle ?"}, actor = self.admin)

        response = self.client.get(
            f"/api/questionnaires/{self.q.id}/versions/{version.version_number}/impact/")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["carry_over_enabled"])
        self.assertEqual(payload["impact"]["participants"], 1)
        self.assertEqual(payload["impact"]["new_questions"], ["Nouvelle ?"])

    def test_publishing_returns_the_carry_over_report(self):
        import json

        self.play(self.alice)
        version = self.new_version()

        response = self.client.post(
            f"/api/questionnaires/{self.q.id}/versions/{version.version_number}/publish/",
            data = json.dumps({}), content_type = "application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["carry_over"]["participants"], 1)

    def test_publishing_can_refuse_the_carry_over(self):
        import json

        self.play(self.alice)
        version = self.new_version()

        response = self.client.post(
            f"/api/questionnaires/{self.q.id}/versions/{version.version_number}/publish/",
            data = json.dumps({"carry_over": False}), content_type = "application/json")

        self.assertIsNone(response.json()["carry_over"])
        self.assertIsNone(self.attempt_on(self.alice, version))
