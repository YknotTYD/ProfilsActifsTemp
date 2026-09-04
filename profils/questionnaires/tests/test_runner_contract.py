"""Ce que l'interface de passage recoit du serveur.

Ces tests protegent un invariant simple : un participant doit pouvoir repondre
a n'importe quelle question, sans quoi il ne peut jamais terminer sa tentative
ni obtenir de resultat.
"""

import json

from django.test import Client, TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.editing import create_question
from profils.questionnaires.question_types import all_types
from profils.questionnaires.serializers import runner_question, runner_state
from profils.questionnaires.services import finish_attempt, save_answer, start_attempt

from .factories import (
    add_single_choice, draft_of, make_admin, make_questionnaire, make_user, publish,
)

KNOWN_WIDGETS = {"choice", "dropdown", "vocabulary", "number", "temporal", "date_range", "address"}

class WidgetContractTests(TestCase):

    def test_every_type_declares_a_widget(self):
        for handler in all_types():
            self.assertTrue(handler.widget, f"{handler.id} ne declare aucun widget")

    def test_every_widget_is_one_the_interface_knows(self):
        for handler in all_types():
            self.assertIn(handler.widget, KNOWN_WIDGETS, handler.id)

    def test_registering_a_type_without_a_widget_is_refused(self):
        from profils.questionnaires.question_types import QuestionType, register

        with self.assertRaises(RuntimeError) as ctx:
            @register
            class Broken(QuestionType):
                id     = "type_sans_widget"
                family = c.FAMILY_NUMERIC
                label  = "Casse"
        self.assertIn("widget", str(ctx.exception))

    def test_the_widget_reaches_the_client(self):
        admin   = make_admin()
        version = draft_of(make_questionnaire(admin))
        question = create_question(version, {
            "type": c.TYPE_YEAR, "text": "Quelle annee ?"}, actor = admin)

        payload = runner_question(question)
        self.assertEqual(payload["widget"], "number")
        self.assertIn("widget", payload)

    def test_year_is_rendered_as_a_number_not_as_a_structured_value(self):
        """Regression : l'annee est de famille « structuree » mais se saisit
        comme un nombre. Le client ne doit pas deduire le champ de la famille."""
        admin   = make_admin()
        version = draft_of(make_questionnaire(admin))
        question = create_question(version, {
            "type": c.TYPE_YEAR, "text": "Annee ?"}, actor = admin)

        payload = runner_question(question)
        self.assertEqual(payload["family"], c.FAMILY_STRUCTURED)
        self.assertEqual(payload["widget"], "number")

class EveryTypeIsAnswerableTests(TestCase):
    """Un questionnaire contenant tous les types doit pouvoir etre termine."""

    ANSWERS = {
        c.TYPE_INTEGER: 20, c.TYPE_DECIMAL: "20.5", c.TYPE_PERCENTAGE: 50,
        c.TYPE_TEMPERATURE: 20, c.TYPE_DISTANCE: 20, c.TYPE_WEIGHT: 20,
        c.TYPE_HEIGHT: 170, c.TYPE_SPEED: 50, c.TYPE_DURATION: 30,
        c.TYPE_YEAR: 2020,
        c.TYPE_DATE: "2026-07-01", c.TYPE_TIME: "08:30:00",
        c.TYPE_DATETIME: "2026-07-01T08:30", c.TYPE_HOUR_MINUTE: "08:30",
        c.TYPE_DATE_RANGE: {"start": "2026-07-01", "end": "2026-07-15"},
        c.TYPE_COUNTRY: "FR", c.TYPE_CITY: "PARIS",
        c.TYPE_MONTH: 7, c.TYPE_WEEKDAY: 2,
        c.TYPE_ADDRESS: {"country": "FR", "postal_code": "75011"},
    }

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("participant")
        self.q     = make_questionnaire(self.admin, title = "Tous les types")
        self.version = draft_of(self.q)

        for handler in all_types():
            payload = {"type": handler.id, "text": f"Question {handler.id}", "required": True}
            if handler.uses_options and not getattr(handler, "fixed_options", ()) \
                    and handler.id != c.TYPE_SCALE:
                payload["options"] = [{"text": "A", "is_correct": True}, {"text": "B"}]
            if handler.id == c.TYPE_SCALE:
                payload["config"] = {"min": 1, "max": 5, "step": 1}
            if handler.id == c.TYPE_CITY:
                payload["config"] = {"cities": [{"code": "PARIS", "name": "Paris"}]}
            if handler.id == c.TYPE_ADDRESS:
                payload["config"] = {"countries": ["FR"], "required_fields": ["country"]}
            create_question(self.version, payload, actor = self.admin)

        publish(self.q, self.admin)
        self.q.refresh_from_db()

    def test_a_participant_can_answer_every_question_and_finish(self):
        attempt = start_attempt(self.q, self.user)

        for question in self.version.questions.prefetch_related("options"):
            if question.handler.uses_options:
                value = {"option_ids": [question.options.first().id]}
            else:
                self.assertIn(question.type, self.ANSWERS,
                              f"aucune reponse de reference pour {question.type}")
                value = self.ANSWERS[question.type]
            save_answer(attempt, question.id, value)

        attempt.refresh_from_db()
        self.assertEqual(attempt.answered_count, attempt.visible_count)

        result = finish_attempt(attempt)
        self.assertIsNotNone(result)
        self.assertEqual(result.attempt_id, attempt.id)

    def test_the_runner_payload_offers_a_control_for_every_question(self):
        attempt = start_attempt(self.q, self.user)
        state   = runner_state(attempt)

        self.assertEqual(len(state["questions"]), self.version.questions.count())
        for question in state["questions"]:
            self.assertIn(question["widget"], KNOWN_WIDGETS, question["type"])
            if question["widget"] in ("choice", "dropdown"):
                self.assertTrue(question["options"], question["type"])
            if question["widget"] == "vocabulary":
                self.assertTrue(question["vocabulary"], question["type"])

class FinishFeedbackTests(TestCase):
    """Terminer doit dire precisement ce qui bloque."""

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("participant")
        self.q     = make_questionnaire(self.admin)
        self.version = draft_of(self.q)
        self.first  = add_single_choice(self.version, self.admin, text = "Q1")
        self.second = add_single_choice(self.version, self.admin, text = "Q2")
        publish(self.q, self.admin)
        self.q.refresh_from_db()

        self.client = Client()
        self.client.force_login(self.user)

    def post(self, url, payload = None):
        return self.client.post(url, data = json.dumps(payload or {}),
                                content_type = "application/json")

    def test_the_error_names_the_missing_questions(self):
        self.post(f"/api/questionnaires/{self.q.id}/start/")
        response = self.post(f"/api/questionnaires/{self.q.id}/finish/")

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["code"], "missing_required")
        self.assertEqual(sorted(payload["missing"]), sorted([self.first.id, self.second.id]))
        self.assertIn("2 question", payload["error"])

    def test_the_list_shrinks_as_the_participant_answers(self):
        self.post(f"/api/questionnaires/{self.q.id}/start/")
        self.post(f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.first.id,
            "value": {"option_ids": [self.first.options.first().id]},
        })
        payload = self.post(f"/api/questionnaires/{self.q.id}/finish/").json()

        self.assertEqual(payload["missing"], [self.second.id])
        self.assertIn("1 question", payload["error"])

    def test_a_complete_attempt_finishes_and_returns_the_result(self):
        self.post(f"/api/questionnaires/{self.q.id}/start/")
        for question in (self.first, self.second):
            self.post(f"/api/questionnaires/{self.q.id}/answers/", {
                "question_id": question.id,
                "value": {"option_ids": [question.options.get(text = "Java").id]},
            })
        response = self.post(f"/api/questionnaires/{self.q.id}/finish/")

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["percentage"], "100.00")

    def test_a_plain_user_can_read_their_result_afterwards(self):
        self.post(f"/api/questionnaires/{self.q.id}/start/")
        for question in (self.first, self.second):
            self.post(f"/api/questionnaires/{self.q.id}/answers/", {
                "question_id": question.id,
                "value": {"option_ids": [question.options.get(text = "Java").id]},
            })
        self.post(f"/api/questionnaires/{self.q.id}/finish/")

        history = self.client.get(f"/api/questionnaires/{self.q.id}/results/me/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["results"]), 1)

        page = self.client.get(f"/questionnaires/{self.q.id}/results/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "100.00")

    def test_the_catalog_offers_the_results_link_after_an_attempt(self):
        self.post(f"/api/questionnaires/{self.q.id}/start/")
        page = self.client.get("/questionnaires/")
        self.assertContains(page, f"/questionnaires/{self.q.id}/results/")
