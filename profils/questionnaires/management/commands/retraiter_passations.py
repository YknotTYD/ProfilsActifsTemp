"""Retraitement des passations anterieures a la reduction a 20 questions.

Contexte
--------
L'epreuve de certification est ramenee a 20 questions. Des passations ont ete
enregistrees avant cette reduction, sur un perimetre plus large, et des badges
ont ete attribues a partir des scores calcules a ce moment-la. Laisser ces
scores en l'etat reviendrait a afficher a une personne une note calculee sur
des questions qui n'existent plus : c'est precisement ce qu'on ne peut pas
faire.

Decision retenue
----------------
On **recalcule** sur les seules questions retenues, plutot que d'invalider les
passations (cela effacerait un travail reel) ou de les conserver telles quelles
en les marquant (cela laisserait le score fantome affiche).

Concretement, pour chaque passation terminee sur une version anterieure :

  1. le score est rejoue sur le perimetre de la version de reference -- les
     reponses aux questions retirees restent en base, elles cessent seulement
     de compter ;
  2. la passation et son resultat portent desormais la trace du retraitement
     (date, version de reference, score avant, score apres) ;
  3. les badges sont reevalues sur les scores recalcules : un badge dont le
     critere n'est plus satisfait est retire, un badge nouvellement merite est
     attribue.

Aucune reponse n'est supprimee, aucune passation n'est detruite. Ce qui change,
ce sont des scores et des attributions -- et chacun de ces changements est
compte, journalise et exportable.

Rejouable : un second passage sur une base deja traitee ne trouve plus rien a
recalculer et ne modifie rien. Le mode par defaut est une simulation ; il faut
`--apply` pour ecrire.

Usage :
    python manage.py retraiter_passations                        # simulation
    python manage.py retraiter_passations --apply                # ecriture
    python manage.py retraiter_passations --questionnaire 6      # cible
    python manage.py retraiter_passations --json rapport.json    # rapport
    docker compose exec web python manage.py retraiter_passations --apply

Voir `docs/certification-20-questions.md` pour le choix des 20 questions.
"""

import json

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db                   import transaction
from django.utils                import timezone

from profils.questionnaires import constants as c
from profils.questionnaires.auditing import log
from profils.questionnaires.badges   import award_for_result, evaluate_badge
from profils.questionnaires.models   import (
    Badge, Questionnaire, QuestionnaireAttempt, QuestionnaireResult, UserBadge,
)
from profils.questionnaires.scoring import score_attempt

# Une passation n'est retraitee que si elle est terminee : une passation en
# cours sera scoree a sa fin, sur le perimetre courant, sans rien avoir a
# rejouer. Les passations de mode TEST sont hors sujet -- elles n'ont jamais
# porte ni score public ni badge reel.
TREATABLE_STATUSES = (c.ATTEMPT_COMPLETED,)

def _reference_version(questionnaire):
    """Version qui fait foi pour le perimetre des questions.

    C'est la version publiee, celle que passe aujourd'hui un candidat. A
    defaut -- questionnaire jamais publie, ou publication retiree -- il n'y a
    pas de perimetre de reference et le questionnaire est laisse tranquille.
    """
    return questionnaire.current_version

def _decimal(value):
    return None if value is None else str(Decimal(value))

class Command(BaseCommand):
    help = (
        "Recalcule les passations enregistrees avant la reduction a 20 questions, "
        "reevalue les badges correspondants, et rend les compteurs avant/apres."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action = "store_true",
            help = "ecrit reellement les changements (sans ce drapeau : simulation).",
        )
        parser.add_argument(
            "--questionnaire", type = int, default = None, metavar = "ID",
            help = "ne traiter qu'un questionnaire donne.",
        )
        parser.add_argument(
            "--json", dest = "json_path", default = None, metavar = "CHEMIN",
            help = "ecrit le rapport complet, exploitable par une machine.",
        )

    # ------------------------------------------------------------------
    # Comptage
    # ------------------------------------------------------------------

    def _counts(self, questionnaires) -> dict:
        """Photographie chiffree, prise avant puis apres le traitement."""
        ids      = [q.id for q in questionnaires]
        attempts = QuestionnaireAttempt.objects.filter(
            questionnaire_id__in = ids, is_test = False, status__in = TREATABLE_STATUSES,
        )
        results  = QuestionnaireResult.objects.filter(
            questionnaire_id__in = ids, is_test = False,
        )
        return {
            "passations":         attempts.count(),
            "passations_reussies": attempts.filter(passed = True).count(),
            "resultats":          results.count(),
            "badges":             UserBadge.objects.filter(
                is_test = False, source_result__questionnaire_id__in = ids,
            ).count(),
        }

    # ------------------------------------------------------------------
    # Retraitement d'une passation
    # ------------------------------------------------------------------

    def _rescore(self, attempt, reference, retained_keys, *, apply: bool) -> dict | None:
        """Rejoue une passation sur le perimetre de reference.

        Retourne la ligne de rapport, ou None si la passation n'avait rien a
        recalculer -- c'est ce qui rend la commande rejouable : au second
        passage, plus aucune passation ne bouge.
        """
        computed = score_attempt(attempt, only_stable_keys = retained_keys)

        before = {
            "score":      _decimal(attempt.score),
            "max_score":  _decimal(attempt.max_score),
            "percentage": _decimal(attempt.percentage),
            "passed":     attempt.passed,
        }
        after = {
            "score":      _decimal(computed["score"]),
            "max_score":  _decimal(computed["max_score"]),
            "percentage": _decimal(computed["percentage"]),
            "passed":     computed["passed"],
        }
        if before == after:
            return None

        retired = [
            entry["stable_key"] for entry in computed["details"]["questions"]
            if entry.get("skipped") == "retired_question"
        ]

        trace = {
            "date":               timezone.now().isoformat(),
            "version_reference":  reference.version_number,
            "version_passation":  attempt.version.version_number,
            "questions_retenues": len(retained_keys),
            "questions_retirees": len(retired),
            "avant":              before,
            "apres":              after,
        }

        row = {
            "passation":     attempt.id,
            "utilisateur":   attempt.user_id,
            "questionnaire": attempt.questionnaire_id,
            **trace,
        }

        if not apply:
            return row

        attempt.score      = computed["score"]
        attempt.max_score  = computed["max_score"]
        attempt.percentage = computed["percentage"]
        attempt.passed     = computed["passed"]
        attempt.metadata   = dict(attempt.metadata or {}) | {c.RESCORE_KEY: trace}
        attempt.revision  += 1
        attempt.save(update_fields = [
            "score", "max_score", "percentage", "passed", "metadata",
            "revision", "last_activity_at",
        ])

        result = QuestionnaireResult.objects.filter(attempt = attempt).first()
        if result is not None:
            # Le resultat est mis a jour, mais les valeurs d'origine sont
            # conservees dans la trace : rien n'est perdu, et la fiche cesse
            # d'afficher un score calcule sur des questions disparues.
            result.score      = computed["score"]
            result.max_score  = computed["max_score"]
            result.percentage = computed["percentage"]
            result.passed     = computed["passed"]
            result.level      = computed["level"]
            result.details    = dict(computed["details"]) | {c.RESCORE_KEY: trace}
            result.save(update_fields = [
                "score", "max_score", "percentage", "passed", "level", "details",
            ])

        log(None, c.AUDIT_RESCORE, attempt,
            questionnaire = attempt.questionnaire, old = before, new = after,
            **{c.RESCORE_KEY: trace})
        return row

    # ------------------------------------------------------------------
    # Reevaluation des badges
    # ------------------------------------------------------------------

    def _reevaluate_badges(self, questionnaires, *, apply: bool) -> dict:
        """Retire les badges dont le critere n'est plus tenu, attribue les autres.

        Un badge attribue depuis un resultat de questionnaire est reevalue sur
        ce meme resultat, recalcule. Les badges manuels ne sont jamais touches :
        ils ne dependent d'aucun score.
        """
        ids     = [q.id for q in questionnaires]
        revoked = []
        awarded = []

        held = (
            UserBadge.objects
            .filter(is_test = False,
                    source          = c.BADGE_SOURCE_RESULT,
                    source_result__questionnaire_id__in = ids)
            .select_related("badge", "user", "source_result")
        )
        for user_badge in held:
            result = user_badge.source_result
            if result is None:
                continue
            if evaluate_badge(user_badge.badge, user_badge.user, result):
                continue
            revoked.append({
                "utilisateur": user_badge.user_id,
                "badge":       user_badge.badge.code,
                "resultat":    result.id,
                "motif":       "critere non tenu apres recalcul",
            })
            if apply:
                log(None, c.AUDIT_BADGE_REVOKE, user_badge,
                    questionnaire = result.questionnaire,
                    old = {"badge": user_badge.badge.code, "user": user_badge.user_id})
                user_badge.delete()

        # Un recalcul peut aussi faire *gagner* un badge : le score sur 20
        # questions peut depasser un seuil que les 100 questions diluaient.
        results = (
            QuestionnaireResult.objects
            .filter(questionnaire_id__in = ids, is_test = False)
            .select_related("user", "questionnaire")
        )
        for result in results:
            if not apply:
                existing = set(
                    UserBadge.objects.filter(user = result.user).values_list("badge_id", flat = True)
                )
                for badge in Badge.objects.filter(active = True).exclude(id__in = existing):
                    if evaluate_badge(badge, result.user, result):
                        awarded.append({
                            "utilisateur": result.user_id,
                            "badge":       badge.code,
                            "resultat":    result.id,
                        })
                continue
            for user_badge in award_for_result(result):
                awarded.append({
                    "utilisateur": user_badge.user_id,
                    "badge":       user_badge.badge.code,
                    "resultat":    result.id,
                })

        return {"retires": revoked, "attribues": awarded}

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------

    def _write_counts(self, title, counts):
        self.stdout.write(f"  {title}")
        for key in ("passations", "passations_reussies", "resultats", "badges"):
            self.stdout.write(f"    {key.replace('_', ' '):22s} {counts[key]:>6d}")

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        apply     = options["apply"]
        target    = options["questionnaire"]
        json_path = options["json_path"]

        questionnaires = Questionnaire.objects.select_related("current_version")
        if target is not None:
            questionnaires = questionnaires.filter(pk = target)
            if not questionnaires.exists():
                raise CommandError(f"aucun questionnaire d'identifiant {target}")
        questionnaires = list(questionnaires)

        treatable = [q for q in questionnaires if _reference_version(q) is not None]
        skipped   = [q for q in questionnaires if _reference_version(q) is None]

        mode = "ECRITURE" if apply else "SIMULATION (utiliser --apply pour ecrire)"
        self.stdout.write(f"Retraitement des passations -- mode {mode}")
        self.stdout.write(f"Plafond de reference : {c.CERTIFICATION_QUESTION_LIMIT} questions\n")

        before = self._counts(treatable)
        self._write_counts("AVANT", before)
        self.stdout.write("")

        rows = []
        with transaction.atomic():
            for questionnaire in treatable:
                reference = _reference_version(questionnaire)
                retained  = set(
                    reference.questions.values_list("stable_key", flat = True)
                )
                attempts = (
                    QuestionnaireAttempt.objects
                    .filter(questionnaire = questionnaire, is_test = False,
                            status__in = TREATABLE_STATUSES)
                    .select_related("version", "user")
                )
                for attempt in attempts:
                    row = self._rescore(attempt, reference, retained, apply = apply)
                    if row is not None:
                        rows.append(row)

            badges = self._reevaluate_badges(treatable, apply = apply)

            if not apply:
                transaction.set_rollback(True)

        after = self._counts(treatable) if apply else before

        # --- rendu -----------------------------------------------------
        self.stdout.write(f"Passations recalculees : {len(rows)}")
        gained = sum(1 for r in rows if r["apres"]["passed"] and not r["avant"]["passed"])
        lost   = sum(1 for r in rows if r["avant"]["passed"] and not r["apres"]["passed"])
        self.stdout.write(f"  dont reussite acquise : {gained}")
        self.stdout.write(f"  dont reussite perdue  : {lost}")
        self.stdout.write(f"Badges retires   : {len(badges['retires'])}")
        self.stdout.write(f"Badges attribues : {len(badges['attribues'])}\n")

        if skipped:
            self.stdout.write(
                f"Ignores (aucune version publiee, donc aucun perimetre de "
                f"reference) : {', '.join(str(q.id) for q in skipped)}\n"
            )

        self._write_counts("APRES", after)

        if not apply:
            self.stdout.write(self.style.WARNING(
                "\nSimulation : la base n'a pas ete modifiee. Relancer avec --apply."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("\nTraitement applique."))

        report = {
            "date":            timezone.now().isoformat(),
            "mode":            "apply" if apply else "simulation",
            "plafond":         c.CERTIFICATION_QUESTION_LIMIT,
            "avant":           before,
            "apres":           after,
            "passations":      rows,
            "badges":          badges,
            "questionnaires_ignores": [q.id for q in skipped],
        }
        if json_path:
            with open(json_path, "w", encoding = "utf-8") as handle:
                json.dump(report, handle, ensure_ascii = False, indent = 2)
            self.stdout.write(f"Rapport ecrit : {json_path}")
