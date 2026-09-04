
from django.core.exceptions import ValidationError
from django.test import TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.editing    import update_question
from profils.questionnaires.models     import QuestionnaireResult
from profils.questionnaires.services   import finish_attempt, save_answer, start_attempt
from profils.questionnaires.versioning import (
    compare_versions, editable_version, invalidate_version, publish_version, restore_version,
)

from .factories import add_single_choice, draft_of, make_admin, make_questionnaire, make_user

class VersionLifecycleTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.q     = make_questionnaire(self.admin)
        self.draft = draft_of(self.q)

    def test_first_version_is_editable_draft(self):
        self.assertEqual(self.draft.version_number, 1)
        self.assertEqual(self.draft.status, c.STATUS_DRAFT)
        self.assertTrue(self.draft.is_editable)

    def test_publishing_freezes_the_version(self):
        add_single_choice(self.draft, self.admin)
        publish_version(self.draft, actor = self.admin)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, c.STATUS_PUBLISHED)
        self.assertFalse(self.draft.is_editable)

        with self.assertRaises(ValidationError):
            self.draft.assert_editable()

    def test_cannot_publish_empty_version(self):
        with self.assertRaises(ValidationError):
            publish_version(self.draft, actor = self.admin)

    def test_editing_a_published_questionnaire_creates_a_new_version(self):
        add_single_choice(self.draft, self.admin)
        publish_version(self.draft, actor = self.admin)

        second = editable_version(self.q, actor = self.admin)
        self.assertEqual(second.version_number, 2)
        self.assertTrue(second.is_editable)
        self.assertEqual(second.questions.count(), 1)

    def test_new_version_keeps_stable_keys(self):
        question = add_single_choice(self.draft, self.admin)
        publish_version(self.draft, actor = self.admin)

        second = editable_version(self.q, actor = self.admin)
        clone  = second.questions.first()

        self.assertNotEqual(question.id, clone.id)
        self.assertEqual(question.stable_key, clone.stable_key)
        self.assertEqual(
            sorted(o.stable_key for o in question.options.all()),
            sorted(o.stable_key for o in clone.options.all()),
        )

    def test_publishing_a_new_version_archives_the_previous_one(self):
        add_single_choice(self.draft, self.admin)
        publish_version(self.draft, actor = self.admin)

        second = editable_version(self.q, actor = self.admin)
        publish_version(second, actor = self.admin)

        self.draft.refresh_from_db()
        self.q.refresh_from_db()
        self.assertEqual(self.draft.status, c.STATUS_ARCHIVED)
        self.assertEqual(self.q.current_version_id, second.id)

    def test_restore_creates_a_new_version_and_leaves_the_old_one_intact(self):
        question = add_single_choice(self.draft, self.admin, text = "Version 1")
        publish_version(self.draft, actor = self.admin)

        second = editable_version(self.q, actor = self.admin)
        update_question(second.questions.first(), {"text": "Version 2"}, actor = self.admin)
        publish_version(second, actor = self.admin)

        third = restore_version(self.q, self.draft, actor = self.admin)

        self.assertEqual(third.version_number, 3)
        self.assertEqual(third.questions.first().text, "Version 1")
        question.refresh_from_db()
        self.assertEqual(question.text, "Version 1")

    def test_version_with_attempts_is_never_editable(self):
        add_single_choice(self.draft, self.admin)
        publish_version(self.draft, actor = self.admin)
        start_attempt(self.q, make_user("candidat"))

        self.draft.refresh_from_db()
        self.assertFalse(self.draft.is_editable)

class VersionComparisonTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.q     = make_questionnaire(self.admin)
        self.v1    = draft_of(self.q)
        add_single_choice(self.v1, self.admin, text = "Question inchangee")
        add_single_choice(self.v1, self.admin, text = "Question modifiee")
        self.removed = add_single_choice(self.v1, self.admin, text = "Question supprimee")
        publish_version(self.v1, actor = self.admin)

        self.v2 = editable_version(self.q, actor = self.admin)
        update_question(
            self.v2.questions.get(stable_key = self.v1.questions.all()[1].stable_key),
            {"text": "Question modifiee (v2)"}, actor = self.admin,
        )
        self.v2.questions.get(stable_key = self.removed.stable_key).delete()
        add_single_choice(self.v2, self.admin, text = "Question ajoutee")

    def test_diff_reports_added_removed_and_changed(self):
        diff = compare_versions(self.v1, self.v2)

        self.assertEqual(diff["summary"]["added"], 1)
        self.assertEqual(diff["summary"]["removed"], 1)
        self.assertEqual(diff["summary"]["changed"], 1)
        self.assertEqual(diff["questions"]["added"][0]["text"], "Question ajoutee")
        self.assertEqual(diff["questions"]["removed"][0]["text"], "Question supprimee")

        changed = diff["questions"]["changed"][0]
        self.assertEqual(changed["fields"]["text"]["from"], "Question modifiee")
        self.assertEqual(changed["fields"]["text"]["to"], "Question modifiee (v2)")

    def test_diff_reports_option_changes(self):
        question = self.v2.questions.first()
        option   = question.options.first()
        option.text = "Java 21"
        option.save()

        diff    = compare_versions(self.v1, self.v2)
        changed = next(q for q in diff["questions"]["changed"] if q["stable_key"] == question.stable_key)
        self.assertEqual(changed["options"]["changed"][0]["fields"]["text"]["to"], "Java 21")

    def test_diff_records_the_author_of_each_version(self):
        diff = compare_versions(self.v1, self.v2)
        self.assertEqual(diff["from"]["created_by"], self.admin.username)
        self.assertEqual(diff["to"]["created_by"], self.admin.username)

class HistoricalIntegrityTests(TestCase):
    """Une modification du questionnaire ne doit jamais toucher l'historique."""

    def test_results_are_immune_to_later_edits(self):
        admin = make_admin()
        user  = make_user("candidat")
        q     = make_questionnaire(admin)
        v1    = draft_of(q)
        question = add_single_choice(v1, admin)
        publish_version(v1, actor = admin)

        attempt = start_attempt(q, user)
        correct = question.options.get(text = "Java")
        save_answer(attempt, question.id, {"option_ids": [correct.id]})
        result = finish_attempt(attempt)

        self.assertTrue(result.passed)
        original = (str(result.score), str(result.percentage), result.version_id)

        v2 = editable_version(q, actor = admin)
        clone = v2.questions.first()
        update_question(clone, {
            "text": "Question entierement reecrite",
            "options": [{"text": "COBOL", "is_correct": True}, {"text": "Java", "is_correct": False}],
        }, actor = admin)
        publish_version(v2, actor = admin)

        result.refresh_from_db()
        self.assertEqual((str(result.score), str(result.percentage), result.version_id), original)
        self.assertEqual(result.version_id, v1.id)

        answer = result.attempt.answers.first()
        self.assertEqual(answer.snapshot["text"], "Langage prefere ?")
        self.assertTrue(answer.is_correct)

    def test_invalidated_version_keeps_past_results_readable(self):
        admin = make_admin()
        user  = make_user("candidat")
        q     = make_questionnaire(admin)
        v1    = draft_of(q)
        question = add_single_choice(v1, admin)
        publish_version(v1, actor = admin)

        attempt = start_attempt(q, user)
        save_answer(attempt, question.id, {"option_ids": [question.options.first().id]})
        result = finish_attempt(attempt)

        invalidate_version(v1, actor = admin, reason = "erreur de contenu")

        self.assertEqual(QuestionnaireResult.objects.filter(pk = result.pk).count(), 1)
        v1.refresh_from_db()
        self.assertEqual(v1.status, c.STATUS_INVALIDATED)
        self.assertFalse(v1.accepts_answers)
