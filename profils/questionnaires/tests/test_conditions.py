##tests/test_conditions.py

from django.test import TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.conditions import ConditionError, compute_visible, validate_condition
from profils.questionnaires.editing    import create_question
from profils.questionnaires.services   import (
    AttemptError, finish_attempt, save_answer, start_attempt, visible_questions,
)

from .factories import draft_of, make_admin, make_questionnaire, make_user, publish


class ConditionValidationTests(TestCase):

    def test_unknown_question_is_refused(self):
        with self.assertRaises(ConditionError):
            validate_condition({"question": "inconnue", "operator": "EQUALS", "value": 1}, {"abc"})

    def test_unknown_operator_is_refused(self):
        with self.assertRaises(ConditionError):
            validate_condition({"question": "abc", "operator": "MAYBE", "value": 1}, {"abc"})

    def test_operator_requiring_a_value(self):
        with self.assertRaises(ConditionError):
            validate_condition({"question": "abc", "operator": "EQUALS"}, {"abc"})

    def test_answered_operator_needs_no_value(self):
        node = validate_condition({"question": "abc", "operator": "ANSWERED"}, {"abc"})
        self.assertNotIn("value", node)

    def test_nested_groups_are_accepted(self):
        node = validate_condition({
            "op": "AND",
            "conditions": [
                {"question": "abc", "operator": "ANSWERED"},
                {"op": "OR", "conditions": [
                    {"question": "def", "operator": "GT", "value": 3},
                    {"question": "def", "operator": "LT", "value": 1},
                ]},
            ],
        }, {"abc", "def"})
        self.assertEqual(node["op"], "AND")
        self.assertEqual(node["conditions"][1]["op"], "OR")

    def test_empty_group_is_refused(self):
        with self.assertRaises(ConditionError):
            validate_condition({"op": "AND", "conditions": []}, set())


class ConditionalDisplayTests(TestCase):
    """Q1 : avez-vous une voiture ? oui -> Q2, non -> Q3"""

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.version = draft_of(self.q)

        self.q1 = create_question(self.version, {
            "type": c.TYPE_YES_NO, "text": "Avez-vous une voiture ?",
        }, actor = self.admin)
        self.yes = self.q1.options.get(value = "yes")
        self.no  = self.q1.options.get(value = "no")

        self.q2 = create_question(self.version, {
            "type": c.TYPE_SINGLE_CHOICE, "text": "Quel est votre modele ?",
            "required": False,
            "options": [{"text": "Citroen"}, {"text": "Renault"}],
            "condition": {"question": self.q1.stable_key, "operator": "EQUALS",
                          "value": self.yes.stable_key},
        }, actor = self.admin)

        self.q3 = create_question(self.version, {
            "type": c.TYPE_SINGLE_CHOICE, "text": "Pourquoi n'avez-vous pas de voiture ?",
            "required": False,
            "options": [{"text": "Ecologie"}, {"text": "Budget"}],
            "condition": {"question": self.q1.stable_key, "operator": "EQUALS",
                          "value": self.no.stable_key},
        }, actor = self.admin)

        publish(self.q, self.admin)
        self.q.refresh_from_db()

    def visible_texts(self, attempt):
        return [q.text for q in visible_questions(attempt)]

    def test_conditional_questions_are_hidden_at_first(self):
        attempt = start_attempt(self.q, self.user)
        self.assertEqual(self.visible_texts(attempt), ["Avez-vous une voiture ?"])

    def test_answering_yes_reveals_the_yes_branch(self):
        attempt = start_attempt(self.q, self.user)
        save_answer(attempt, self.q1.id, {"option_ids": [self.yes.id]})

        self.assertEqual(self.visible_texts(attempt),
                         ["Avez-vous une voiture ?", "Quel est votre modele ?"])

    def test_answering_no_reveals_the_no_branch(self):
        attempt = start_attempt(self.q, self.user)
        save_answer(attempt, self.q1.id, {"option_ids": [self.no.id]})

        self.assertEqual(self.visible_texts(attempt),
                         ["Avez-vous une voiture ?", "Pourquoi n'avez-vous pas de voiture ?"])

    def test_answering_a_hidden_question_is_refused(self):
        attempt = start_attempt(self.q, self.user)
        with self.assertRaises(AttemptError) as ctx:
            save_answer(attempt, self.q2.id, {"option_ids": [self.q2.options.first().id]})
        self.assertEqual(ctx.exception.code, "question_not_visible")

    def test_a_question_that_becomes_hidden_is_excluded_from_scoring(self):
        attempt = start_attempt(self.q, self.user)
        save_answer(attempt, self.q1.id, {"option_ids": [self.yes.id]})
        save_answer(attempt, self.q2.id, {"option_ids": [self.q2.options.first().id]})
        self.assertEqual(attempt.answers.count(), 2)

        # l'utilisateur change d'avis : Q2 disparait, sa reponse reste stockee
        save_answer(attempt, self.q1.id, {"option_ids": [self.no.id]})
        attempt.refresh_from_db()

        self.assertEqual(self.visible_texts(attempt),
                         ["Avez-vous une voiture ?", "Pourquoi n'avez-vous pas de voiture ?"])
        self.assertEqual(attempt.answers.count(), 2)

        result = finish_attempt(attempt, force = True)
        hidden = next(e for e in result.details["questions"] if e["question_id"] == self.q2.id)
        self.assertEqual(hidden["skipped"], "hidden_by_condition")
        self.assertIsNotNone(hidden["answer_id"])

    def test_progress_follows_visibility(self):
        attempt = start_attempt(self.q, self.user)
        self.assertEqual(attempt.visible_count, 1)

        save_answer(attempt, self.q1.id, {"option_ids": [self.yes.id]})
        attempt.refresh_from_db()
        self.assertEqual(attempt.visible_count, 2)
        self.assertEqual(attempt.answered_count, 1)

    def test_a_hidden_required_question_does_not_block_the_end(self):
        attempt = start_attempt(self.q, self.user)
        save_answer(attempt, self.q1.id, {"option_ids": [self.yes.id]})
        save_answer(attempt, self.q2.id, {"option_ids": [self.q2.options.first().id]})
        result = finish_attempt(attempt)
        self.assertIsNotNone(result)


class ConditionOperatorTests(TestCase):

    def setUp(self):
        self.admin   = make_admin()
        self.q       = make_questionnaire(self.admin)
        self.version = draft_of(self.q)
        self.age = create_question(self.version, {
            "type": c.TYPE_INTEGER, "text": "Age ?", "config": {"min": 0, "max": 130},
        }, actor = self.admin)

    def dependent(self, condition):
        return create_question(self.version, {
            "type": c.TYPE_YES_NO, "text": "Question dependante",
            "required": False, "condition": condition,
        }, actor = self.admin)

    def visible_with(self, value):
        questions = list(self.version.questions.prefetch_related("options"))
        answers = {} if value is None else {self.age.stable_key: {"number": str(value), "unit": None}}
        return [q.text for q in compute_visible(questions, answers)]

    def test_greater_than(self):
        self.dependent({"question": self.age.stable_key, "operator": "GT", "value": 18})
        self.assertIn("Question dependante", self.visible_with(19))
        self.assertNotIn("Question dependante", self.visible_with(18))

    def test_greater_or_equal(self):
        self.dependent({"question": self.age.stable_key, "operator": "GTE", "value": 18})
        self.assertIn("Question dependante", self.visible_with(18))
        self.assertNotIn("Question dependante", self.visible_with(17))

    def test_less_than_and_less_or_equal(self):
        self.dependent({"question": self.age.stable_key, "operator": "LT", "value": 10})
        self.assertIn("Question dependante", self.visible_with(9))
        self.assertNotIn("Question dependante", self.visible_with(10))

    def test_not_equals(self):
        self.dependent({"question": self.age.stable_key, "operator": "NOT_EQUALS", "value": 30})
        self.assertIn("Question dependante", self.visible_with(31))
        self.assertNotIn("Question dependante", self.visible_with(30))

    def test_answered_and_not_answered(self):
        self.dependent({"question": self.age.stable_key, "operator": "ANSWERED"})
        self.assertIn("Question dependante", self.visible_with(42))
        self.assertNotIn("Question dependante", self.visible_with(None))

    def test_and_or_combination(self):
        self.dependent({"op": "OR", "conditions": [
            {"question": self.age.stable_key, "operator": "LT", "value": 18},
            {"question": self.age.stable_key, "operator": "GT", "value": 65},
        ]})
        self.assertIn("Question dependante", self.visible_with(10))
        self.assertIn("Question dependante", self.visible_with(70))
        self.assertNotIn("Question dependante", self.visible_with(40))

    def test_and_requires_every_branch(self):
        self.dependent({"op": "AND", "conditions": [
            {"question": self.age.stable_key, "operator": "GTE", "value": 18},
            {"question": self.age.stable_key, "operator": "LTE", "value": 65},
        ]})
        self.assertIn("Question dependante", self.visible_with(40))
        self.assertNotIn("Question dependante", self.visible_with(70))


class MultipleChoiceConditionTests(TestCase):

    def test_contains_on_a_multiple_choice_question(self):
        admin   = make_admin()
        q       = make_questionnaire(admin)
        version = draft_of(q)

        source = create_question(version, {
            "type": c.TYPE_MULTIPLE_CHOICE, "text": "Langages connus ?",
            "options": [{"text": "Java"}, {"text": "Rust"}, {"text": "COBOL"}],
        }, actor = admin)
        rust = source.options.get(text = "Rust")

        create_question(version, {
            "type": c.TYPE_YES_NO, "text": "Depuis quand Rust ?", "required": False,
            "condition": {"question": source.stable_key, "operator": "CONTAINS",
                          "value": rust.stable_key},
        }, actor = admin)

        questions = list(version.questions.prefetch_related("options"))
        java = source.options.get(text = "Java")

        with_rust = compute_visible(questions, {source.stable_key: {"option_ids": [java.id, rust.id]}})
        self.assertEqual(len(with_rust), 2)

        without = compute_visible(questions, {source.stable_key: {"option_ids": [java.id]}})
        self.assertEqual(len(without), 1)


class CascadeVisibilityTests(TestCase):

    def test_a_branch_hidden_upstream_hides_its_children(self):
        admin   = make_admin()
        q       = make_questionnaire(admin)
        version = draft_of(q)

        root = create_question(version, {"type": c.TYPE_YES_NO, "text": "Racine"}, actor = admin)
        yes  = root.options.get(value = "yes")

        child = create_question(version, {
            "type": c.TYPE_YES_NO, "text": "Enfant", "required": False,
            "condition": {"question": root.stable_key, "operator": "EQUALS", "value": yes.stable_key},
        }, actor = admin)
        child_yes = child.options.get(value = "yes")

        create_question(version, {
            "type": c.TYPE_YES_NO, "text": "Petit-enfant", "required": False,
            "condition": {"question": child.stable_key, "operator": "EQUALS",
                          "value": child_yes.stable_key},
        }, actor = admin)

        questions = list(version.questions.prefetch_related("options"))

        # l'enfant a une reponse, mais la racine dit "non" : tout le sous-arbre disparait
        answers = {
            root.stable_key:  {"option_ids": [root.options.get(value = "no").id]},
            child.stable_key: {"option_ids": [child_yes.id]},
        }
        self.assertEqual([q.text for q in compute_visible(questions, answers)], ["Racine"])
