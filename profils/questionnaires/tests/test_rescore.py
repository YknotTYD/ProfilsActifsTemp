"""Reduction a 20 questions : plafond de publication et retraitement.

Deux sujets distincts, testes separement :

  * une version publiee ne peut pas depasser 20 questions ;
  * les passations enregistrees avant une reduction sont recalculees sur le
    seul perimetre encore en vigueur, et les badges suivent.

Le scenario de reference, celui qui compte : une personne passe une epreuve de
quatre questions, en reussit trois, decroche un badge ; l'epreuve est ensuite
ramenee a deux questions, dont celle qu'elle avait ratee. Elle tombe a 50 %,
sous le seuil : son score doit changer et son badge doit tomber -- sinon elle
garde une certification calculee sur des questions qui n'existent plus.
"""

from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test            import TestCase

from profils.questionnaires import constants as c
from profils.questionnaires.models     import QuestionnaireAttempt, UserBadge
from profils.questionnaires.services   import finish_attempt, save_answer, start_attempt
from profils.questionnaires.versioning import create_version, publish_version

from .factories import (
    add_single_choice, draft_of, make_admin, make_badge, make_questionnaire, make_user, publish,
)

class PublicationLimitTests(TestCase):
    """Le plafond mord a la publication, et seulement la."""

    def setUp(self):
        self.admin = make_admin()
        self.q     = make_questionnaire(self.admin)

    def _fill(self, count):
        version = draft_of(self.q)
        for index in range(count):
            add_single_choice(version, self.admin, text = f"Question {index}")
        return version

    def test_a_version_of_twenty_questions_publishes(self):
        version = self._fill(c.CERTIFICATION_QUESTION_LIMIT)
        publish_version(version, actor = self.admin)
        self.assertEqual(version.status, c.STATUS_PUBLISHED)

    def test_a_version_of_twenty_one_questions_is_refused(self):
        version = self._fill(c.CERTIFICATION_QUESTION_LIMIT + 1)
        with self.assertRaises(ValidationError) as raised:
            publish_version(version, actor = self.admin)
        self.assertIn("21", str(raised.exception))

    def test_a_draft_may_hold_more_while_it_is_being_trimmed(self):
        version = self._fill(c.CERTIFICATION_QUESTION_LIMIT + 5)
        self.assertEqual(version.status, c.STATUS_DRAFT)
        self.assertEqual(version.questions.count(), c.CERTIFICATION_QUESTION_LIMIT + 5)

class RescoreTests(TestCase):
    """Retraitement des passations anterieures a la reduction."""

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)

        version = draft_of(self.q)
        self.questions = [
            add_single_choice(version, self.admin, text = f"Question {index}")
            for index in range(4)
        ]
        publish(self.q, self.admin)
        self.q.refresh_from_db()

        self.badge = make_badge(
            "CERTIF", criteria = {"type": "questionnaire_passed", "questionnaire": self.q.id}
        )

    def _answer(self, attempt, question, correct):
        option = question.options.get(text = "Java" if correct else "COBOL")
        save_answer(attempt, question.id, {"option_ids": [option.id]})

    def _play(self, correctness):
        attempt = start_attempt(self.q, self.user)
        for question, correct in zip(self.questions, correctness):
            self._answer(attempt, question, correct)
        finish_attempt(attempt)
        return QuestionnaireAttempt.objects.get(pk = attempt.pk)

    def _reduce_to(self, keep, *, carry_over = False):
        """Publie une nouvelle version ne portant que les questions gardees.

        `carry_over` est coupe par defaut : le report de reponses est un
        mecanisme distinct, qui cree une *nouvelle* passation sur la nouvelle
        version. Il est teste a part -- ici on veut voir agir le seul
        retraitement des passations historiques.
        """
        kept_keys = {self.questions[index].stable_key for index in keep}
        version   = create_version(self.q, actor = self.admin)
        version.questions.exclude(stable_key__in = kept_keys).delete()
        publish_version(version, actor = self.admin, carry_over = carry_over)
        self.q.refresh_from_db()
        return version

    def _run(self, *args):
        out = StringIO()
        call_command("retraiter_passations", *args, stdout = out)
        return out.getvalue()

    # ------------------------------------------------------------------

    def test_a_score_is_recomputed_on_the_remaining_questions(self):
        attempt = self._play([True, True, False, False])
        self.assertEqual(attempt.percentage, 50)

        self._reduce_to([0, 1])
        self._run("--apply")

        attempt.refresh_from_db()
        self.assertEqual(attempt.percentage, 100)
        self.assertEqual(attempt.metadata[c.RESCORE_KEY]["questions_retenues"], 2)
        self.assertEqual(attempt.metadata[c.RESCORE_KEY]["questions_retirees"], 2)

    def test_a_badge_falls_when_its_criterion_stops_holding(self):
        # 3 bonnes reponses sur 4 = 75 %, au-dessus du seuil de reussite.
        self._play([True, True, True, False])
        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 1)

        # On ne garde qu'une question reussie et la question ratee : 50 %,
        # sous le seuil. La certification ne tient plus.
        self._reduce_to([0, 3])
        self._run("--apply")

        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 0)

    def test_a_badge_can_also_be_gained(self):
        attempt = self._play([True, False, False, False])
        self.assertFalse(attempt.passed)
        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 0)

        self._reduce_to([0])
        self._run("--apply")

        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)
        self.assertEqual(UserBadge.objects.filter(user = self.user).count(), 1)

    def test_the_answers_to_retired_questions_are_kept(self):
        attempt = self._play([True, True, False, False])
        self._reduce_to([0, 1])
        self._run("--apply")

        # Les reponses restent en base : on retire des questions du calcul,
        # on n'efface pas ce que la personne a repondu.
        self.assertEqual(attempt.answers.count(), 4)

    def test_the_result_carries_the_notice(self):
        attempt = self._play([True, True, False, False])
        self._reduce_to([0, 1])
        self._run("--apply")

        attempt.refresh_from_db()
        trace = attempt.result.details[c.RESCORE_KEY]
        self.assertEqual(trace["avant"]["percentage"], "50.00")
        self.assertEqual(trace["apres"]["percentage"], "100.00")

    def test_a_simulation_writes_nothing(self):
        attempt = self._play([True, True, False, False])
        self._reduce_to([0, 1])

        output = self._run()

        attempt.refresh_from_db()
        self.assertEqual(attempt.percentage, 50)
        self.assertIn("SIMULATION", output)
        self.assertIn("Passations recalculees : 1", output)

    def test_a_second_pass_changes_nothing(self):
        self._play([True, True, False, False])
        self._reduce_to([0, 1])
        self._run("--apply")

        output = self._run("--apply")
        self.assertIn("Passations recalculees : 0", output)

    def test_the_report_counts_before_and_after(self):
        self._play([True, True, True, False])
        self._reduce_to([0, 3])

        output = self._run("--apply")

        self.assertIn("AVANT", output)
        self.assertIn("APRES", output)
        self.assertIn("passations reussies         1", output)
        self.assertIn("reussite perdue  : 1", output)
        self.assertIn("Badges retires   : 1", output)

    def test_the_carry_over_result_is_not_mistaken_for_a_stale_one(self):
        """Le report de reponses cree une passation *neuve* sur le perimetre
        courant : elle n'a rien a recalculer, seule l'ancienne bouge."""
        self._play([True, True, True, False])
        self._reduce_to([0, 1], carry_over = True)

        output = self._run("--apply")

        self.assertEqual(QuestionnaireAttempt.objects.filter(user = self.user).count(), 2)
        self.assertIn("Passations recalculees : 1", output)

    def test_a_questionnaire_without_a_published_version_is_left_alone(self):
        attempt = self._play([True, True, False, False])
        self.q.current_version = None
        self.q.save(update_fields = ["current_version"])

        self._run("--apply")

        attempt.refresh_from_db()
        self.assertEqual(attempt.percentage, 50)
        self.assertNotIn(c.RESCORE_KEY, attempt.metadata)
