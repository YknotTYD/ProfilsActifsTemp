import json

from django.contrib.auth.models import User
from django.test import Client, TestCase

from profils.notifications import types as notification_types
from profils.notifications.models import Notification

from .models import VideoLink


class ReactionNotificationTests(TestCase):
    """Section 5 : "like recu", "dislike recu"."""

    def setUp(self):
        self.owner = User.objects.create_user("proprietaire", None, None)
        self.reactor = User.objects.create_user("reacteur", None, None)
        self.video = VideoLink.objects.create(user = self.owner, url = "https://exemple.test/v.mp4")
        self.client = Client()
        self.client.force_login(self.reactor)

    def _react(self, reaction):
        return self.client.post(
            "/api/react/", data = json.dumps({"video_id": self.video.id, "reaction": reaction}),
            content_type = "application/json",
        )

    def test_a_like_notifies_the_owner(self):
        self._react("like")
        notif = Notification.objects.get(recipient = self.owner)
        self.assertEqual(notif.type, notification_types.VIDEO_LIKED)

    def test_a_dislike_notifies_the_owner(self):
        self._react("dislike")
        notif = Notification.objects.get(recipient = self.owner)
        self.assertEqual(notif.type, notification_types.VIDEO_DISLIKED)

    def test_removing_a_reaction_does_not_notify_again(self):
        self._react("like")
        self._react("like")  # meme reaction : la retire
        self.assertEqual(Notification.objects.filter(recipient = self.owner).count(), 1)

    def test_reacting_to_ones_own_video_does_not_notify(self):
        self.client.force_login(self.owner)
        self._react("like")
        self.assertFalse(Notification.objects.filter(recipient = self.owner).exists())
