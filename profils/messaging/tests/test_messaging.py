##tests/test_messaging.py
"""Messagerie recruteur -> candidat (spec section 4).

Seuls les recruteurs peuvent demarrer une conversation, et seulement avec un
candidat ayant publie une video ; les deux participants peuvent ensuite s'y
repondre librement, et personne d'autre ne peut ni la lire ni y ecrire.
"""

from django.contrib.auth.models import Group
from django.test import Client, TestCase

from profils.notifications import types as notification_types
from profils.notifications.models import Notification
from profils.profiles import constants as c
from profils.profiles import services as profile_services
from profils.profiles.tests.factories import add_video, make_profile, make_user

from .. import rules, services
from ..http import BadRequest, MessagingAccessDenied
from ..models import Conversation, Message


def make_recruiter(username = "recruteur"):
    user = make_user(username)
    Group.objects.get_or_create(name = "recruiter")[0].user_set.add(user)
    return user


class RulesTests(TestCase):

    def setUp(self):
        self.candidate = make_profile("candidat").user

    def test_a_recruiter_can_contact_a_candidate_with_a_published_video(self):
        recruiter = make_recruiter()
        profile = profile_services.get_profile(self.candidate)
        add_video(profile, status = c.VIDEO_PUBLISHED)

        self.assertTrue(rules.can_start(recruiter, self.candidate))

    def test_a_recruiter_cannot_contact_a_candidate_without_a_video(self):
        recruiter = make_recruiter()
        self.assertFalse(rules.can_start(recruiter, self.candidate))

    def test_a_non_recruiter_cannot_initiate_contact(self):
        profile = profile_services.get_profile(self.candidate)
        add_video(profile, status = c.VIDEO_PUBLISHED)

        other_candidate = make_user("autre-candidat")
        self.assertFalse(rules.can_start(other_candidate, self.candidate))

    def test_nobody_can_contact_themselves(self):
        recruiter = make_recruiter()
        self.assertFalse(rules.can_start(recruiter, recruiter))

    def test_an_anonymous_visitor_cannot_initiate_contact(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(rules.can_start(AnonymousUser(), self.candidate))


class StartConversationTests(TestCase):

    def setUp(self):
        self.candidate_user = make_profile("candidat").user
        profile = profile_services.get_profile(self.candidate_user)
        add_video(profile, status = c.VIDEO_PUBLISHED)
        self.recruiter = make_recruiter()

    def test_a_recruiter_can_start_a_conversation(self):
        conv = services.start_conversation(self.recruiter, self.candidate_user)
        self.assertEqual(conv.initiator_id, self.recruiter.id)
        self.assertEqual(conv.recipient_id, self.candidate_user.id)

    def test_starting_twice_returns_the_same_conversation(self):
        first  = services.start_conversation(self.recruiter, self.candidate_user)
        second = services.start_conversation(self.recruiter, self.candidate_user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_a_non_recruiter_cannot_start_one(self):
        other = make_user("un-autre")
        with self.assertRaises(MessagingAccessDenied):
            services.start_conversation(other, self.candidate_user)

    def test_cannot_start_a_conversation_with_oneself(self):
        with self.assertRaises(BadRequest):
            services.start_conversation(self.recruiter, self.recruiter)

    def test_a_video_can_be_recorded_as_the_context(self):
        profile = profile_services.get_profile(self.candidate_user)
        video = add_video(profile, status = c.VIDEO_PUBLISHED)
        conv = services.start_conversation(self.recruiter, self.candidate_user, context = video)
        self.assertEqual(conv.context, video)


class SendMessageTests(TestCase):

    def setUp(self):
        self.candidate_user = make_profile("candidat").user
        profile = profile_services.get_profile(self.candidate_user)
        add_video(profile, status = c.VIDEO_PUBLISHED)
        self.recruiter = make_recruiter()
        self.conversation = services.start_conversation(self.recruiter, self.candidate_user)

    def test_either_participant_can_reply(self):
        services.send_message(self.conversation, self.recruiter, "Bonjour !")
        services.send_message(self.conversation, self.candidate_user, "Bonjour, merci de votre message.")
        self.assertEqual(Message.objects.filter(conversation = self.conversation).count(), 2)

    def test_a_third_party_cannot_write_into_it(self):
        stranger = make_user("etranger")
        with self.assertRaises(MessagingAccessDenied):
            services.send_message(self.conversation, stranger, "Salut")

    def test_an_empty_message_is_refused(self):
        with self.assertRaises(BadRequest):
            services.send_message(self.conversation, self.recruiter, "   ")

    def test_sending_notifies_the_other_participant(self):
        services.send_message(self.conversation, self.recruiter, "Bonjour !")
        notif = Notification.objects.get(recipient = self.candidate_user)
        self.assertEqual(notif.type, notification_types.NEW_MESSAGE)
        self.assertEqual(notif.payload["sender"], self.recruiter.username)


class MessagingPagesTests(TestCase):

    def setUp(self):
        self.candidate_user = make_profile("candidat").user
        profile = profile_services.get_profile(self.candidate_user)
        add_video(profile, status = c.VIDEO_PUBLISHED)
        self.recruiter = make_recruiter()

    def test_conversations_page_requires_login(self):
        self.assertEqual(Client().get("/messages/").status_code, 302)

    def test_starting_from_the_profile_page_redirects_to_the_thread(self):
        client = Client()
        client.force_login(self.recruiter)
        response = client.post("/messages/start/", {"recipient": self.candidate_user.username})
        conv = Conversation.objects.get()
        self.assertRedirects(response, f"/messages/{conv.pk}/")

    def test_a_stranger_gets_404_on_someone_elses_thread(self):
        conv = services.start_conversation(self.recruiter, self.candidate_user)
        stranger = make_user("etranger")
        client = Client()
        client.force_login(stranger)
        self.assertEqual(client.get(f"/messages/{conv.pk}/").status_code, 404)

    def test_the_profile_page_shows_the_contact_button_to_an_eligible_recruiter(self):
        client = Client()
        client.force_login(self.recruiter)
        response = client.get(f"/profile/{self.candidate_user.username}/")
        self.assertContains(response, "Contacter ce candidat")

    def test_the_profile_page_hides_the_contact_button_from_a_non_recruiter(self):
        visitor = make_user("visiteur")
        client = Client()
        client.force_login(visitor)
        response = client.get(f"/profile/{self.candidate_user.username}/")
        self.assertNotContains(response, "Contacter ce candidat")
