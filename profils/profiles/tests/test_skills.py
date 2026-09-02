##tests/test_skills.py
"""Referentiel de competences : canonicalisation, niveaux, doublons (sections 3 et 4)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from profils.profiles import constants as c
from profils.profiles import services
from profils.profiles.models import Skill, UserSkill
from profils.profiles.skills import (
    add_alias, find_skill, normalize_skill_name, resolve_skill, resolve_skills,
)

from .factories import add_skill, make_profile


class NormalizationTests(TestCase):

    def test_case_and_accents_collapse_to_one_key(self):
        for spelling in ("Java", "java", "JAVA", "  jAvA  "):
            self.assertEqual(normalize_skill_name(spelling), "java")
        self.assertEqual(normalize_skill_name("Referencement"), "referencement")
        self.assertEqual(normalize_skill_name("Référencement"), "referencement")

    def test_technical_characters_keep_their_meaning(self):
        """Un slugify naif ecraserait C++, C# et C sur la meme cle."""
        self.assertEqual(normalize_skill_name("C++"),    "cpp")
        self.assertEqual(normalize_skill_name("C#"),     "csharp")
        self.assertEqual(normalize_skill_name("F#"),     "fsharp")
        self.assertEqual(normalize_skill_name("C"),      "c")
        self.assertEqual(normalize_skill_name(".NET"),   "net")
        self.assertEqual(normalize_skill_name("ASP.NET"), "asp-net")
        self.assertEqual(normalize_skill_name("Objective-C"), "objective-c")

        keys = {normalize_skill_name(name) for name in ("C", "C++", "C#")}
        self.assertEqual(len(keys), 3)

    def test_separators_are_collapsed(self):
        self.assertEqual(normalize_skill_name("Node  js"),   "node-js")
        self.assertEqual(normalize_skill_name("node_js"),    "node-js")
        self.assertEqual(normalize_skill_name("--node.js--"), "node-js")

    def test_a_name_without_content_is_refused(self):
        for name in ("", "   ", "***", "///"):
            with self.assertRaises(ValidationError):
                normalize_skill_name(name)


class ResolutionTests(TestCase):

    def test_the_same_skill_is_never_created_twice(self):
        first  = resolve_skill("Java")
        second = resolve_skill("java")
        third  = resolve_skill("JAVA")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.pk, third.pk)
        self.assertEqual(Skill.objects.filter(slug = "java").count(), 1)

    def test_first_spelling_becomes_the_display_name(self):
        skill = resolve_skill("PostgreSQL")
        self.assertEqual(skill.name, "PostgreSQL")
        self.assertEqual(resolve_skill("postgresql").name, "PostgreSQL")

    def test_an_alias_points_to_the_existing_skill(self):
        node = resolve_skill("Node.js")
        add_alias(node, "NodeJS")

        self.assertEqual(find_skill("NodeJS").pk, node.pk)
        self.assertEqual(find_skill("nodejs").pk, node.pk)
        self.assertEqual(Skill.objects.count(), 1)

    def test_an_alias_cannot_hijack_another_skill(self):
        java = resolve_skill("Java")
        resolve_skill("JavaScript")

        with self.assertRaises(ValidationError):
            add_alias(java, "JavaScript")

    def test_resolve_without_create_returns_none(self):
        self.assertIsNone(resolve_skill("Brainfuck", create = False))
        self.assertFalse(Skill.objects.filter(slug = "brainfuck").exists())

    def test_resolve_skills_drops_duplicates_and_keeps_order(self):
        skills = resolve_skills(["Docker", "docker", "Kubernetes"])
        self.assertEqual([s.slug for s in skills], ["docker", "kubernetes"])


class UserSkillTests(TestCase):

    def setUp(self):
        self.profile = make_profile("dev")

    def test_add_skill_with_level_and_years(self):
        row = add_skill(self.profile, "Java", c.LEVEL_ADVANCED, 3)

        self.assertEqual(row.skill.name, "Java")
        self.assertEqual(row.level, c.LEVEL_ADVANCED)
        self.assertEqual(row.years_experience, 3)
        self.assertEqual(row.level_rank, c.SKILL_LEVEL_RANKS[c.LEVEL_ADVANCED])

    def test_level_rank_follows_the_level(self):
        row = add_skill(self.profile, "Docker", c.LEVEL_BEGINNER)
        self.assertEqual(row.level_rank, 1)

        services.update_skill(row, {"level": c.LEVEL_EXPERT})
        row.refresh_from_db()
        self.assertEqual(row.level, c.LEVEL_EXPERT)
        self.assertEqual(row.level_rank, 4)

    def test_the_rank_scale_is_strictly_ordered(self):
        ranks = [c.skill_level_rank(level) for level, _ in c.SKILL_LEVELS]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(len(set(ranks)), len(ranks))

    def test_readding_a_skill_updates_instead_of_duplicating(self):
        add_skill(self.profile, "Java", c.LEVEL_BEGINNER, 1)
        services.add_skill(self.profile, {
            "name": "JAVA", "level": c.LEVEL_EXPERT, "years_experience": 5,
        })

        rows = self.profile.skills.all()
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows[0].level, c.LEVEL_EXPERT)
        self.assertEqual(rows[0].years_experience, 5)

    def test_the_unique_constraint_is_enforced_in_database(self):
        from django.db import IntegrityError, transaction

        skill = resolve_skill("Rust")
        UserSkill.objects.create(profile = self.profile, skill = skill)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserSkill.objects.create(profile = self.profile, skill = skill)

    def test_remove_skill(self):
        row = add_skill(self.profile, "COBOL")
        services.remove_skill(row)
        self.assertEqual(self.profile.skills.count(), 0)
        # la competence reste au referentiel : d'autres profils la partagent
        self.assertTrue(Skill.objects.filter(slug = "cobol").exists())

    def test_reorder_skills(self):
        java   = add_skill(self.profile, "Java")
        docker = add_skill(self.profile, "Docker")

        services.reorder_skills(self.profile, [docker.skill_id, java.skill_id])
        order = list(self.profile.skills.values_list("skill__slug", flat = True))
        self.assertEqual(order, ["docker", "java"])

    def test_a_profile_cannot_declare_an_unbounded_number_of_skills(self):
        from profils.questionnaires.http import BadRequest

        for index in range(c.MAX_SKILLS_PER_PROFILE):
            add_skill(self.profile, f"skill-{index}")
        with self.assertRaises(BadRequest):
            add_skill(self.profile, "une-de-trop")

    def test_updating_an_owned_skill_is_never_blocked_by_the_cap(self):
        """Reajouter une competence deja possedee est une mise a jour, pas un ajout."""
        for index in range(c.MAX_SKILLS_PER_PROFILE):
            add_skill(self.profile, f"skill-{index}")

        row = services.add_skill(self.profile, {"name": "skill-0", "level": c.LEVEL_EXPERT})
        self.assertEqual(row.level, c.LEVEL_EXPERT)
        self.assertEqual(self.profile.skills.count(), c.MAX_SKILLS_PER_PROFILE)

    def test_an_invalid_level_is_refused(self):
        from profils.questionnaires.http import BadRequest

        with self.assertRaises(BadRequest):
            services.add_skill(self.profile, {"name": "Java", "level": "GODLIKE"})
