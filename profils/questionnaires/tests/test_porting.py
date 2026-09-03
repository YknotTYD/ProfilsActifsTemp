##tests/test_porting.py
"""Export et import de questionnaires."""

import json

from django.core.exceptions import ValidationError
from django.test import Client, TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.editing import create_question, set_access_rules
from profils.questionnaires.models  import Questionnaire
from profils.questionnaires.porting import (
    FORMAT, QUESTION_FIELDS, export_questionnaire, import_questionnaire, validate_document,
)
from profils.questionnaires.services   import finish_attempt, save_answer, start_attempt
from profils.questionnaires.versioning import publish_version

from .factories import (
    add_single_choice, draft_of, make_admin, make_badge, make_questionnaire, make_user, publish,
)


class ExportTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.q = make_questionnaire(self.admin, title = "Quiz exportable",
                                    max_attempts = 3, cooldown_seconds = 60)
        self.version = draft_of(self.q)
        self.question = add_single_choice(self.version, self.admin)
        create_question(self.version, {
            "type": c.TYPE_TEMPERATURE, "text": "Temperature ideale ?",
            "config": {"unit": "C"},
            "expected_config": {"rules": [{"type": "range", "min": 18, "max": 22}]},
        }, actor = self.admin)

    def test_document_shape(self):
        doc = export_questionnaire(self.q)

        self.assertEqual(doc["format"], FORMAT)
        self.assertEqual(doc["questionnaire"]["title"], "Quiz exportable")
        self.assertEqual(doc["questionnaire"]["attempt_rules"]["max_attempts"], 3)
        self.assertEqual(len(doc["content"]["questions"]), 2)

    def test_document_carries_no_primary_keys(self):
        doc  = export_questionnaire(self.q)
        blob = json.dumps(doc["content"])

        for question in doc["content"]["questions"]:
            self.assertNotIn("id", question)
            for option in question["options"]:
                self.assertNotIn("id", option)
                self.assertIn("stable_key", option)
        self.assertIn("stable_key", blob)

    def test_document_is_json_serialisable(self):
        json.dumps(export_questionnaire(self.q))

    def test_export_of_a_specific_version(self):
        publish_version(self.version, actor = self.admin)
        doc = export_questionnaire(self.q, self.version)
        self.assertEqual(doc["source"]["version_number"], 1)

    def test_export_without_version_is_refused(self):
        empty = Questionnaire.objects.create(title = "Vide", created_by = self.admin)
        with self.assertRaises(ValidationError):
            export_questionnaire(empty)


class ImportTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.source = make_questionnaire(self.admin, title = "Original", max_attempts = 2)
        self.version = draft_of(self.source)

    def roundtrip(self, **kwargs):
        return import_questionnaire(export_questionnaire(self.source), actor = self.admin, **kwargs)

    def test_roundtrip_recreates_the_content(self):
        add_single_choice(self.version, self.admin)
        copy = self.roundtrip()

        self.assertNotEqual(copy.pk, self.source.pk)
        self.assertEqual(copy.status, c.STATUS_DRAFT)
        self.assertEqual(copy.max_attempts, 2)

        original = self.version.questions.first()
        clone    = copy.latest_version().questions.first()
        self.assertEqual(clone.text, original.text)
        self.assertEqual(clone.type, original.type)
        self.assertEqual(
            list(clone.options.values_list("text", "is_correct")),
            list(original.options.values_list("text", "is_correct")))

    def test_stable_keys_are_preserved(self):
        question = add_single_choice(self.version, self.admin)
        clone = self.roundtrip().latest_version().questions.first()

        self.assertEqual(clone.stable_key, question.stable_key)
        self.assertEqual(
            sorted(o.stable_key for o in clone.options.all()),
            sorted(o.stable_key for o in question.options.all()))

    def test_conditions_survive_the_roundtrip(self):
        first = create_question(self.version, {
            "type": c.TYPE_YES_NO, "text": "Avez-vous une voiture ?"}, actor = self.admin)
        yes = first.options.get(value = "yes")
        create_question(self.version, {
            "type": c.TYPE_SINGLE_CHOICE, "text": "Quel modele ?", "required": False,
            "options": [{"text": "Citroen"}, {"text": "Renault"}],
            "condition": {"question": first.stable_key, "operator": "EQUALS",
                          "value": yes.stable_key},
        }, actor = self.admin)

        clone = self.roundtrip().latest_version()
        child = clone.questions.get(text = "Quel modele ?")

        self.assertIsNotNone(child.condition)
        self.assertEqual(child.condition["question"], first.stable_key)
        self.assertEqual(child.condition["value"], yes.stable_key)
        self.assertTrue(clone.questions.filter(stable_key = child.condition["question"]).exists())

    def test_a_forward_condition_is_accepted(self):
        """Une condition peut referencer une question importee plus tard."""
        create_question(self.version, {
            "type": c.TYPE_YES_NO, "text": "Premiere"}, actor = self.admin)
        second = create_question(self.version, {
            "type": c.TYPE_YES_NO, "text": "Seconde"}, actor = self.admin)

        doc = export_questionnaire(self.source)
        # la premiere question depend de la seconde
        doc["content"]["questions"][0]["condition"] = {
            "question": second.stable_key, "operator": "ANSWERED"}

        clone = import_questionnaire(doc, actor = self.admin).latest_version()
        self.assertEqual(clone.questions.get(text = "Premiere").condition["question"],
                         second.stable_key)

    def test_expected_answers_survive(self):
        create_question(self.version, {
            "type": c.TYPE_TEMPERATURE, "text": "Temperature ?", "config": {"unit": "C"},
            "expected_config": {"rules": [{"type": "range", "min": 18, "max": 22}]},
        }, actor = self.admin)

        clone = self.roundtrip().latest_version().questions.first()
        self.assertEqual(clone.expected_config["rules"][0]["max"], 22)
        self.assertTrue(clone.is_graded)

    def test_scoring_survives(self):
        add_single_choice(self.version, self.admin, scoring_config = {"weight": 3, "incorrect_score": -1})
        self.version.scoring_config = {"pass_threshold_percent": 80, "floor_negative": False, "levels": []}
        self.version.save()

        copy = self.roundtrip().latest_version()
        self.assertEqual(copy.scoring["pass_threshold_percent"], 80)
        self.assertEqual(copy.questions.first().scoring["weight"], 3)

    def test_import_creates_an_independent_copy(self):
        question = add_single_choice(self.version, self.admin)
        copy = self.roundtrip()

        clone = copy.latest_version().questions.first()
        clone.text = "Modifie apres import"
        clone.save()

        question.refresh_from_db()
        self.assertEqual(question.text, "Langage prefere ?")

    def test_a_custom_title_can_be_given(self):
        add_single_choice(self.version, self.admin)
        self.assertEqual(self.roundtrip(title = "Copie 2026").title, "Copie 2026")

    def test_the_import_is_a_draft_and_publishable(self):
        add_single_choice(self.version, self.admin)
        copy = self.roundtrip()
        version = copy.latest_version()

        self.assertTrue(version.is_editable)
        publish_version(version, actor = self.admin)
        copy.refresh_from_db()
        self.assertEqual(copy.status, c.STATUS_PUBLISHED)

    def test_every_question_type_survives_a_roundtrip(self):
        from profils.questionnaires.question_types import all_types

        for handler in all_types():
            payload = {"type": handler.id, "text": f"Question {handler.id}", "required": False}
            if handler.uses_options and not getattr(handler, "fixed_options", ()) \
                    and handler.id != c.TYPE_SCALE:
                payload["options"] = [{"text": "A", "is_correct": True}, {"text": "B"}]
            if handler.id == c.TYPE_SCALE:
                payload["config"] = {"min": 1, "max": 5, "step": 1}
            if handler.id == c.TYPE_CITY:
                payload["config"] = {"cities": [{"code": "PAR", "name": "Paris"}]}
            create_question(self.version, payload, actor = self.admin)

        clone = self.roundtrip().latest_version()
        self.assertEqual(clone.questions.count(), self.version.questions.count())
        self.assertEqual(
            sorted(clone.questions.values_list("type", flat = True)),
            sorted(self.version.questions.values_list("type", flat = True)))


class ImportRulesTests(TestCase):

    def test_role_rules_are_reimported(self):
        admin = make_admin()
        q = make_questionnaire(admin)
        add_single_choice(draft_of(q), admin)
        set_access_rules(q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_ROLE, "role": "Premium"}]], actor = admin)

        copy = import_questionnaire(export_questionnaire(q), actor = admin)
        rules = copy.access_rules.filter(kind = c.RULE_KIND_ACCESS)
        self.assertEqual(rules.count(), 1)
        self.assertEqual(rules.first().role, "Premium")

    def test_a_badge_absent_from_this_instance_is_skipped(self):
        admin = make_admin()
        badge = make_badge("SPECIAL")
        q = make_questionnaire(admin)
        add_single_choice(draft_of(q), admin)
        set_access_rules(q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_BADGE, "badge_code": "SPECIAL"}]], actor = admin)

        doc = export_questionnaire(q)
        self.assertEqual(doc["questionnaire"]["access"][0][0]["badge_code"], "SPECIAL")

        badge.delete()
        copy = import_questionnaire(doc, actor = admin)
        self.assertEqual(copy.access_rules.count(), 0)

    def test_a_user_rule_is_matched_by_username(self):
        admin = make_admin()
        target = make_user("cible")
        q = make_questionnaire(admin)
        add_single_choice(draft_of(q), admin)
        set_access_rules(q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_USER, "user_id": target.id}]], actor = admin)

        doc = export_questionnaire(q)
        self.assertEqual(doc["questionnaire"]["access"][0][0]["username"], "cible")

        copy = import_questionnaire(doc, actor = admin)
        self.assertEqual(copy.access_rules.first().target_user_id, target.id)


class DocumentValidationTests(TestCase):

    def test_a_foreign_format_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_document({"format": "autre-chose", "content": {"questions": []}})

    def test_a_future_format_version_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_document({"format": FORMAT, "format_version": 99, "content": {"questions": []}})

    def test_a_missing_content_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_document({"format": FORMAT})

    def test_an_unknown_question_type_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_document({"format": FORMAT, "content": {"questions": [
                {"text": "Question", "type": "teleportation"}]}})
        self.assertIn("teleportation", str(ctx.exception))

    def test_a_question_without_text_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_document({"format": FORMAT, "content": {"questions": [
                {"type": c.TYPE_INTEGER}]}})

    def test_duplicate_stable_keys_are_refused(self):
        with self.assertRaises(ValidationError):
            validate_document({"format": FORMAT, "content": {"questions": [
                {"text": "A", "type": c.TYPE_INTEGER, "stable_key": "x"},
                {"text": "B", "type": c.TYPE_INTEGER, "stable_key": "x"}]}})

    def test_an_invalid_configuration_is_refused_at_import(self):
        admin = make_admin()
        with self.assertRaises(ValidationError) as ctx:
            import_questionnaire({"format": FORMAT, "content": {"questions": [
                {"text": "Ville ?", "type": c.TYPE_CITY, "config": {}}]}}, actor = admin)
        self.assertIn("cities", str(ctx.exception))

    def test_a_failed_import_leaves_nothing_behind(self):
        admin = make_admin()
        before = Questionnaire.objects.count()
        with self.assertRaises(ValidationError):
            import_questionnaire({"format": FORMAT, "content": {"questions": [
                {"text": "Correcte", "type": c.TYPE_INTEGER},
                {"text": "Ville ?",  "type": c.TYPE_CITY, "config": {}}]}}, actor = admin)
        self.assertEqual(Questionnaire.objects.count(), before)


class PortingApiTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("simple")
        self.q = make_questionnaire(self.admin, title = "A exporter")
        add_single_choice(draft_of(self.q), self.admin)

        self.client = Client()
        self.client.force_login(self.admin)

    def test_export_endpoint(self):
        response = self.client.get(f"/api/questionnaires/{self.q.id}/export/")
        self.assertEqual(response.status_code, 200)

        doc = response.json()
        self.assertEqual(doc["format"], FORMAT)
        self.assertEqual(len(doc["content"]["questions"]), 1)

    def test_import_endpoint(self):
        doc = self.client.get(f"/api/questionnaires/{self.q.id}/export/").json()
        response = self.client.post("/api/questionnaires/import/",
                                    data = json.dumps({"document": doc, "title": "Importe"}),
                                    content_type = "application/json")

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["questions"], 1)
        self.assertEqual(payload["questionnaire"]["title"], "Importe")

    def test_a_bare_document_is_accepted(self):
        doc = self.client.get(f"/api/questionnaires/{self.q.id}/export/").json()
        response = self.client.post("/api/questionnaires/import/", data = json.dumps(doc),
                                    content_type = "application/json")
        self.assertEqual(response.status_code, 201)

    def test_a_bad_document_answers_400(self):
        response = self.client.post("/api/questionnaires/import/",
                                    data = json.dumps({"format": "n'importe quoi"}),
                                    content_type = "application/json")
        self.assertEqual(response.status_code, 400)

    def test_a_regular_user_cannot_export_or_import(self):
        client = Client()
        client.force_login(self.user)
        self.assertEqual(client.get(f"/api/questionnaires/{self.q.id}/export/").status_code, 403)
        self.assertEqual(client.post("/api/questionnaires/import/", data = "{}",
                                     content_type = "application/json").status_code, 403)

    def test_results_are_not_exported(self):
        """Un export contient le questionnaire, jamais les donnees des participants."""
        publish(self.q, self.admin)
        self.q.refresh_from_db()
        question = self.q.current_version.questions.first()

        attempt = start_attempt(self.q, self.user)
        save_answer(attempt, question.id, {"option_ids": [question.options.first().id]})
        finish_attempt(attempt)

        doc = self.client.get(f"/api/questionnaires/{self.q.id}/export/").json()

        # le document n'expose que la definition du questionnaire
        self.assertEqual(set(doc), {"format", "format_version", "exported_at", "source",
                                    "questionnaire", "content"})
        self.assertEqual(set(doc["content"]), {"title", "description", "scoring_config", "questions"})

        # aucune trace du participant ni de son passage
        self.assertNotIn(self.user.username, json.dumps(doc))
        for question_doc in doc["content"]["questions"]:
            self.assertEqual(
                set(question_doc) - {"stable_key", "options"}, set(QUESTION_FIELDS))
