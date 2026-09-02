##tests/test_sections.py
"""Experiences, formations, certifications, projets, langues (sections 5 a 9)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from profils.profiles import constants as c
from profils.profiles import services
from profils.profiles.models import Skill, WorkExperienceSkill
from profils.questionnaires.http import BadRequest

from .factories import (
    add_certification, add_education, add_experience, add_language, add_project,
    make_profile,
)


class ExperienceTests(TestCase):

    def setUp(self):
        self.profile = make_profile("experimente")

    def test_create_with_all_the_fields(self):
        row = services.create_experience(self.profile, {
            "title": "Developpeur backend", "company": "ACME",
            "description": "Services distribues.",
            "start_date": "2020-01-01", "end_date": "2022-07-01",
            "location_city": "Nantes", "location_country": "fr",
            "contract_type": c.CONTRACT_CDI,
            "skills": ["Java", "Docker"],
        })

        self.assertEqual(row.title, "Developpeur backend")
        self.assertEqual(row.location_country, "FR")
        self.assertEqual(row.duration_months, 30)
        self.assertEqual(
            sorted(link.skill.slug for link in row.skill_links.all()), ["docker", "java"]
        )

    def test_linked_skills_use_the_shared_catalog(self):
        """Une competence citee dans une experience est la meme ligne que celle du profil."""
        services.add_skill(self.profile, {"name": "Java"})
        row = add_experience(self.profile, skills = ["JAVA"])

        java = Skill.objects.get(slug = "java")
        self.assertEqual(Skill.objects.filter(slug = "java").count(), 1)
        self.assertEqual(row.skill_links.first().skill_id, java.pk)

    def test_a_current_experience_has_no_end_date(self):
        row = services.create_experience(self.profile, {
            "title": "Poste actuel", "company": "ACME",
            "start_date": "2023-01-01", "end_date": "2024-01-01",
            "is_current": True,
        })
        self.assertIsNone(row.end_date)
        self.assertTrue(row.is_current)

    def test_an_end_date_before_the_start_is_refused(self):
        with self.assertRaises(ValidationError):
            services.create_experience(self.profile, {
                "title": "Voyage temporel", "company": "ACME",
                "start_date": "2022-01-01", "end_date": "2020-01-01",
            })

    def test_a_missing_required_field_is_refused(self):
        with self.assertRaises(BadRequest):
            services.create_experience(self.profile, {"company": "ACME",
                                                      "start_date": "2020-01-01"})
        with self.assertRaises(BadRequest):
            services.create_experience(self.profile, {"title": "Dev", "company": "ACME"})

    def test_update_replaces_the_linked_skills(self):
        row = add_experience(self.profile, skills = ["Java", "Docker"])
        services.update_experience(row, {"skills": ["Rust"]})

        self.assertEqual([link.skill.slug for link in row.skill_links.all()], ["rust"])
        self.assertEqual(WorkExperienceSkill.objects.filter(experience = row).count(), 1)

    def test_update_without_the_skills_key_leaves_them_alone(self):
        row = add_experience(self.profile, skills = ["Java"])
        services.update_experience(row, {"title": "Nouveau titre"})
        self.assertEqual(row.skill_links.count(), 1)

    def test_delete(self):
        row = add_experience(self.profile)
        services.delete_experience(row)
        self.assertEqual(self.profile.experiences.count(), 0)


class TotalExperienceTests(TestCase):
    """`total_experience_months` alimente le filtre et le classement : il doit suivre."""

    def setUp(self):
        self.profile = make_profile("compteur")

    def test_it_is_recomputed_on_create_and_delete(self):
        row = add_experience(self.profile, start = date(2020, 1, 1), end = date(2022, 1, 1))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_experience_months, 24)

        services.delete_experience(row)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_experience_months, 0)

    def test_consecutive_periods_add_up(self):
        add_experience(self.profile, start = date(2018, 1, 1), end = date(2020, 1, 1))
        add_experience(self.profile, company = "B",
                       start = date(2020, 1, 1), end = date(2021, 1, 1))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_experience_months, 36)

    def test_overlapping_periods_are_counted_once(self):
        """Deux postes menes de front sur la meme annee ne font pas deux ans."""
        add_experience(self.profile, start = date(2020, 1, 1), end = date(2021, 1, 1))
        add_experience(self.profile, company = "B",
                       start = date(2020, 6, 1), end = date(2021, 1, 1))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_experience_months, 12)

    def test_an_update_refreshes_the_total(self):
        row = add_experience(self.profile, start = date(2020, 1, 1), end = date(2021, 1, 1))
        services.update_experience(row, {"end_date": "2022-01-01"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_experience_months, 24)


class EducationTests(TestCase):

    def setUp(self):
        self.profile = make_profile("etudiant")

    def test_create_with_degree_and_skills(self):
        row = services.create_education(self.profile, {
            "institution": "Epitech", "degree": "Master of Science",
            "degree_level": c.DEGREE_BAC_5, "field_of_study": "Informatique",
            "start_date": "2018-09-01", "end_date": "2023-06-30",
            "diploma_url": "https://exemple.test/diplome.pdf",
            "skills": ["C", "C++"],
        })

        self.assertEqual(row.degree_level, c.DEGREE_BAC_5)
        self.assertEqual(
            sorted(link.skill.slug for link in row.skill_links.all()), ["c", "cpp"]
        )

    def test_degree_ranks_are_ordered(self):
        self.assertGreater(c.degree_level_rank(c.DEGREE_BAC_5),
                           c.degree_level_rank(c.DEGREE_BAC_3))
        self.assertGreater(c.degree_level_rank(c.DEGREE_BAC_3),
                           c.degree_level_rank(c.DEGREE_BAC))

    def test_update_and_delete(self):
        row = add_education(self.profile)
        services.update_education(row, {"degree": "Licence",
                                        "degree_level": c.DEGREE_BAC_3})
        row.refresh_from_db()
        self.assertEqual(row.degree_level, c.DEGREE_BAC_3)

        services.delete_education(row)
        self.assertEqual(self.profile.education.count(), 0)

    def test_an_invalid_degree_level_is_refused(self):
        with self.assertRaises(BadRequest):
            services.create_education(self.profile, {
                "institution": "X", "start_date": "2020-01-01",
                "degree_level": "BAC_12",
            })


class CertificationTests(TestCase):

    def setUp(self):
        self.profile = make_profile("certifie")

    def test_create_with_verification(self):
        row = services.create_certification(self.profile, {
            "name": "AWS Solutions Architect", "issuer": "Amazon",
            "issued_on": "2024-03-01", "expires_on": "2027-03-01",
            "credential_id": "ABC-123",
            "verification_url": "https://verify.test/ABC-123",
            "skills": ["AWS"],
        })

        self.assertEqual(row.credential_id, "ABC-123")
        self.assertFalse(row.is_expired)
        self.assertEqual(row.skill_links.count(), 1)

    def test_an_expiry_before_the_issue_date_is_refused(self):
        with self.assertRaises(ValidationError):
            services.create_certification(self.profile, {
                "name": "X", "issued_on": "2024-01-01", "expires_on": "2023-01-01",
            })

    def test_an_expired_certification_is_flagged(self):
        row = add_certification(self.profile, issued_on = "2010-01-01",
                                expires_on = "2012-01-01")
        self.assertTrue(row.is_expired)

    def test_a_certification_can_back_a_skill(self):
        certification = add_certification(self.profile, name = "AWS")
        skill = services.add_skill(self.profile, {"name": "AWS"})
        services.update_skill(skill, {"certification_id": certification.pk})

        skill.refresh_from_db()
        self.assertEqual(skill.evidence_certification_id, certification.pk)

    def test_a_certification_of_another_profile_cannot_back_a_skill(self):
        other = add_certification(make_profile("autre"), name = "Autre")
        skill = services.add_skill(self.profile, {"name": "AWS"})

        with self.assertRaises(BadRequest):
            services.update_skill(skill, {"certification_id": other.pk})


class ProjectTests(TestCase):

    def setUp(self):
        self.profile = make_profile("createur")

    def test_create_with_skills(self):
        row = services.create_project(self.profile, {
            "title": "API Rust", "description": "Une API REST.",
            "role": "Auteur", "url": "https://exemple.test/api",
            "started_on": "2024-01-01", "ended_on": "2024-06-01",
            "skills": ["Rust", "PostgreSQL"],
        })
        self.assertEqual(
            sorted(link.skill.slug for link in row.skill_links.all()),
            ["postgresql", "rust"],
        )

    def test_a_project_may_reference_one_of_my_videos(self):
        from .factories import add_video

        video = add_video(self.profile)
        row   = services.create_project(self.profile, {"title": "P", "video_id": video.pk})
        self.assertEqual(row.video_id, video.pk)

    def test_a_project_cannot_reference_someone_elses_video(self):
        from .factories import add_video

        video = add_video(make_profile("autre"))
        with self.assertRaises(BadRequest):
            services.create_project(self.profile, {"title": "P", "video_id": video.pk})

    def test_delete(self):
        row = add_project(self.profile)
        services.delete_project(row)
        self.assertEqual(self.profile.projects.count(), 0)


class LanguageTests(TestCase):

    def setUp(self):
        self.profile = make_profile("polyglotte")

    def test_declare_languages_with_cefr_levels(self):
        add_language(self.profile, "fr", c.CEFR_NATIVE)
        add_language(self.profile, "en", c.CEFR_C1)
        add_language(self.profile, "de", c.CEFR_B1)

        rows = {row.language.code: row for row in self.profile.languages.all()}
        self.assertEqual(rows["en"].level, c.CEFR_C1)
        self.assertEqual(rows["en"].level_rank, c.LANGUAGE_LEVEL_RANKS[c.CEFR_C1])
        self.assertGreater(rows["fr"].level_rank, rows["de"].level_rank)

    def test_redeclaring_a_language_updates_its_level(self):
        add_language(self.profile, "en", c.CEFR_A2)
        add_language(self.profile, "en", c.CEFR_C1)

        self.assertEqual(self.profile.languages.count(), 1)
        self.assertEqual(self.profile.languages.first().level, c.CEFR_C1)

    def test_an_unknown_language_is_refused(self):
        with self.assertRaises(BadRequest):
            services.set_language(self.profile, {"language": "klingon"})

    def test_the_reference_list_is_seeded_by_migration(self):
        from profils.profiles.models import Language

        self.assertTrue(Language.objects.filter(code = "fr").exists())
        self.assertTrue(Language.objects.filter(code = "en").exists())

    def test_remove_language(self):
        row = add_language(self.profile, "en", c.CEFR_B2)
        services.remove_language(row)
        self.assertEqual(self.profile.languages.count(), 0)
