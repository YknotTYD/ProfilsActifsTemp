##tests/test_videos.py
"""Videos : structure, association aux competences, preparation du feed.

Sections 15 a 19. Le feed vertical n'est pas implemente ; ce qui est teste
ici, c'est que la structure sur laquelle il se branchera existe, qu'elle
respecte les memes regles de visibilite que le reste, et que le chemin
"recherche -> profils -> videos" fonctionne deja.
"""

import json

from django.contrib.auth.models import AnonymousUser
from django.test import Client, TestCase

from profils.profiles import constants as c
from profils.profiles import services
from profils.profiles.feed import video_candidates, videos_for_skills
from profils.profiles.models import ProfileVideo, ProfileVideoSkill, Skill
from profils.profiles.search import ProfileQuery
from profils.profiles.visibility import can_view_video, visible_videos

from .factories import add_skill, add_video, make_profile, make_user


class EmptySectionTests(TestCase):
    """Section 15 : la section existe et repond, vide, des maintenant."""

    def setUp(self):
        self.profile = make_profile("sans-video", visibility = c.VISIBILITY_PUBLIC)
        self.client  = Client()

    def test_the_endpoint_answers_with_an_empty_list(self):
        response = self.client.get(f"/api/profiles/{self.profile.username}/videos/")
        payload  = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["videos"], [])
        self.assertEqual(payload["username"], self.profile.username)

    def test_the_profile_payload_carries_an_empty_video_section(self):
        from profils.profiles import serializers

        payload = serializers.public_profile(self.profile, AnonymousUser())
        self.assertEqual(payload["videos"], [])
        self.assertTrue(payload["sections"][c.SECTION_VIDEOS])

    def test_the_page_renders_the_empty_state(self):
        response = self.client.get(f"/profile/{self.profile.username}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Videos")


class VideoModelTests(TestCase):

    def setUp(self):
        self.profile = make_profile("videaste")

    def test_create_with_metadata(self):
        video = services.create_video(self.profile, {
            "title": "Je developpe une API Rust",
            "description": "Tour du projet en 60 secondes.",
            "file_url": "https://exemple.test/v.mp4",
            "thumbnail_url": "https://exemple.test/v.jpg",
            "duration_seconds": 58,
            "status": c.VIDEO_PUBLISHED,
            "tags": ["rust", "backend"],
        })

        self.assertEqual(video.status, c.VIDEO_PUBLISHED)
        self.assertEqual(video.tags, ["rust", "backend"])
        self.assertEqual(video.duration_seconds, 58)

    def test_publication_date_follows_the_status(self):
        """La date de publication est calculee, pas fournie par le client."""
        draft = add_video(self.profile, status = c.VIDEO_DRAFT)
        self.assertIsNone(draft.published_at)

        services.update_video(draft, {"status": c.VIDEO_PUBLISHED})
        draft.refresh_from_db()
        self.assertIsNotNone(draft.published_at)

    def test_every_status_of_the_specification_exists(self):
        declared = {value for value, _ in c.VIDEO_STATUSES}
        self.assertEqual(
            declared, {"DRAFT", "PROCESSING", "PUBLISHED", "HIDDEN", "DELETED"}
        )

    def test_deletion_is_logical(self):
        """Une video citee par un projet ne doit pas disparaitre sous ses pieds."""
        video = add_video(self.profile)
        services.delete_video(video)

        video.refresh_from_db()
        self.assertEqual(video.status, c.VIDEO_DELETED)
        self.assertTrue(ProfileVideo.objects.filter(pk = video.pk).exists())

    def test_an_invalid_status_is_refused(self):
        from profils.questionnaires.http import BadRequest

        with self.assertRaises(BadRequest):
            services.create_video(self.profile, {"title": "X", "status": "EN_VRAC"})


class VideoSkillTests(TestCase):
    """Section 17 : plusieurs competences par video."""

    def setUp(self):
        self.profile = make_profile("videaste")

    def test_several_skills_can_be_attached(self):
        video = services.create_video(self.profile, {
            "title": "Je developpe une API Rust",
            "skills": ["Rust", "REST API", "PostgreSQL"],
        })

        slugs = sorted(link.skill.slug for link in video.skill_links.all())
        self.assertEqual(slugs, ["postgresql", "rest-api", "rust"])

    def test_they_use_the_shared_catalog(self):
        services.add_skill(self.profile, {"name": "Rust"})
        video = add_video(self.profile, skills = ["RUST"])

        rust = Skill.objects.get(slug = "rust")
        self.assertEqual(Skill.objects.filter(slug = "rust").count(), 1)
        self.assertEqual(video.skill_links.first().skill_id, rust.pk)

    def test_a_skill_is_not_attached_twice(self):
        video = add_video(self.profile, skills = ["Rust", "rust", "RUST"])
        self.assertEqual(ProfileVideoSkill.objects.filter(video = video).count(), 1)

    def test_update_replaces_the_association(self):
        video = add_video(self.profile, skills = ["Rust"])
        services.update_video(video, {"skills": ["Go", "gRPC"]})

        slugs = sorted(link.skill.slug for link in video.skill_links.all())
        self.assertEqual(slugs, ["go", "grpc"])


class VideoVisibilityTests(TestCase):

    def setUp(self):
        self.owner   = make_user("videaste")
        self.profile = make_profile(user = self.owner, visibility = c.VISIBILITY_PUBLIC)
        self.visitor = make_user("passant")

    def test_only_published_videos_reach_a_visitor(self):
        add_video(self.profile, title = "Publiee", status = c.VIDEO_PUBLISHED)
        add_video(self.profile, title = "Brouillon", status = c.VIDEO_DRAFT)
        add_video(self.profile, title = "Masquee", status = c.VIDEO_HIDDEN)

        titles = [v.title for v in visible_videos(self.visitor, self.profile)]
        self.assertEqual(titles, ["Publiee"])

    def test_the_owner_sees_their_drafts(self):
        add_video(self.profile, title = "Brouillon", status = c.VIDEO_DRAFT)
        titles = [v.title for v in visible_videos(self.owner, self.profile)]
        self.assertEqual(titles, ["Brouillon"])

    def test_a_deleted_video_is_shown_to_nobody(self):
        video = add_video(self.profile)
        services.delete_video(video)

        self.assertEqual(list(visible_videos(self.owner, self.profile)), [])
        self.assertEqual(list(visible_videos(self.visitor, self.profile)), [])

    def test_a_video_can_be_more_restrictive_than_its_profile(self):
        video = add_video(self.profile, visibility = c.VISIBILITY_REGISTERED_USERS)

        self.assertFalse(can_view_video(AnonymousUser(), video))
        self.assertTrue(can_view_video(self.visitor, video))

    def test_hiding_the_section_hides_every_video(self):
        add_video(self.profile)
        services.update_visibility(self.profile, {c.SECTION_VIDEOS: c.VISIBILITY_PRIVATE})
        self.profile.refresh_from_db()

        self.assertEqual(list(visible_videos(self.visitor, self.profile)), [])
        # le proprietaire, lui, garde acces a sa propre section
        self.assertEqual(visible_videos(self.owner, self.profile).count(), 1)


class FeedPreparationTests(TestCase):
    """Sections 18 et 19 : le chainon recherche -> profils -> videos existe."""

    def setUp(self):
        self.rustacean = make_profile("rustacean", visibility = c.VISIBILITY_PUBLIC)
        add_skill(self.rustacean, "Rust", c.LEVEL_EXPERT, 4)
        self.video = add_video(self.rustacean, title = "API Rust",
                               skills = ["Rust", "PostgreSQL"])

        self.javaiste = make_profile("javaiste", visibility = c.VISIBILITY_PUBLIC)
        add_skill(self.javaiste, "Java")
        add_video(self.javaiste, title = "Spring Boot", skills = ["Java"])

    def test_a_search_leads_to_the_videos_of_the_matching_profiles(self):
        query  = ProfileQuery.from_params({"skill": "rust"})
        videos = video_candidates(query)

        self.assertEqual([v.title for v in videos], ["API Rust"])

    def test_it_excludes_a_non_searchable_profile(self):
        services.update_search_settings(self.rustacean, {"searchable": False})

        query = ProfileQuery.from_params({"skill": "rust"})
        self.assertEqual(list(video_candidates(query)), [])

    def test_it_excludes_a_profile_that_opted_out_of_the_feed(self):
        services.update_search_settings(self.rustacean, {"appear_in_video_feed": False})

        query = ProfileQuery.from_params({"skill": "rust"})
        self.assertEqual(list(video_candidates(query)), [])

    def test_it_excludes_an_unpublished_video(self):
        self.video.status = c.VIDEO_DRAFT
        self.video.save()

        query = ProfileQuery.from_params({"skill": "rust"})
        self.assertEqual(list(video_candidates(query)), [])

    def test_a_skill_leads_to_the_videos_that_carry_it(self):
        """Section 19 : chercher `Rust` doit pouvoir remonter aux videos."""
        rust   = Skill.objects.get(slug = "rust")
        videos = videos_for_skills([rust.pk])
        self.assertEqual([v.title for v in videos], ["API Rust"])

    def test_a_video_skill_is_found_even_without_the_profile_skill(self):
        newcomer = make_profile("nouveau", visibility = c.VISIBILITY_PUBLIC)
        add_video(newcomer, title = "Premiers pas en Go", skills = ["Go"])

        go = Skill.objects.get(slug = "go")
        self.assertEqual([v.title for v in videos_for_skills([go.pk])],
                         ["Premiers pas en Go"])

    def test_video_candidates_is_a_queryset_not_a_list(self):
        """Le futur feed doit pouvoir paginer et ordonner en base."""
        from django.db.models import QuerySet

        query = ProfileQuery.from_params({"skill": "rust"})
        self.assertIsInstance(video_candidates(query), QuerySet)

    def test_no_feed_route_is_exposed(self):
        """Section 18 : ne pas livrer de faux feed."""
        client = Client()
        for url in ("/feed/", "/api/feed/", "/api/videos/feed/"):
            self.assertEqual(client.get(url).status_code, 404, url)


class MatchingPreparationTests(TestCase):
    """Section 26 : les donnees d'un rapprochement offre / candidat sont pretes."""

    def setUp(self):
        self.profile = make_profile(
            "candidat", professional_field = c.FIELD_SOFTWARE,
            location_country = "FR", contract_types = [c.CONTRACT_CDI],
        )
        add_skill(self.profile, "Java", c.LEVEL_ADVANCED, 3)
        add_skill(self.profile, "Docker", c.LEVEL_INTERMEDIATE, 1)

    def test_profile_features_expose_the_comparable_data(self):
        from profils.profiles.matching import profile_features

        features = profile_features(self.profile)

        self.assertEqual(features["skills"]["java"]["level"], c.LEVEL_ADVANCED)
        self.assertEqual(features["skills"]["java"]["years"], 3)
        self.assertEqual(features["field"], c.FIELD_SOFTWARE)
        self.assertEqual(features["contract_types"], [c.CONTRACT_CDI])
        self.assertTrue(features["is_available"])

    def test_an_offer_translates_into_a_search_query(self):
        from profils.profiles.matching import query_from_offer
        from profils.profiles.search import search

        query = query_from_offer({
            "skills": ["Java", "Docker"], "min_level": c.LEVEL_INTERMEDIATE,
            "contract": c.CONTRACT_CDI, "field": c.FIELD_SOFTWARE, "country": "FR",
        })
        result = search(query)

        self.assertEqual([p.username for p in result["profiles"]], ["candidat"])

    def test_an_offer_asking_too_much_finds_nobody(self):
        from profils.profiles.matching import query_from_offer
        from profils.profiles.search import search

        query = query_from_offer({
            "skills": ["Java", "Docker"], "min_level": c.LEVEL_EXPERT,
        })
        self.assertEqual(list(search(query)["profiles"]), [])
