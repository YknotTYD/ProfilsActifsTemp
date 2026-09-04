##tests/test_notifications.py
"""Centre de notifications (spec section 5).

Lues / non lues, compteur, acces rapide, et le fait que le pipeline de
moderation video en emet vraiment aux bons moments -- ce n'est pas un
systeme a part, il n'a de valeur que branche.
"""

from django.test import Client, TestCase

from profils.profiles import services as profile_services
from profils.profiles.tests.factories import make_admin, make_profile, make_user

from .. import services, types
from ..models import Notification


class NotifyTests(TestCase):

    def setUp(self):
        self.user = make_user("destinataire")

    def test_notify_creates_an_unread_notification(self):
        services.notify(self.user, types.VIDEO_APPROVED, title = "Ma video")
        notif = Notification.objects.get(recipient = self.user)
        self.assertEqual(notif.type, types.VIDEO_APPROVED)
        self.assertFalse(notif.is_read)
        self.assertEqual(notif.payload, {"title": "Ma video"})

    def test_an_unknown_type_is_refused(self):
        with self.assertRaises(ValueError):
            services.notify(self.user, "TYPE_INCONNU")

    def test_a_target_is_recorded_generically(self):
        profile = make_profile("cible")
        services.notify(self.user, types.NEW_MESSAGE, target = profile)
        notif = Notification.objects.get(recipient = self.user)
        self.assertEqual(notif.target, profile)

    def test_unread_count(self):
        services.notify(self.user, types.VIDEO_APPROVED)
        services.notify(self.user, types.VIDEO_REJECTED)
        self.assertEqual(services.unread_count(self.user), 2)

    def test_mark_read_updates_the_count(self):
        n = services.notify(self.user, types.VIDEO_APPROVED)
        services.mark_read(n)
        self.assertEqual(services.unread_count(self.user), 0)

    def test_mark_all_read(self):
        services.notify(self.user, types.VIDEO_APPROVED)
        services.notify(self.user, types.VIDEO_REJECTED)
        services.mark_all_read(self.user)
        self.assertEqual(services.unread_count(self.user), 0)

    def test_a_read_notification_is_not_marked_again(self):
        """Marquer une notification deja lue ne doit pas rafraichir sa date."""
        n = services.notify(self.user, types.VIDEO_APPROVED)
        services.mark_read(n)
        first_read_at = n.read_at
        services.mark_read(n)
        self.assertEqual(n.read_at, first_read_at)


class NotificationApiTests(TestCase):

    def setUp(self):
        self.user = make_user("destinataire")
        self.client = Client()
        self.client.force_login(self.user)

    def test_requires_authentication(self):
        response = Client().get("/api/notifications/")
        self.assertEqual(response.status_code, 401)

    def test_lists_only_my_notifications(self):
        other = make_user("un-autre")
        services.notify(self.user, types.VIDEO_APPROVED)
        services.notify(other, types.VIDEO_APPROVED)

        payload = self.client.get("/api/notifications/").json()
        self.assertEqual(len(payload["notifications"]), 1)
        self.assertEqual(payload["unread_count"], 1)

    def test_mark_read_via_api(self):
        n = services.notify(self.user, types.VIDEO_APPROVED)
        response = self.client.post(f"/api/notifications/{n.id}/read/")
        self.assertEqual(response.status_code, 200)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_cannot_mark_someone_elses_notification_as_read(self):
        other = make_user("un-autre")
        n = services.notify(other, types.VIDEO_APPROVED)
        response = self.client.post(f"/api/notifications/{n.id}/read/")
        self.assertEqual(response.status_code, 404)
        n.refresh_from_db()
        self.assertFalse(n.is_read)

    def test_mark_all_read_via_api(self):
        services.notify(self.user, types.VIDEO_APPROVED)
        services.notify(self.user, types.VIDEO_REJECTED)
        self.client.post("/api/notifications/read-all/")
        self.assertEqual(self.client.get("/api/notifications/unread-count/").json()["count"], 0)


class VideoModerationNotificationTests(TestCase):
    """Le pipeline de moderation video emet vraiment ces notifications."""

    def setUp(self):
        self.profile = make_profile("videaste")
        self.owner = self.profile.user
        self.admin = make_admin()

    def test_approval_notifies_the_owner(self):
        video = profile_services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        profile_services.approve_video(video, user = self.admin)

        notif = Notification.objects.get(recipient = self.owner)
        self.assertEqual(notif.type, types.VIDEO_APPROVED)
        self.assertEqual(notif.target_id, video.pk)
        # section 5 : le lien mene la ou le proprietaire agit sur sa video,
        # pas sur sa page publique.
        self.assertEqual(notif.url, "/profiles/me/video/")

    def test_rejection_notifies_the_owner_with_the_reason(self):
        video = profile_services.submit_video_link(self.profile, {
            "title": "V", "file_url": "https://exemple.test/v.mp4",
        })
        profile_services.reject_video(video, "format non conforme", user = self.admin)

        notif = Notification.objects.get(recipient = self.owner, type = types.VIDEO_REJECTED)
        self.assertEqual(notif.payload["reason"], "format non conforme")

    def test_being_replaced_notifies_the_owner(self):
        old = profile_services.submit_video_link(self.profile, {
            "title": "Ancienne", "file_url": "https://exemple.test/old.mp4",
        })
        profile_services.approve_video(old, user = self.admin)
        profile_services.publish_presentation_video(old, user = self.owner)

        new = profile_services.submit_video_link(self.profile, {
            "title": "Nouvelle", "file_url": "https://exemple.test/new.mp4",
            "replaces": old.pk,
        })
        profile_services.approve_video(new, user = self.admin)
        profile_services.publish_presentation_video(new, user = self.owner)

        self.assertTrue(
            Notification.objects.filter(recipient = self.owner, type = types.VIDEO_HIDDEN).exists()
        )
