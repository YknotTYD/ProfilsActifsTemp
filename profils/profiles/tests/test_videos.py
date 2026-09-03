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
from profils.profiles import moderation, services
from profils.profiles.feed import video_candidates, videos_for_skills
from profils.profiles.http import BadRequest
from profils.profiles.models import (
    ProfileVideo, ProfileVideoSkill, Skill, VideoModerationEvent,
)
from profils.profiles.permissions import ProfileAccessDenied
from profils.profiles.search import ProfileQuery
from profils.profiles.visibility import can_view_video, visible_videos

from .factories import add_skill, add_video, make_admin, make_profile, make_user


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
        """La date de publication est calculee, pas fournie par le client.

        `update_video` ne touche plus au statut depuis l'introduction de la
        moderation (voir `ModerationPipelineTests`) : ce test verifie
        directement la regle du modele, `ProfileVideo.save()`.
        """
        draft = add_video(self.profile, status = c.VIDEO_DRAFT)
        self.assertIsNone(draft.published_at)

        draft.status = c.VIDEO_PUBLISHED
        draft.save()
        draft.refresh_from_db()
        self.assertIsNotNone(draft.published_at)

    def test_every_status_of_the_specification_exists(self):
        declared = {value for value, _ in c.VIDEO_STATUSES}
        self.assertEqual(
            declared,
            {"DRAFT", "PROCESSING", "PENDING", "APPROVED", "PUBLISHED",
             "REJECTED", "HIDDEN", "DELETED"},
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


class ModerationPipelineTests(TestCase):
    """Sections 1, 2 et "Historique de moderation".

    Une video n'est jamais publique avant validation admin ; une validation
    ne publie jamais toute seule ; un refus exige un motif, visible du seul
    proprietaire ; chaque transition est historisee.
    """

    def setUp(self):
        self.profile = make_profile("videaste")
        self.owner   = self.profile.user
        self.admin   = make_admin()
        self.other   = make_user("un-autre")

    def test_a_link_submission_enters_the_moderation_queue(self):
        video = services.submit_video_link(self.profile, {
            "title": "Ma presentation", "file_url": "https://exemple.test/v.mp4",
        })
        self.assertEqual(video.status, c.VIDEO_PENDING)
        self.assertTrue(video.is_presentation)
        self.assertFalse(video.is_published)

    def test_an_unknown_transition_is_refused(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        with self.assertRaises(BadRequest):
            moderation.transition_video(video, c.VIDEO_PUBLISHED, actor = c.ACTOR_OWNER)

    def test_approval_never_publishes_by_itself(self):
        """Critere d'acceptation : une validation admin ne publie jamais seule."""
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        services.approve_video(video, user = self.admin)

        video.refresh_from_db()
        self.assertEqual(video.status, c.VIDEO_APPROVED)
        self.assertFalse(video.is_published)
        self.assertEqual(video.requires_user_action, "CONFIRM_PUBLICATION")

    def test_only_the_owner_can_confirm_publication(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        services.approve_video(video, user = self.admin)

        with self.assertRaises(ProfileAccessDenied):
            moderation.transition_video(video, c.VIDEO_PUBLISHED, actor = c.ACTOR_ADMIN)

    def test_the_owner_confirmation_publishes_it(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        services.approve_video(video, user = self.admin)
        services.publish_presentation_video(video, user = self.owner)

        video.refresh_from_db()
        self.assertEqual(video.status, c.VIDEO_PUBLISHED)
        self.assertTrue(video.is_published)

    def test_rejection_requires_a_reason(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        with self.assertRaises(BadRequest):
            services.reject_video(video, "", user = self.admin)

    def test_a_rejected_video_shows_its_reason_to_the_owner_only(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        services.reject_video(video, "contenu hors sujet", user = self.admin)

        video.refresh_from_db()
        self.assertEqual(video.status, c.VIDEO_REJECTED)
        self.assertEqual(video.rejection_reason, "contenu hors sujet")
        # ce que le visiteur voit est verifie a la serialisation (section 6
        # pour les reactions, meme principe pour le motif de refus) : ici, on
        # verifie seulement que le champ existe pour le proprietaire.

    def test_a_rejected_video_can_be_resubmitted(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        services.reject_video(video, "format non conforme", user = self.admin)
        services.resubmit_video(video, user = self.owner)

        video.refresh_from_db()
        self.assertEqual(video.status, c.VIDEO_PENDING)
        self.assertEqual(video.rejection_reason, "", "le motif ne doit pas survivre a la sortie de REJECTED")

    def test_a_non_admin_cannot_approve(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        with self.assertRaises(ProfileAccessDenied):
            moderation.transition_video(video, c.VIDEO_APPROVED, actor = c.ACTOR_OWNER)

    def test_the_owner_or_an_admin_can_delete_it(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        services.delete_video(video, actor = c.ACTOR_ADMIN, user = self.admin)

        video.refresh_from_db()
        self.assertEqual(video.status, c.VIDEO_DELETED)

    def test_every_transition_is_historized(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        services.approve_video(video, user = self.admin)
        services.publish_presentation_video(video, user = self.owner)

        events = list(VideoModerationEvent.objects.filter(video = video).order_by("created_at"))
        self.assertEqual(
            [(e.old_status, e.new_status, e.source) for e in events],
            [
                (c.VIDEO_PENDING,  c.VIDEO_APPROVED,  c.ACTOR_ADMIN),
                (c.VIDEO_APPROVED, c.VIDEO_PUBLISHED, c.ACTOR_OWNER),
            ],
        )
        self.assertEqual(events[0].actor, self.admin)

    def test_publishing_over_the_url_of_a_live_video_forces_re_moderation(self):
        video = services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        services.approve_video(video, user = self.admin)
        services.publish_presentation_video(video, user = self.owner)

        services.replace_video_link(video, "https://exemple.test/v2.mp4", user = self.owner)

        video.refresh_from_db()
        self.assertEqual(video.status, c.VIDEO_PENDING)
        self.assertFalse(video.is_published)


class PresentationReplacementTests(TestCase):
    """Section 2 : remplacement d'une video de presentation deja publiee."""

    def setUp(self):
        self.profile = make_profile("videaste")
        self.owner   = self.profile.user
        self.admin   = make_admin()

        self.old = services.submit_video_link(self.profile, {
            "title": "Ancienne presentation", "file_url": "https://exemple.test/old.mp4",
        })
        services.approve_video(self.old, user = self.admin)
        services.publish_presentation_video(self.old, user = self.owner)

    def test_the_old_video_stays_online_through_moderation(self):
        new = services.submit_video_link(self.profile, {
            "title": "Nouvelle presentation", "file_url": "https://exemple.test/new.mp4",
            "replaces": self.old.pk,
        })
        self.old.refresh_from_db()
        self.assertTrue(self.old.is_published)
        self.assertEqual(new.status, c.VIDEO_PENDING)

    def test_the_old_video_stays_online_after_rejection(self):
        new = services.submit_video_link(self.profile, {
            "title": "Nouvelle presentation", "file_url": "https://exemple.test/new.mp4",
            "replaces": self.old.pk,
        })
        services.reject_video(new, "qualite insuffisante", user = self.admin)

        self.old.refresh_from_db()
        self.assertTrue(self.old.is_published)

    def test_the_old_video_stays_online_after_approval_until_confirmed(self):
        new = services.submit_video_link(self.profile, {
            "title": "Nouvelle presentation", "file_url": "https://exemple.test/new.mp4",
            "replaces": self.old.pk,
        })
        services.approve_video(new, user = self.admin)

        self.old.refresh_from_db()
        self.assertTrue(self.old.is_published)
        self.assertFalse(new.is_published)

    def test_confirmation_swaps_them_atomically(self):
        new = services.submit_video_link(self.profile, {
            "title": "Nouvelle presentation", "file_url": "https://exemple.test/new.mp4",
            "replaces": self.old.pk,
        })
        services.approve_video(new, user = self.admin)
        services.publish_presentation_video(new, user = self.owner)

        self.old.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual(self.old.status, c.VIDEO_HIDDEN)
        self.assertEqual(new.status, c.VIDEO_PUBLISHED)
        self.assertTrue(new.is_published)

    def test_only_one_published_presentation_can_exist_at_the_database_level(self):
        """La garantie tient a l'index, pas au service : on le verifie directement."""
        second = ProfileVideo(
            profile = self.profile, title = "Doublon", is_presentation = True,
            status = c.VIDEO_PUBLISHED, source_type = c.VIDEO_SOURCE_LINK,
            file_url = "https://exemple.test/doublon.mp4",
        )
        with self.assertRaises(Exception):
            second.save()
