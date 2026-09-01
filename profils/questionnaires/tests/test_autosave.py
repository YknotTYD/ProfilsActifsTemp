##tests/test_autosave.py
"""Sauvegarde automatique, idempotence et concurrence (sections 11 a 13, 33)."""

import json

from django.test import Client, TestCase

from profils.questionnaires.models   import UserAnswer, UserAnswerSelection
from profils.questionnaires.services import (
    AttemptError, StaleWrite, clear_answer, save_answer, start_attempt,
)

from .factories import (
    add_single_choice, add_temperature, draft_of, make_admin,
    make_questionnaire, make_user, publish,
)


class AutosaveTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.version  = draft_of(self.q)
        self.question = add_single_choice(self.version, self.admin)
        self.temp     = add_temperature(self.version, self.admin, required = False)
        publish(self.q, self.admin)
        self.q.refresh_from_db()

        self.attempt = start_attempt(self.q, self.user)
        self.java  = self.question.options.get(text = "Java")
        self.cobol = self.question.options.get(text = "COBOL")

    def test_an_answer_is_persisted_immediately(self):
        state = save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]})

        self.assertTrue(state["saved"])
        self.assertEqual(UserAnswer.objects.filter(attempt = self.attempt).count(), 1)
        self.assertEqual(state["progress"]["answered"], 1)

    def test_the_attempt_state_is_returned_to_the_client(self):
        state = save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]})

        self.assertIn("attempt_revision", state)
        self.assertIn("server_time", state)
        self.assertEqual(state["answer"]["question_id"], self.question.id)
        self.assertEqual(state["answer"]["revision"], 1)

    def test_selections_are_stored_in_their_own_table(self):
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]})
        self.assertEqual(UserAnswerSelection.objects.filter(option = self.java).count(), 1)

        save_answer(self.attempt, self.question.id, {"option_ids": [self.cobol.id]})
        self.assertEqual(UserAnswerSelection.objects.filter(option = self.java).count(), 0)
        self.assertEqual(UserAnswerSelection.objects.filter(option = self.cobol).count(), 1)

    def test_a_snapshot_is_attached_to_every_answer(self):
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]})
        snapshot = UserAnswer.objects.get(attempt = self.attempt).snapshot

        self.assertEqual(snapshot["text"], "Langage prefere ?")
        self.assertEqual(len(snapshot["options"]), 3)
        self.assertEqual(snapshot["version"]["version_number"], 1)

    def test_the_snapshot_never_carries_the_expected_answers(self):
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]})
        snapshot = json.dumps(UserAnswer.objects.get(attempt = self.attempt).snapshot)

        self.assertNotIn("is_correct", snapshot)
        self.assertNotIn("expected_config", snapshot)

    def test_saving_a_value_type_answer(self):
        save_answer(self.attempt, self.temp.id, {"number": "20", "unit": "C"})
        answer = UserAnswer.objects.get(attempt = self.attempt, question = self.temp)
        self.assertEqual(answer.value, {"number": "20", "unit": "C"})

    def test_an_invalid_answer_is_refused_without_being_stored(self):
        with self.assertRaises(AttemptError) as ctx:
            save_answer(self.attempt, self.temp.id, {"number": "pas-un-nombre"})
        self.assertEqual(ctx.exception.code, "invalid_answer")
        self.assertEqual(UserAnswer.objects.filter(attempt = self.attempt).count(), 0)

    def test_an_answer_can_be_cleared(self):
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]})
        clear_answer(self.attempt, self.question.id)

        answer = UserAnswer.objects.get(attempt = self.attempt)
        self.assertIsNone(answer.value)
        self.assertEqual(answer.selections.count(), 0)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.answered_count, 0)

    def test_a_question_from_another_version_is_refused(self):
        other = make_questionnaire(self.admin, title = "Autre")
        foreign = add_single_choice(draft_of(other), self.admin)

        with self.assertRaises(AttemptError) as ctx:
            save_answer(self.attempt, foreign.id, {"option_ids": [foreign.options.first().id]})
        self.assertEqual(ctx.exception.code, "unknown_question")


class IdempotencyTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.question = add_single_choice(draft_of(self.q), self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()
        self.attempt = start_attempt(self.q, self.user)
        self.java = self.question.options.get(text = "Java")

    def test_replaying_the_same_request_creates_no_duplicate(self):
        payload = {"option_ids": [self.java.id]}
        first  = save_answer(self.attempt, self.question.id, payload,
                             client_sequence = 1, idempotency_key = "abc")
        second = save_answer(self.attempt, self.question.id, payload,
                             client_sequence = 1, idempotency_key = "abc")

        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(UserAnswer.objects.filter(attempt = self.attempt).count(), 1)
        self.assertEqual(UserAnswer.objects.get().revision, 1)

    def test_a_new_key_applies_the_change(self):
        cobol = self.question.options.get(text = "COBOL")
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]},
                    client_sequence = 1, idempotency_key = "k1")
        save_answer(self.attempt, self.question.id, {"option_ids": [cobol.id]},
                    client_sequence = 2, idempotency_key = "k2")

        answer = UserAnswer.objects.get(attempt = self.attempt)
        self.assertEqual(answer.value["option_ids"], [cobol.id])
        self.assertEqual(answer.revision, 2)


class ConcurrencyTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.question = add_single_choice(draft_of(self.q), self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()
        self.attempt = start_attempt(self.q, self.user)
        self.java  = self.question.options.get(text = "Java")
        self.rust  = self.question.options.get(text = "Rust")
        self.cobol = self.question.options.get(text = "COBOL")

    def test_a_late_request_never_overwrites_a_newer_answer(self):
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]},
                    client_sequence = 5, idempotency_key = "k5")

        with self.assertRaises(StaleWrite) as ctx:
            save_answer(self.attempt, self.question.id, {"option_ids": [self.cobol.id]},
                        client_sequence = 3, idempotency_key = "k3")

        self.assertEqual(ctx.exception.code, "stale_write")
        self.assertEqual(UserAnswer.objects.get().value["option_ids"], [self.java.id])
        self.assertEqual(ctx.exception.answer.client_sequence, 5)

    def test_a_newer_request_is_applied(self):
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]},
                    client_sequence = 1, idempotency_key = "k1")
        save_answer(self.attempt, self.question.id, {"option_ids": [self.rust.id]},
                    client_sequence = 2, idempotency_key = "k2")

        self.assertEqual(UserAnswer.objects.get().value["option_ids"], [self.rust.id])

    def test_sequence_zero_is_a_valid_sequence(self):
        """0 est une sequence valide, pas une absence de sequence."""
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]},
                    client_sequence = 4, idempotency_key = "k4")

        with self.assertRaises(StaleWrite):
            save_answer(self.attempt, self.question.id, {"option_ids": [self.cobol.id]},
                        client_sequence = 0, idempotency_key = "k0")

    def test_an_unsequenced_client_is_still_accepted(self):
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]})
        save_answer(self.attempt, self.question.id, {"option_ids": [self.cobol.id]})
        self.assertEqual(UserAnswer.objects.get().value["option_ids"], [self.cobol.id])

    def test_the_attempt_revision_increases_on_every_write(self):
        before = self.attempt.revision
        save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]})
        self.attempt.refresh_from_db()
        self.assertGreater(self.attempt.revision, before)

    def test_two_tabs_share_a_single_attempt(self):
        """La contrainte d'unicite empeche deux tentatives ouvertes en parallele."""
        first  = start_attempt(self.q, self.user)
        second = start_attempt(self.q, self.user)
        self.assertEqual(first.id, second.id)

    def test_one_answer_row_per_question_and_attempt(self):
        for index in range(5):
            save_answer(self.attempt, self.question.id, {"option_ids": [self.java.id]},
                        client_sequence = index + 1, idempotency_key = f"k{index}")
        self.assertEqual(UserAnswer.objects.filter(attempt = self.attempt).count(), 1)


class AutosaveApiTests(TestCase):
    """Le contrat HTTP consomme par le client d'autosave."""

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        self.question = add_single_choice(draft_of(self.q), self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()

        self.client = Client()
        self.client.force_login(self.user)
        self.java = self.question.options.get(text = "Java")

    def post(self, url, payload):
        return self.client.post(url, data = json.dumps(payload), content_type = "application/json")

    def test_answering_without_an_attempt_is_refused(self):
        response = self.post(f"/api/questionnaires/{self.q.id}/answers/",
                             {"question_id": self.question.id, "value": {"option_ids": [self.java.id]}})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "no_attempt")

    def test_full_autosave_round_trip(self):
        start = self.post(f"/api/questionnaires/{self.q.id}/start/", {})
        self.assertEqual(start.status_code, 201)

        response = self.post(f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.question.id,
            "value": {"option_ids": [self.java.id]},
            "client_sequence": 1,
            "idempotency_key": "abc",
        })
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertTrue(payload["saved"])
        self.assertEqual(payload["progress"]["answered"], 1)
        self.assertEqual(payload["visible_question_ids"], [self.question.id])

    def test_a_stale_request_answers_409_with_the_current_value(self):
        self.post(f"/api/questionnaires/{self.q.id}/start/", {})
        self.post(f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.question.id, "value": {"option_ids": [self.java.id]},
            "client_sequence": 9, "idempotency_key": "k9",
        })
        late = self.post(f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.question.id,
            "value": {"option_ids": [self.question.options.get(text = "COBOL").id]},
            "client_sequence": 2, "idempotency_key": "k2",
        })

        self.assertEqual(late.status_code, 409)
        body = late.json()
        self.assertEqual(body["code"], "stale_write")
        self.assertEqual(body["answer"]["value"]["option_ids"], [self.java.id])

    def test_an_invalid_answer_answers_400(self):
        self.post(f"/api/questionnaires/{self.q.id}/start/", {})
        response = self.post(f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.question.id, "value": {"option_ids": [999999]},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_answer")

    def test_the_state_endpoint_allows_resynchronisation(self):
        self.post(f"/api/questionnaires/{self.q.id}/start/", {})
        self.post(f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.question.id, "value": {"option_ids": [self.java.id]},
        })

        state = self.client.get(f"/api/questionnaires/{self.q.id}/state/").json()
        self.assertEqual(state["attempt"]["progress"]["answered"], 1)
        self.assertEqual(state["questions"][0]["answer"]["value"]["option_ids"], [self.java.id])

    def test_an_anonymous_user_cannot_save(self):
        response = Client().post(
            f"/api/questionnaires/{self.q.id}/answers/",
            data = json.dumps({"question_id": self.question.id, "value": None}),
            content_type = "application/json",
        )
        self.assertEqual(response.status_code, 401)
