##tests/test_scoring.py

from decimal import Decimal

from django.test import TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.editing  import create_question
from profils.questionnaires.scoring  import score_question
from profils.questionnaires.services import finish_attempt, save_answer, start_attempt

from .factories import (
    add_multiple_choice, add_single_choice, draft_of, make_admin, make_questionnaire,
    make_user, publish,
)


class ScoreQuestionTests(TestCase):

    def setUp(self):
        self.admin   = make_admin()
        self.q       = make_questionnaire(self.admin)
        self.version = draft_of(self.q)

    def score(self, question, raw):
        value    = question.handler.normalize_answer(question, raw)
        answered = question.handler.is_answered(value)
        return score_question(question, value, answered)

    def test_correct_answer_scores_one_by_default(self):
        question = add_single_choice(self.version, self.admin)
        java = question.options.get(text = "Java")
        entry = self.score(question, {"option_ids": [java.id]})

        self.assertEqual(Decimal(entry["score"]), Decimal("1"))
        self.assertTrue(entry["is_correct"])

    def test_wrong_answer_scores_zero_by_default(self):
        question = add_single_choice(self.version, self.admin)
        cobol = question.options.get(text = "COBOL")
        entry = self.score(question, {"option_ids": [cobol.id]})

        self.assertEqual(Decimal(entry["score"]), Decimal("0"))
        self.assertFalse(entry["is_correct"])

    def test_negative_score_on_wrong_answer(self):
        question = add_single_choice(self.version, self.admin,
                                     scoring_config = {"incorrect_score": -0.5})
        cobol = question.options.get(text = "COBOL")
        self.assertEqual(Decimal(self.score(question, {"option_ids": [cobol.id]})["score"]),
                         Decimal("-0.5"))

    def test_weight_multiplies_the_score(self):
        question = add_single_choice(self.version, self.admin, scoring_config = {"weight": 2})
        java = question.options.get(text = "Java")
        entry = self.score(question, {"option_ids": [java.id]})

        self.assertEqual(Decimal(entry["score"]), Decimal("2"))
        self.assertEqual(Decimal(entry["max_score"]), Decimal("2"))

    def test_partial_score_two_out_of_three(self):
        question = create_question(self.version, {
            "type": c.TYPE_MULTIPLE_CHOICE, "text": "Trois bonnes reponses",
            "options": [
                {"text": "A", "is_correct": True}, {"text": "B", "is_correct": True},
                {"text": "C", "is_correct": True}, {"text": "D"},
            ],
        }, actor = self.admin)
        options = {o.text: o.id for o in question.options.all()}
        entry = self.score(question, {"option_ids": [options["A"], options["B"]]})

        self.assertAlmostEqual(float(entry["score"]), 2 / 3, places = 3)
        self.assertFalse(entry["is_correct"])

    def test_all_or_nothing_mode(self):
        question = add_multiple_choice(self.version, self.admin, scoring_config = {
            "partial": True, "partial_mode": c.PARTIAL_ALL_OR_NOTHING})
        options = {o.text: o.id for o in question.options.all()}

        self.assertEqual(Decimal(self.score(question, {"option_ids": [options["Java"]]})["score"]),
                         Decimal("0"))
        self.assertEqual(
            Decimal(self.score(question, {"option_ids": [options["Java"], options["Rust"]]})["score"]),
            Decimal("1"))

    def test_threshold_mode(self):
        question = add_multiple_choice(self.version, self.admin, scoring_config = {
            "partial": True, "partial_mode": c.PARTIAL_THRESHOLD, "partial_threshold": 0.5})
        options = {o.text: o.id for o in question.options.all()}
        self.assertEqual(Decimal(self.score(question, {"option_ids": [options["Java"]]})["score"]),
                         Decimal("1"))

    def test_unanswered_question_uses_its_own_score(self):
        question = add_single_choice(self.version, self.admin,
                                     scoring_config = {"unanswered_score": -1})
        entry = score_question(question, None, False)
        self.assertEqual(Decimal(entry["score"]), Decimal("-1"))

    def test_ungraded_question_contributes_nothing(self):
        question = create_question(self.version, {
            "type": c.TYPE_SINGLE_CHOICE, "text": "Sondage",
            "options": [{"text": "A"}, {"text": "B"}],
        }, actor = self.admin)
        entry = self.score(question, {"option_ids": [question.options.first().id]})

        self.assertFalse(entry["graded"])
        self.assertEqual(Decimal(entry["max_score"]), Decimal("0"))


class ScoreAttemptTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.version = draft_of(self.q)

    def run_attempt(self, answers):
        publish(self.q, self.admin)
        self.q.refresh_from_db()
        attempt = start_attempt(self.q, self.user)
        for question_id, value in answers.items():
            save_answer(attempt, question_id, value)
        return finish_attempt(attempt)

    def test_percentage_and_pass_threshold(self):
        q1 = add_single_choice(self.version, self.admin, text = "Q1")
        q2 = add_single_choice(self.version, self.admin, text = "Q2")

        result = self.run_attempt({
            q1.id: {"option_ids": [q1.options.get(text = "Java").id]},
            q2.id: {"option_ids": [q2.options.get(text = "COBOL").id]},
        })

        self.assertEqual(result.score, Decimal("1.000"))
        self.assertEqual(result.max_score, Decimal("2.000"))
        self.assertEqual(result.percentage, Decimal("50.00"))
        self.assertFalse(result.passed)

    def test_custom_pass_threshold(self):
        self.version.scoring_config = {"pass_threshold_percent": 50}
        self.version.save()

        q1 = add_single_choice(self.version, self.admin, text = "Q1")
        q2 = add_single_choice(self.version, self.admin, text = "Q2")
        result = self.run_attempt({
            q1.id: {"option_ids": [q1.options.get(text = "Java").id]},
            q2.id: {"option_ids": [q2.options.get(text = "COBOL").id]},
        })
        self.assertTrue(result.passed)

    def test_success_levels(self):
        self.version.scoring_config = {
            "pass_threshold_percent": 50,
            "levels": [
                {"name": "Bronze", "min_percent": 50},
                {"name": "Argent", "min_percent": 75},
                {"name": "Or",     "min_percent": 100},
            ],
        }
        self.version.save()

        questions = [add_single_choice(self.version, self.admin, text = f"Q{i}") for i in range(4)]
        answers = {
            q.id: {"option_ids": [q.options.get(text = "Java" if i < 3 else "COBOL").id]}
            for i, q in enumerate(questions)
        }
        result = self.run_attempt(answers)

        self.assertEqual(result.percentage, Decimal("75.00"))
        self.assertEqual(result.level, "Argent")

    def test_negative_total_is_floored_at_zero(self):
        self.version.scoring_config = {"floor_negative": True, "pass_threshold_percent": 60}
        self.version.save()

        q1 = add_single_choice(self.version, self.admin, text = "Q1",
                               scoring_config = {"incorrect_score": -1})
        result = self.run_attempt({q1.id: {"option_ids": [q1.options.get(text = "COBOL").id]}})

        self.assertEqual(result.score, Decimal("0.000"))
        self.assertEqual(result.percentage, Decimal("0.00"))

    def test_negative_total_can_be_kept(self):
        self.version.scoring_config = {"floor_negative": False, "pass_threshold_percent": 60}
        self.version.save()

        q1 = add_single_choice(self.version, self.admin, text = "Q1",
                               scoring_config = {"incorrect_score": -1})
        result = self.run_attempt({q1.id: {"option_ids": [q1.options.get(text = "COBOL").id]}})
        self.assertEqual(result.score, Decimal("-1.000"))

    def test_result_details_are_historised_per_question(self):
        q1 = add_single_choice(self.version, self.admin, text = "Q1")
        result = self.run_attempt({q1.id: {"option_ids": [q1.options.get(text = "Java").id]}})

        entries = result.details["questions"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["question_id"], q1.id)
        self.assertTrue(entries[0]["is_correct"])
        self.assertEqual(Decimal(result.details["threshold"]), Decimal("60"))

    def test_result_is_never_overwritten_by_a_new_attempt(self):
        self.q.allow_retry_after_pass = True
        q1 = add_single_choice(self.version, self.admin, text = "Q1")
        first = self.run_attempt({q1.id: {"option_ids": [q1.options.get(text = "COBOL").id]}})

        self.q.refresh_from_db()
        self.q.allow_retry_after_pass = True
        self.q.save()

        attempt = start_attempt(self.q, self.user)
        save_answer(attempt, q1.id, {"option_ids": [q1.options.get(text = "Java").id]})
        second = finish_attempt(attempt)

        first.refresh_from_db()
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.percentage, Decimal("0.00"))
        self.assertEqual(second.percentage, Decimal("100.00"))
        self.assertEqual(self.user.questionnaire_results.count(), 2)
