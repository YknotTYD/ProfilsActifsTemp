"""Contrat HTTP : administration, utilisation et etancheite des corriges."""

import json

from django.test import Client, TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.models import Questionnaire

from .factories import (
    add_single_choice, draft_of, make_admin, make_questionnaire, make_user, publish,
)

class ApiTestCase(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")

        self.as_admin = Client()
        self.as_admin.force_login(self.admin)
        self.as_user = Client()
        self.as_user.force_login(self.user)

    def post(self, client, url, payload = None):
        return client.post(url, data = json.dumps(payload or {}),
                           content_type = "application/json")

    def put(self, client, url, payload = None):
        return client.put(url, data = json.dumps(payload or {}),
                          content_type = "application/json")

class AdminApiTests(ApiTestCase):

    def test_create_a_questionnaire(self):
        response = self.post(self.as_admin, "/api/questionnaires/", {"title": "Culture generale"})

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["title"], "Culture generale")
        self.assertEqual(payload["status"], c.STATUS_DRAFT)
        self.assertEqual(payload["draft_version"], 1)
        self.assertTrue(Questionnaire.objects.filter(pk = payload["id"]).exists())

    def test_creation_requires_a_title(self):
        response = self.post(self.as_admin, "/api/questionnaires/", {})
        self.assertEqual(response.status_code, 400)

    def test_a_regular_user_cannot_reach_the_admin_api(self):
        for method, url in (
            ("get",  "/api/questionnaires/"),
            ("post", "/api/questionnaires/"),
        ):
            response = (self.as_user.get(url) if method == "get"
                        else self.post(self.as_user, url, {"title": "x"}))
            self.assertEqual(response.status_code, 403, url)

    def test_anonymous_access_is_refused(self):
        self.assertEqual(Client().get("/api/questionnaires/").status_code, 401)

    def test_the_question_type_catalog_is_exposed(self):
        payload = self.as_admin.get("/api/questionnaires/types/").json()
        self.assertEqual(len(payload["types"]), 28)
        self.assertIn(c.FAMILY_NUMERIC, payload["families"])

    def test_full_authoring_flow(self):
        created = self.post(self.as_admin, "/api/questionnaires/", {"title": "Quiz"}).json()
        qid     = created["id"]

        question = self.post(self.as_admin, f"/api/questionnaires/{qid}/versions/1/questions/", {
            "type": c.TYPE_SINGLE_CHOICE,
            "text": "Capitale de la France ?",
            "options": [{"text": "Paris", "is_correct": True}, {"text": "Lyon"}],
        })
        self.assertEqual(question.status_code, 201)
        question_id = question.json()["question"]["id"]

        option = self.post(
            self.as_admin,
            f"/api/questionnaires/{qid}/versions/1/questions/{question_id}/options/",
            {"text": "Marseille"},
        )
        self.assertEqual(option.status_code, 201)

        published = self.post(self.as_admin, f"/api/questionnaires/{qid}/versions/1/publish/")
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["questionnaire"]["status"], c.STATUS_PUBLISHED)

    def test_editing_a_published_version_is_refused(self):
        q = make_questionnaire(self.admin)
        question = add_single_choice(draft_of(q), self.admin)
        publish(q, self.admin)

        response = self.put(
            self.as_admin,
            f"/api/questionnaires/{q.id}/versions/1/questions/{question.id}/",
            {"text": "Modification interdite"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("nouvelle version", response.json()["error"])

    def test_deriving_a_new_editable_version(self):
        q = make_questionnaire(self.admin)
        add_single_choice(draft_of(q), self.admin)
        publish(q, self.admin)

        response = self.post(self.as_admin, f"/api/questionnaires/{q.id}/versions/editable/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"]["version_number"], 2)
        self.assertTrue(response.json()["version"]["is_editable"])

    def test_version_comparison_endpoint(self):
        q = make_questionnaire(self.admin)
        add_single_choice(draft_of(q), self.admin)
        publish(q, self.admin)
        self.post(self.as_admin, f"/api/questionnaires/{q.id}/versions/editable/")

        diff = self.as_admin.get(
            f"/api/questionnaires/{q.id}/versions/compare/?from=1&to=2").json()["diff"]
        self.assertEqual(diff["summary"], {"added": 0, "removed": 0, "changed": 0})

    def test_duplicate_creates_an_independent_draft(self):
        q = make_questionnaire(self.admin, title = "Original")
        add_single_choice(draft_of(q), self.admin)
        publish(q, self.admin)

        copy = self.post(self.as_admin, f"/api/questionnaires/{q.id}/duplicate/").json()["questionnaire"]

        self.assertNotEqual(copy["id"], q.id)
        self.assertEqual(copy["title"], "Original (copie)")
        self.assertEqual(copy["status"], c.STATUS_DRAFT)

        clone = Questionnaire.objects.get(pk = copy["id"])
        self.assertEqual(clone.latest_version().questions.count(), 1)

    def test_delete_archives_a_questionnaire_that_has_attempts(self):
        from profils.questionnaires.services import start_attempt

        q = make_questionnaire(self.admin)
        add_single_choice(draft_of(q), self.admin)
        publish(q, self.admin)
        q.refresh_from_db()
        start_attempt(q, self.user)

        response = self.as_admin.delete(f"/api/questionnaires/{q.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["archived"])
        self.assertFalse(response.json()["deleted"])

        q.refresh_from_db()
        self.assertEqual(q.status, c.STATUS_ARCHIVED)

    def test_delete_removes_an_unused_questionnaire(self):
        q = make_questionnaire(self.admin)
        response = self.as_admin.delete(f"/api/questionnaires/{q.id}/")

        self.assertTrue(response.json()["deleted"])
        self.assertFalse(Questionnaire.objects.filter(pk = q.id).exists())

    def test_updating_the_attempt_and_answer_rules(self):
        q = make_questionnaire(self.admin)
        response = self.put(self.as_admin, f"/api/questionnaires/{q.id}/", {
            "max_attempts": 3, "cooldown_seconds": 60,
            "answer_edit_mode": c.ANSWERS_LOCKED_ON_VALIDATE,
            "navigation_mode":  c.NAVIGATION_LINEAR,
            "allow_back": False,
        })
        self.assertEqual(response.status_code, 200)

        q.refresh_from_db()
        self.assertEqual(q.max_attempts, 3)
        self.assertEqual(q.answer_edit_mode, c.ANSWERS_LOCKED_ON_VALIDATE)
        self.assertFalse(q.allow_back)

    def test_an_invalid_navigation_mode_is_refused(self):
        q = make_questionnaire(self.admin)
        response = self.put(self.as_admin, f"/api/questionnaires/{q.id}/",
                            {"navigation_mode": "TELEPORTATION"})
        self.assertEqual(response.status_code, 400)

    def test_access_rules_can_be_written_and_read_back(self):
        q = make_questionnaire(self.admin)
        response = self.put(self.as_admin, f"/api/questionnaires/{q.id}/access/", {
            "access": [[{"rule_type": c.RULE_ROLE, "role": "Premium"}]],
            "result_visibility": {"show_correct_answers": True},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["access"]), 1)
        self.assertTrue(response.json()["result_visibility"]["show_correct_answers"])

    def test_method_not_allowed_is_reported_as_json(self):
        q = make_questionnaire(self.admin)
        response = self.as_admin.get(f"/api/questionnaires/{q.id}/duplicate/")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], "method_not_allowed")

    def test_the_audit_trail_is_readable(self):
        q = make_questionnaire(self.admin)
        add_single_choice(draft_of(q), self.admin)
        publish(q, self.admin)

        entries = self.as_admin.get(f"/api/questionnaires/{q.id}/audit/").json()["entries"]
        actions = {entry["action"] for entry in entries}
        self.assertIn(c.AUDIT_PUBLISH, actions)
        self.assertIn(c.AUDIT_QUESTION_CHANGE, actions)
        self.assertIn(c.AUDIT_VERSION_CREATE, actions)

    def test_statistics_endpoint(self):
        q = make_questionnaire(self.admin)
        stats = self.as_admin.get(f"/api/questionnaires/{q.id}/statistics/").json()
        self.assertIn("attempts", stats)
        self.assertIn("by_version", stats)

class UserApiTests(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.q = make_questionnaire(self.admin, title = "Quiz public")
        self.question = add_single_choice(draft_of(self.q), self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()
        self.java = self.question.options.get(text = "Java")

    def test_the_catalog_lists_accessible_questionnaires(self):
        payload = self.as_user.get("/api/questionnaires/available/").json()
        self.assertEqual(len(payload["questionnaires"]), 1)

        card = payload["questionnaires"][0]
        self.assertEqual(card["title"], "Quiz public")
        self.assertTrue(card["can_start"]["allowed"])
        self.assertEqual(card["question_count"], 1)

    def test_the_catalog_hides_a_draft(self):
        make_questionnaire(self.admin, title = "Brouillon")
        payload = self.as_user.get("/api/questionnaires/available/").json()
        self.assertEqual(len(payload["questionnaires"]), 1)

    def test_start_then_resume(self):
        started = self.post(self.as_user, f"/api/questionnaires/{self.q.id}/start/")
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.json()["attempt"]["status"], c.ATTEMPT_IN_PROGRESS)

        current = self.as_user.get(f"/api/questionnaires/{self.q.id}/current/").json()
        self.assertEqual(current["attempt"]["id"], started.json()["attempt"]["id"])
        self.assertEqual(current["attempt"]["resume_question_id"], self.question.id)

    def test_current_returns_null_without_an_attempt(self):
        payload = self.as_user.get(f"/api/questionnaires/{self.q.id}/current/").json()
        self.assertIsNone(payload["attempt"])
        self.assertTrue(payload["can_start"]["allowed"])

    def test_the_runner_payload_never_exposes_the_correct_answers(self):
        raw = self.post(self.as_user, f"/api/questionnaires/{self.q.id}/start/").content.decode()

        self.assertNotIn("is_correct", raw)
        self.assertNotIn("expected_config", raw)
        self.assertNotIn("scoring_config", raw)

    def test_finish_and_read_the_result(self):
        self.post(self.as_user, f"/api/questionnaires/{self.q.id}/start/")
        self.post(self.as_user, f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.question.id, "value": {"option_ids": [self.java.id]},
        })
        finished = self.post(self.as_user, f"/api/questionnaires/{self.q.id}/finish/")

        self.assertEqual(finished.status_code, 200)
        result = finished.json()["result"]
        self.assertEqual(result["percentage"], "100.00")
        self.assertTrue(result["passed"])

        history = self.as_user.get(f"/api/questionnaires/{self.q.id}/results/me/").json()
        self.assertEqual(len(history["results"]), 1)

    def test_result_visibility_is_enforced(self):
        self.q.result_visibility = {
            **c.DEFAULT_RESULT_VISIBILITY,
            "show_score": False, "show_percentage": False, "show_correct_answers": False,
        }
        self.q.save()

        self.post(self.as_user, f"/api/questionnaires/{self.q.id}/start/")
        self.post(self.as_user, f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.question.id, "value": {"option_ids": [self.java.id]},
        })
        result = self.post(self.as_user, f"/api/questionnaires/{self.q.id}/finish/").json()["result"]

        self.assertNotIn("score", result)
        self.assertNotIn("percentage", result)
        self.assertIn("passed", result)
        self.assertNotIn("expected", result["answers"][0])

    def test_an_attempt_of_another_user_is_not_readable(self):
        started = self.post(self.as_user, f"/api/questionnaires/{self.q.id}/start/").json()
        attempt_id = started["attempt"]["id"]

        intruder = Client()
        intruder.force_login(make_user("intrus"))
        self.assertEqual(intruder.get(f"/api/attempts/{attempt_id}/").status_code, 403)

        self.assertEqual(self.as_admin.get(f"/api/attempts/{attempt_id}/").status_code, 200)

    def test_a_user_cannot_see_the_admin_attempt_list(self):
        self.assertEqual(
            self.as_user.get(f"/api/questionnaires/{self.q.id}/attempts/").status_code, 403)

    def test_abandon(self):
        self.post(self.as_user, f"/api/questionnaires/{self.q.id}/start/")
        response = self.post(self.as_user, f"/api/questionnaires/{self.q.id}/abandon/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], c.ATTEMPT_ABANDONED)

    def test_a_transcript_rebuilds_a_past_attempt(self):
        self.post(self.as_user, f"/api/questionnaires/{self.q.id}/start/")
        self.post(self.as_user, f"/api/questionnaires/{self.q.id}/answers/", {
            "question_id": self.question.id, "value": {"option_ids": [self.java.id]},
        })
        finished = self.post(self.as_user, f"/api/questionnaires/{self.q.id}/finish/")
        self.assertEqual(finished.status_code, 200)

        attempt_id = self.q.attempts.first().id
        transcript = self.as_admin.get(
            f"/api/questionnaires/{self.q.id}/attempts/{attempt_id}/transcript/"
        ).json()["transcript"]

        self.assertEqual(transcript["answers"][0]["question"]["text"], "Langage prefere ?")
        self.assertEqual(transcript["answers"][0]["display"], "Java")

class PageTests(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.q = make_questionnaire(self.admin)
        add_single_choice(draft_of(self.q), self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()

    def test_user_pages_render(self):
        for url in (
            "/questionnaires/",
            f"/questionnaires/{self.q.id}/",
            f"/questionnaires/{self.q.id}/results/",
        ):
            self.assertEqual(self.as_user.get(url).status_code, 200, url)

    def test_admin_pages_render(self):
        for url in (
            "/questionnaires/manage/",
            f"/questionnaires/manage/{self.q.id}/",
            f"/questionnaires/manage/{self.q.id}/versions/",
            f"/questionnaires/manage/{self.q.id}/attempts/",
            f"/questionnaires/manage/{self.q.id}/preview/1/",
        ):
            self.assertEqual(self.as_admin.get(url).status_code, 200, url)

    def test_admin_pages_are_hidden_from_regular_users(self):
        self.assertEqual(self.as_user.get("/questionnaires/manage/").status_code, 404)

    def test_anonymous_users_are_redirected_to_login(self):
        response = Client().get("/questionnaires/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

    def test_existing_pages_still_work(self):
        """Le site existant ne doit pas etre casse."""
        for url in ("/", "/login/", "/register/"):
            self.assertEqual(Client().get(url).status_code, 200, url)
