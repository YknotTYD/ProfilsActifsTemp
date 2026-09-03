##tests/test_question_types.py

from django.test import TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.editing       import create_question
from profils.questionnaires.question_types import AnswerError, ConfigError, all_types, get_type

from .factories import draft_of, make_admin, make_questionnaire


class RegistryTests(TestCase):

    def test_every_required_type_is_registered(self):
        registered = {t.id for t in all_types()}
        expected = {
            c.TYPE_SINGLE_CHOICE, c.TYPE_MULTIPLE_CHOICE, c.TYPE_CHECKBOX, c.TYPE_YES_NO,
            c.TYPE_TRUE_FALSE, c.TYPE_DROPDOWN, c.TYPE_MULTI_SELECT, c.TYPE_SCALE,
            c.TYPE_INTEGER, c.TYPE_DECIMAL, c.TYPE_PERCENTAGE, c.TYPE_TEMPERATURE,
            c.TYPE_DISTANCE, c.TYPE_WEIGHT, c.TYPE_HEIGHT, c.TYPE_SPEED, c.TYPE_DURATION,
            c.TYPE_DATE, c.TYPE_TIME, c.TYPE_DATETIME, c.TYPE_HOUR_MINUTE, c.TYPE_DATE_RANGE,
            c.TYPE_COUNTRY, c.TYPE_CITY, c.TYPE_YEAR, c.TYPE_MONTH, c.TYPE_WEEKDAY, c.TYPE_ADDRESS,
        }
        self.assertEqual(expected - registered, set())

    def test_no_generic_free_text_type_exists(self):
        """Section 6 : aucune saisie libre generique."""
        for handler in all_types():
            self.assertIn(
                handler.family,
                (c.FAMILY_CHOICE, c.FAMILY_NUMERIC, c.FAMILY_TEMPORAL, c.FAMILY_STRUCTURED),
            )
        self.assertNotIn("text", {t.id for t in all_types()})


class QuestionTypeTestCase(TestCase):

    def setUp(self):
        self.admin   = make_admin()
        self.q       = make_questionnaire(self.admin)
        self.version = draft_of(self.q)

    def build(self, **payload):
        payload.setdefault("text", "Question")
        return create_question(self.version, payload, actor = self.admin)

    def normalize(self, question, raw):
        return question.handler.normalize_answer(question, raw)

    def ratio(self, question, raw):
        value = self.normalize(question, raw)
        return question.handler.evaluate(question, value)[0]


class ChoiceTypeTests(QuestionTypeTestCase):

    def test_single_choice_rejects_multiple_options(self):
        question = self.build(type = c.TYPE_SINGLE_CHOICE, options = [
            {"text": "A", "is_correct": True}, {"text": "B"},
        ])
        ids = list(question.options.values_list("id", flat = True))
        with self.assertRaises(AnswerError):
            self.normalize(question, {"option_ids": ids})

    def test_unknown_option_is_rejected(self):
        question = self.build(type = c.TYPE_SINGLE_CHOICE, options = [{"text": "A"}, {"text": "B"}])
        with self.assertRaises(AnswerError):
            self.normalize(question, {"option_ids": [999999]})

    def test_multiple_choice_partial_ratio(self):
        question = self.build(type = c.TYPE_MULTIPLE_CHOICE, options = [
            {"text": "Java", "is_correct": True},
            {"text": "Rust", "is_correct": True},
            {"text": "Python", "is_correct": True},
            {"text": "COBOL"},
        ])
        options = {o.text: o.id for o in question.options.all()}

        self.assertEqual(self.ratio(question, {"option_ids": list(options.values())[:3]}), 1.0)
        self.assertAlmostEqual(
            self.ratio(question, {"option_ids": [options["Java"], options["Rust"]]}), 2 / 3)
        self.assertAlmostEqual(
            self.ratio(question, {"option_ids": [options["Java"], options["COBOL"]]}), 0.0)

    def test_penalty_per_wrong_is_configurable(self):
        question = self.build(type = c.TYPE_MULTIPLE_CHOICE, config = {"penalty_per_wrong": 0}, options = [
            {"text": "Java", "is_correct": True},
            {"text": "Rust", "is_correct": True},
            {"text": "COBOL"},
        ])
        options = {o.text: o.id for o in question.options.all()}
        self.assertAlmostEqual(
            self.ratio(question, {"option_ids": [options["Java"], options["COBOL"]]}), 0.5)

    def test_min_and_max_selected(self):
        question = self.build(type = c.TYPE_CHECKBOX,
                              config = {"min_selected": 2, "max_selected": 3},
                              options = [{"text": t} for t in "ABCD"])
        ids = list(question.options.values_list("id", flat = True))
        with self.assertRaises(AnswerError):
            self.normalize(question, {"option_ids": ids[:1]})
        with self.assertRaises(AnswerError):
            self.normalize(question, {"option_ids": ids})
        self.assertIsNotNone(self.normalize(question, {"option_ids": ids[:2]}))

    def test_accepted_combinations(self):
        question = self.build(type = c.TYPE_MULTIPLE_CHOICE, options = [
            {"text": "A"}, {"text": "B"}, {"text": "C"},
        ])
        keys = {o.text: o.stable_key for o in question.options.all()}
        question.expected_config = {"combinations": [[keys["A"], keys["B"]], [keys["C"]]]}
        question.save()

        ids = {o.text: o.id for o in question.options.all()}
        self.assertEqual(self.ratio(question, {"option_ids": [ids["A"], ids["B"]]}), 1.0)
        self.assertEqual(self.ratio(question, {"option_ids": [ids["C"]]}), 1.0)
        self.assertEqual(self.ratio(question, {"option_ids": [ids["A"]]}), 0.0)

    def test_yes_no_and_true_false_options_are_created_automatically(self):
        yes_no = self.build(type = c.TYPE_YES_NO)
        self.assertEqual(list(yes_no.options.values_list("text", flat = True)), ["Oui", "Non"])

        true_false = self.build(type = c.TYPE_TRUE_FALSE)
        self.assertEqual(list(true_false.options.values_list("text", flat = True)), ["Vrai", "Faux"])

    def test_scale_generates_its_options_and_accepts_numeric_rules(self):
        question = self.build(type = c.TYPE_SCALE, config = {"min": 1, "max": 5},
                              expected_config = {"rules": [{"type": "one_of", "values": [4, 5]}]})
        self.assertEqual(question.options.count(), 5)

        four = question.options.get(value = "4")
        two  = question.options.get(value = "2")
        self.assertEqual(self.ratio(question, {"option_ids": [four.id]}), 1.0)
        self.assertEqual(self.ratio(question, {"option_ids": [two.id]}), 0.0)


class NumericTypeTests(QuestionTypeTestCase):

    def test_integer_rejects_decimals(self):
        question = self.build(type = c.TYPE_INTEGER)
        with self.assertRaises(AnswerError):
            self.normalize(question, 4.5)
        self.assertEqual(self.normalize(question, 42)["number"], "42")

    def test_bounds_are_enforced(self):
        question = self.build(type = c.TYPE_INTEGER, config = {"min": 0, "max": 10})
        with self.assertRaises(AnswerError):
            self.normalize(question, 11)
        with self.assertRaises(AnswerError):
            self.normalize(question, -1)

    def test_exact_value(self):
        question = self.build(type = c.TYPE_INTEGER,
                              expected_config = {"rules": [{"type": "exact", "value": 42}]})
        self.assertEqual(self.ratio(question, 42), 1.0)
        self.assertEqual(self.ratio(question, 41), 0.0)

    def test_range_of_values(self):
        question = self.build(type = c.TYPE_INTEGER, expected_config = {
            "rules": [{"type": "range", "min": 40, "max": 45}]})
        self.assertEqual(self.ratio(question, 40), 1.0)
        self.assertEqual(self.ratio(question, 45), 1.0)
        self.assertEqual(self.ratio(question, 46), 0.0)

    def test_several_accepted_ranges(self):
        question = self.build(type = c.TYPE_INTEGER, expected_config = {
            "match": "any",
            "rules": [
                {"type": "range", "min": 0,  "max": 10},
                {"type": "range", "min": 90, "max": 100},
            ],
        })
        self.assertEqual(self.ratio(question, 5), 1.0)
        self.assertEqual(self.ratio(question, 95), 1.0)
        self.assertEqual(self.ratio(question, 50), 0.0)

    def test_thresholds(self):
        question = self.build(type = c.TYPE_INTEGER, expected_config = {
            "match": "all", "rules": [{"type": "min", "value": 10}, {"type": "max", "value": 20}]})
        self.assertEqual(self.ratio(question, 15), 1.0)
        self.assertEqual(self.ratio(question, 25), 0.0)

    def test_temperature_range_with_unit(self):
        question = self.build(type = c.TYPE_TEMPERATURE, config = {"unit": "C"},
                              expected_config = {"rules": [{"type": "range", "min": 18, "max": 22}]})
        self.assertEqual(self.normalize(question, 20)["unit"], "C")
        self.assertEqual(self.ratio(question, {"number": "20", "unit": "C"}), 1.0)
        self.assertEqual(self.ratio(question, {"number": "30", "unit": "C"}), 0.0)

        with self.assertRaises(AnswerError):
            self.normalize(question, {"number": "20", "unit": "F"})

    def test_percentage_defaults_to_zero_hundred(self):
        question = self.build(type = c.TYPE_PERCENTAGE)
        with self.assertRaises(AnswerError):
            self.normalize(question, 101)

    def test_decimals_are_limited_by_configuration(self):
        question = self.build(type = c.TYPE_DECIMAL, config = {"decimals": 2})
        self.assertIsNotNone(self.normalize(question, "1.25"))
        with self.assertRaises(AnswerError):
            self.normalize(question, "1.256")

    def test_every_measurement_type_has_units(self):
        for type_id in (c.TYPE_DISTANCE, c.TYPE_WEIGHT, c.TYPE_HEIGHT, c.TYPE_SPEED, c.TYPE_DURATION):
            self.assertTrue(get_type(type_id).units, type_id)


class TemporalTypeTests(QuestionTypeTestCase):

    def test_date_parsing_and_bounds(self):
        question = self.build(type = c.TYPE_DATE, config = {"min": "2026-01-01", "max": "2026-12-31"})
        self.assertEqual(self.normalize(question, "2026-06-15")["date"], "2026-06-15")
        with self.assertRaises(AnswerError):
            self.normalize(question, "2025-06-15")
        with self.assertRaises(AnswerError):
            self.normalize(question, "pas-une-date")

    def test_date_expected_value(self):
        question = self.build(type = c.TYPE_DATE,
                              expected_config = {"rules": [{"type": "exact", "value": "2026-07-14"}]})
        self.assertEqual(self.ratio(question, "2026-07-14"), 1.0)
        self.assertEqual(self.ratio(question, "2026-07-15"), 0.0)

    def test_hour_minute_drops_seconds(self):
        question = self.build(type = c.TYPE_HOUR_MINUTE)
        self.assertEqual(self.normalize(question, "08:30:45")["time"], "08:30")

    def test_datetime(self):
        question = self.build(type = c.TYPE_DATETIME)
        self.assertTrue(self.normalize(question, "2026-06-15T10:30")["datetime"].startswith("2026-06-15"))

    def test_date_range(self):
        question = self.build(type = c.TYPE_DATE_RANGE, config = {"max_days": 7})
        value = self.normalize(question, {"start": "2026-06-01", "end": "2026-06-05"})
        self.assertEqual(value, {"start": "2026-06-01", "end": "2026-06-05"})

        with self.assertRaises(AnswerError):
            self.normalize(question, {"start": "2026-06-10", "end": "2026-06-01"})
        with self.assertRaises(AnswerError):
            self.normalize(question, {"start": "2026-06-01", "end": "2026-06-30"})


class StructuredTypeTests(QuestionTypeTestCase):

    def test_country_uses_a_controlled_vocabulary(self):
        question = self.build(type = c.TYPE_COUNTRY)
        self.assertEqual(self.normalize(question, "FR")["country"], "FR")
        with self.assertRaises(AnswerError):
            self.normalize(question, "XX")

    def test_country_can_be_restricted(self):
        question = self.build(type = c.TYPE_COUNTRY, config = {"allowed": ["FR", "BE"]})
        self.assertIsNotNone(self.normalize(question, "BE"))
        with self.assertRaises(AnswerError):
            self.normalize(question, "DE")

    def test_city_requires_a_declared_vocabulary(self):
        with self.assertRaises(ConfigError):
            self.build(type = c.TYPE_CITY, config = {})

        question = self.build(type = c.TYPE_CITY, config = {"cities": [
            {"code": "PAR", "name": "Paris"}, {"code": "LYS", "name": "Lyon"},
        ]})
        self.assertIsNotNone(self.normalize(question, "PAR"))
        with self.assertRaises(AnswerError):
            self.normalize(question, "Marseille")

    def test_month_and_weekday(self):
        month = self.build(type = c.TYPE_MONTH)
        self.assertEqual(self.normalize(month, 7)["month"], "7")
        with self.assertRaises(AnswerError):
            self.normalize(month, 13)

        weekday = self.build(type = c.TYPE_WEEKDAY)
        self.assertEqual(self.normalize(weekday, 0)["weekday"], "0")
        with self.assertRaises(AnswerError):
            self.normalize(weekday, 9)

    def test_year_bounds(self):
        question = self.build(type = c.TYPE_YEAR)
        self.assertIsNotNone(self.normalize(question, 2026))
        with self.assertRaises(AnswerError):
            self.normalize(question, 1800)

    def test_address_is_validated_component_by_component(self):
        question = self.build(type = c.TYPE_ADDRESS, config = {
            "countries": ["FR"], "required_fields": ["country", "postal_code"],
        })
        value = self.normalize(question, {
            "street_number": 12, "street": "rue des Lilas",
            "postal_code": "75011", "country": "FR",
        })
        self.assertEqual(value["postal_code"], "75011")

        with self.assertRaises(AnswerError):
            self.normalize(question, {"country": "DE", "postal_code": "10115"})
        with self.assertRaises(AnswerError):
            self.normalize(question, {"country": "FR", "postal_code": "75011",
                                      "street": "<script>alert(1)</script>"})

    def test_address_street_text_can_be_forbidden(self):
        question = self.build(type = c.TYPE_ADDRESS, config = {
            "allow_street_text": False, "required_fields": [],
        })
        with self.assertRaises(AnswerError):
            self.normalize(question, {"street": "rue des Lilas"})
