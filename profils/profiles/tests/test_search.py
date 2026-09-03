##tests/test_search.py
"""Moteur de recherche : filtres, AND/OR, pagination, classement (sections 12 a 14)."""

from datetime import date

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from profils.profiles import constants as c
from profils.profiles import services
from profils.profiles.ranking import score_breakdown
from profils.profiles.search import ProfileQuery, search
from profils.questionnaires.http import BadRequest

from .factories import (
    add_education, add_experience, add_language, add_skill, make_admin, make_profile,
    make_user,
)


def usernames(result) -> list[str]:
    return [profile.username for profile in result["profiles"]]


class SkillMatchingTests(TestCase):

    def setUp(self):
        self.java_docker = make_profile("java-docker")
        add_skill(self.java_docker, "Java",   c.LEVEL_ADVANCED, 3)
        add_skill(self.java_docker, "Docker", c.LEVEL_INTERMEDIATE, 1)

        self.java_only = make_profile("java-only")
        add_skill(self.java_only, "Java", c.LEVEL_EXPERT, 8)

        self.rust_only = make_profile("rust-only")
        add_skill(self.rust_only, "Rust", c.LEVEL_EXPERT, 5)

    def test_one_skill(self):
        result = search(ProfileQuery.from_params({"skill": "java"}))
        self.assertEqual(sorted(usernames(result)), ["java-docker", "java-only"])

    def test_search_is_case_insensitive(self):
        for spelling in ("java", "Java", "JAVA"):
            result = search(ProfileQuery.from_params({"skill": spelling}))
            self.assertEqual(len(usernames(result)), 2, spelling)

    def test_several_skills_in_and_mode(self):
        result = search(ProfileQuery.from_params({"skills": "java,docker",
                                                  "mode": c.MATCH_MODE_AND}))
        self.assertEqual(usernames(result), ["java-docker"])

    def test_several_skills_in_or_mode(self):
        result = search(ProfileQuery.from_params({"skills": "java,rust",
                                                  "mode": c.MATCH_MODE_OR}))
        self.assertEqual(sorted(usernames(result)),
                         ["java-docker", "java-only", "rust-only"])

    def test_or_mode_returns_each_profile_once(self):
        """Une jointure OR sans `distinct` renverrait le profil une fois par competence."""
        result = search(ProfileQuery.from_params({"skills": "java,docker",
                                                  "mode": c.MATCH_MODE_OR}))
        found = usernames(result)
        self.assertEqual(len(found), len(set(found)))

    def test_and_mode_with_an_unknown_skill_returns_nothing(self):
        result = search(ProfileQuery.from_params({"skills": "java,klingon"}))
        self.assertEqual(usernames(result), [])
        self.assertEqual(result["query"]["unknown_skills"], ["klingon"])

    def test_minimum_level(self):
        result = search(ProfileQuery.from_params({"skill": "java",
                                                  "min_level": c.LEVEL_EXPERT}))
        self.assertEqual(usernames(result), ["java-only"])

    def test_minimum_level_applies_to_every_requested_skill(self):
        result = search(ProfileQuery.from_params({
            "skills": "java,docker", "min_level": c.LEVEL_ADVANCED,
        }))
        self.assertEqual(usernames(result), [])

    def test_minimum_years_on_a_skill(self):
        result = search(ProfileQuery.from_params({"skill": "java", "min_years": 5}))
        self.assertEqual(usernames(result), ["java-only"])

    def test_a_skill_with_unknown_years_does_not_satisfy_a_minimum(self):
        profile = make_profile("annees-inconnues")
        add_skill(profile, "Java", c.LEVEL_EXPERT, None)

        result = search(ProfileQuery.from_params({"skill": "java", "min_years": 1}))
        self.assertNotIn("annees-inconnues", usernames(result))


class FilterTests(TestCase):

    def setUp(self):
        self.a = make_profile(
            "a", professional_field = c.FIELD_SOFTWARE, location_city = "Nantes",
            location_country = "FR", availability_status = c.AVAILABILITY_OPEN_TO_WORK,
            contract_types = [c.CONTRACT_CDI], open_to_remote = True,
        )
        add_skill(self.a, "Java")
        add_experience(self.a, start = date(2015, 1, 1), end = date(2023, 1, 1))
        add_education(self.a, level = c.DEGREE_BAC_5, institution = "Epitech")
        add_language(self.a, "en", c.CEFR_C1)

        self.b = make_profile(
            "b", professional_field = c.FIELD_DATA, location_city = "Lyon",
            location_country = "FR", availability_status = c.AVAILABILITY_NOT_LOOKING,
            contract_types = [c.CONTRACT_FREELANCE], open_to_onsite = True,
        )
        add_skill(self.b, "Java")
        add_education(self.b, level = c.DEGREE_BAC_3, institution = "Universite")
        add_language(self.b, "en", c.CEFR_A2)

    def test_professional_field(self):
        result = search(ProfileQuery.from_params({"field": c.FIELD_DATA}))
        self.assertEqual(usernames(result), ["b"])

    def test_city_and_country(self):
        self.assertEqual(usernames(search(ProfileQuery.from_params({"city": "nantes"}))), ["a"])
        self.assertEqual(len(usernames(search(ProfileQuery.from_params({"country": "fr"})))), 2)
        self.assertEqual(usernames(search(ProfileQuery.from_params({"country": "be"}))), [])

    def test_availability(self):
        result = search(ProfileQuery.from_params({"available": "1"}))
        self.assertEqual(usernames(result), ["a"])

    def test_contract_type(self):
        self.assertEqual(usernames(search(ProfileQuery.from_params({"contract": "CDI"}))), ["a"])
        self.assertEqual(
            usernames(search(ProfileQuery.from_params({"contract": "FREELANCE"}))), ["b"]
        )

    def test_work_mode(self):
        result = search(ProfileQuery.from_params({"work_mode": c.WORK_MODE_REMOTE}))
        self.assertEqual(usernames(result), ["a"])

    def test_minimum_total_experience(self):
        result = search(ProfileQuery.from_params({"min_experience_years": 5}))
        self.assertEqual(usernames(result), ["a"])

    def test_minimum_degree_level(self):
        result = search(ProfileQuery.from_params({"min_degree_level": c.DEGREE_BAC_5}))
        self.assertEqual(usernames(result), ["a"])

        result = search(ProfileQuery.from_params({"min_degree_level": c.DEGREE_BAC_3}))
        self.assertEqual(sorted(usernames(result)), ["a", "b"])

    def test_language_with_a_minimum_level(self):
        result = search(ProfileQuery.from_params({
            "language": "en", "min_language_level": c.CEFR_B2,
        }))
        self.assertEqual(usernames(result), ["a"])

    def test_free_text_matches_name_and_headline(self):
        services.update_profile(self.a, {"headline": "Architecte logiciel"})
        result = search(ProfileQuery.from_params({"q": "architecte"}))
        self.assertEqual(usernames(result), ["a"])

    def test_filters_combine(self):
        result = search(ProfileQuery.from_params({
            "skill": "java", "field": c.FIELD_SOFTWARE,
            "contract": "CDI", "available": "1", "country": "FR",
        }))
        self.assertEqual(usernames(result), ["a"])

    def test_an_invalid_filter_value_is_refused(self):
        for params in ({"field": "ASTRONAUTE"}, {"min_level": "GODLIKE"},
                       {"contract": "ESCLAVAGE"}, {"sort": "au_hasard"}):
            with self.assertRaises(BadRequest, msg = params):
                ProfileQuery.from_params(params)


class SearchableTests(TestCase):
    """Section 28.5 : un profil non recherchable n'apparait dans aucun resultat."""

    def setUp(self):
        self.visible = make_profile("visible")
        add_skill(self.visible, "Java")

        self.hidden = make_profile("cache", searchable = False)
        add_skill(self.hidden, "Java")

    def test_a_non_searchable_profile_is_excluded(self):
        result = search(ProfileQuery.from_params({"skill": "java"}))
        self.assertEqual(usernames(result), ["visible"])

    def test_it_is_excluded_even_for_an_administrator(self):
        """Le drapeau est un choix de l'utilisateur, pas une permission."""
        result = search(ProfileQuery.from_params({"skill": "java"}), make_admin())
        self.assertEqual(usernames(result), ["visible"])

    def test_it_is_excluded_even_from_an_empty_search(self):
        result = search(ProfileQuery.from_params({}))
        self.assertNotIn("cache", usernames(result))

    def test_it_remains_directly_reachable(self):
        """Non recherchable ne veut pas dire invisible."""
        from profils.profiles.visibility import can_view_profile

        self.assertTrue(can_view_profile(make_user("passant"), self.hidden))


class SearchVisibilityTests(TestCase):

    def setUp(self):
        self.public     = make_profile("publique", visibility = c.VISIBILITY_PUBLIC)
        self.registered = make_profile("inscrits",
                                       visibility = c.VISIBILITY_REGISTERED_USERS)
        self.private    = make_profile("privee", visibility = c.VISIBILITY_PRIVATE)
        for profile in (self.public, self.registered, self.private):
            add_skill(profile, "Java")

    def test_an_anonymous_visitor_only_finds_public_profiles(self):
        result = search(ProfileQuery.from_params({"skill": "java"}), AnonymousUser())
        self.assertEqual(usernames(result), ["publique"])

    def test_a_registered_visitor_finds_public_and_registered_profiles(self):
        result = search(ProfileQuery.from_params({"skill": "java"}), make_user("passant"))
        self.assertEqual(sorted(usernames(result)), ["inscrits", "publique"])

    def test_a_private_profile_is_never_returned(self):
        for viewer in (AnonymousUser(), make_user("x"), make_admin()):
            result = search(ProfileQuery.from_params({"skill": "java"}), viewer)
            self.assertNotIn("privee", usernames(result))


class RankingTests(TestCase):
    """Section 14 : mieux couvrir, mieux maitriser et plus d'experience remonte."""

    def test_more_matching_skills_ranks_first(self):
        both = make_profile("les-deux")
        add_skill(both, "Java", c.LEVEL_INTERMEDIATE, 2)
        add_skill(both, "Docker", c.LEVEL_INTERMEDIATE, 2)

        one = make_profile("une-seule")
        add_skill(one, "Java", c.LEVEL_EXPERT, 10)

        result = search(ProfileQuery.from_params({"skills": "java,docker",
                                                  "mode": c.MATCH_MODE_OR}))
        self.assertEqual(usernames(result)[0], "les-deux")

    def test_a_higher_level_ranks_first_at_equal_coverage(self):
        expert = make_profile("expert")
        add_skill(expert, "Java", c.LEVEL_EXPERT)

        beginner = make_profile("debutant")
        add_skill(beginner, "Java", c.LEVEL_BEGINNER)

        result = search(ProfileQuery.from_params({"skill": "java"}))
        self.assertEqual(usernames(result), ["expert", "debutant"])

    def test_more_relevant_years_rank_first(self):
        senior = make_profile("senior")
        add_skill(senior, "Java", c.LEVEL_ADVANCED, 8)

        junior = make_profile("junior")
        add_skill(junior, "Java", c.LEVEL_ADVANCED, 1)

        result = search(ProfileQuery.from_params({"skill": "java"}))
        self.assertEqual(usernames(result), ["senior", "junior"])

    def test_availability_breaks_a_tie(self):
        available = make_profile("dispo", availability_status = c.AVAILABILITY_OPEN_TO_WORK)
        add_skill(available, "Java", c.LEVEL_ADVANCED, 2)

        busy = make_profile("en-poste", availability_status = c.AVAILABILITY_NOT_LOOKING)
        add_skill(busy, "Java", c.LEVEL_ADVANCED, 2)

        result = search(ProfileQuery.from_params({"skill": "java"}))
        self.assertEqual(usernames(result), ["dispo", "en-poste"])

    def test_the_field_gives_a_bonus(self):
        matching = make_profile("bon-domaine", professional_field = c.FIELD_SOFTWARE)
        add_skill(matching, "Java", c.LEVEL_ADVANCED, 2)

        other = make_profile("autre-domaine", professional_field = c.FIELD_FINANCE)
        add_skill(other, "Java", c.LEVEL_ADVANCED, 2)

        result = search(ProfileQuery.from_params({"skill": "java",
                                                  "field": c.FIELD_SOFTWARE}))
        self.assertEqual(usernames(result)[0], "bon-domaine")

    def test_the_score_is_explainable(self):
        profile = make_profile("explique", availability_status = c.AVAILABILITY_OPEN_TO_WORK)
        add_skill(profile, "Java", c.LEVEL_EXPERT, 4)

        query  = ProfileQuery.from_params({"skill": "java"})
        result = search(query)
        found  = result["profiles"][0]
        parts  = score_breakdown(found, query)

        self.assertEqual(found.matched_skill_count, 1)
        self.assertEqual(parts["skill_match"], c.RANKING_WEIGHTS["skill_match"])
        self.assertEqual(parts["total"], found.relevance)

    def test_aggregates_are_not_inflated_by_other_relations(self):
        """Une jointure sur les langues ne doit pas multiplier la somme des niveaux."""
        profile = make_profile("multi-relations")
        add_skill(profile, "Java", c.LEVEL_EXPERT, 3)
        for code in ("fr", "en", "es", "de"):
            add_language(profile, code, c.CEFR_B2)

        query  = ProfileQuery.from_params({"skill": "java", "language": "fr,en"})
        found  = search(query)["profiles"][0]

        self.assertEqual(found.matched_skill_count, 1)
        self.assertEqual(found.matched_skill_level, c.SKILL_LEVEL_RANKS[c.LEVEL_EXPERT])
        self.assertEqual(found.matched_skill_years, 3)
        self.assertEqual(found.matched_language_count, 2)

    def test_skill_years_are_capped(self):
        profile = make_profile("veteran")
        add_skill(profile, "Java", c.LEVEL_EXPERT, 40)

        found = search(ProfileQuery.from_params({"skill": "java"}))["profiles"][0]
        self.assertEqual(found.capped_skill_years, c.RANKING_CAPS["skill_years"])


class SortAndPaginationTests(TestCase):

    def setUp(self):
        for index in range(25):
            profile = make_profile(f"profil-{index:02d}")
            add_skill(profile, "Java", c.LEVEL_INTERMEDIATE, index % 5)

    def test_default_page_size(self):
        result = search(ProfileQuery.from_params({"skill": "java"}))
        self.assertEqual(len(result["profiles"]), c.DEFAULT_PAGE_SIZE)
        self.assertEqual(result["pagination"]["total"], 25)
        self.assertEqual(result["pagination"]["pages"], 2)
        self.assertTrue(result["pagination"]["has_next"])

    def test_second_page(self):
        result = search(ProfileQuery.from_params({"skill": "java", "page": 2}))
        self.assertEqual(len(result["profiles"]), 5)
        self.assertFalse(result["pagination"]["has_next"])

    def test_pages_do_not_overlap(self):
        first  = usernames(search(ProfileQuery.from_params({"skill": "java", "page": 1})))
        second = usernames(search(ProfileQuery.from_params({"skill": "java", "page": 2})))
        self.assertEqual(set(first) & set(second), set())
        self.assertEqual(len(set(first) | set(second)), 25)

    def test_page_size_is_capped(self):
        result = search(ProfileQuery.from_params({"skill": "java", "page_size": 500}))
        self.assertEqual(result["pagination"]["page_size"], c.MAX_PAGE_SIZE)

    def test_a_page_beyond_the_last_returns_the_last(self):
        result = search(ProfileQuery.from_params({"skill": "java", "page": 99}))
        self.assertEqual(result["pagination"]["page"], 2)

    def test_sort_by_experience(self):
        senior = make_profile("tres-ancien")
        add_skill(senior, "Java")
        add_experience(senior, start = date(2005, 1, 1), end = date(2024, 1, 1))

        result = search(ProfileQuery.from_params({"skill": "java",
                                                  "sort": c.SORT_EXPERIENCE}))
        self.assertEqual(usernames(result)[0], "tres-ancien")

    def test_sort_by_name(self):
        result = search(ProfileQuery.from_params({"skill": "java", "sort": c.SORT_NAME}))
        self.assertEqual(usernames(result), sorted(usernames(result)))


class QueryEfficiencyTests(TestCase):
    """Le moteur ne doit pas ramener tous les profils pour filtrer ensuite."""

    def setUp(self):
        for index in range(30):
            profile = make_profile(f"p{index:02d}")
            add_skill(profile, "Java" if index % 2 else "Rust")

    def _capture(self, query):
        """Requetes SQL emises par une recherche complete."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            result = search(query)
            list(result["profiles"])
        return result, [entry["sql"] for entry in captured.captured_queries]

    def test_the_query_count_does_not_grow_with_the_result_size(self):
        """Le cout d'une recherche doit dependre de la page, pas du nombre de profils."""
        small = ProfileQuery.from_params({"skill": "java", "page_size": 3})
        big   = ProfileQuery.from_params({"skill": "java", "page_size": 15})

        _, small_sql = self._capture(small)
        _, big_sql   = self._capture(big)
        self.assertEqual(len(small_sql), len(big_sql))

    def test_the_total_is_counted_by_the_database(self):
        result, sql = self._capture(ProfileQuery.from_params({"skill": "java"}))

        self.assertEqual(result["pagination"]["total"], 15)
        self.assertTrue(any("COUNT(*)" in statement for statement in sql))

    def test_only_one_page_is_fetched(self):
        """La page est decoupee en SQL : rien n'est ramene puis tronque en Python."""
        result, sql = self._capture(
            ProfileQuery.from_params({"skill": "java", "page_size": 5})
        )

        self.assertEqual(len(result["profiles"]), 5)
        self.assertEqual(result["pagination"]["total"], 15)
        selects = [s for s in sql if "relevance" in s]
        self.assertTrue(selects)
        self.assertTrue(all("LIMIT 5" in statement for statement in selects))

    def test_sorting_happens_in_sql(self):
        _, sql = self._capture(ProfileQuery.from_params({"skill": "java"}))
        page = next(s for s in sql if "relevance" in s)
        self.assertIn("ORDER BY", page)

    def test_serializing_a_page_of_results_does_not_reresolve_the_viewers_roles_per_row(self):
        """`search_card` recevait `viewer` seul et relancait `can_see_private` a
        chaque profil : la requete de roles (groupes Django + `mainapp.Role`)
        grossissait avec le nombre de resultats de la page au lieu de rester
        fixe. Comparer deux tailles de page plutot que fixer un nombre absolu :
        c'est la mise a l'echelle qui est le vrai defaut, pas le compte exact,
        qui depend aussi du cache interne de permissions de Django."""
        from django.db import connection
        from django.test import Client
        from django.test.utils import CaptureQueriesContext

        def role_query_count(page_size):
            client = Client()
            client.force_login(make_user(f"visiteur-{page_size}"))
            with CaptureQueriesContext(connection) as captured:
                response = client.get(f"/api/profiles/search/?skill=java&page_size={page_size}")
            self.assertEqual(response.status_code, 200)
            return len([
                entry for entry in captured.captured_queries
                if "auth_group" in entry["sql"] or "mainapp_role" in entry["sql"]
            ])

        small_page_count = role_query_count(3)
        big_page_count   = role_query_count(15)
        self.assertEqual(small_page_count, big_page_count)
