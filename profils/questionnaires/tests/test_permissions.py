##tests/test_permissions.py

from django.contrib.auth.models import Permission, User
from django.test import TestCase

from profils.mainapp.models import Role
from profils.questionnaires import constants as c
from profils.questionnaires.access      import AccessDenied, can_see, evaluate_rules
from profils.questionnaires.editing     import set_access_rules
from profils.questionnaires.models      import UserBadge
from profils.questionnaires.permissions import has_perm, is_questionnaire_admin, user_roles
from profils.questionnaires.services    import start_attempt

from .factories import (
    add_single_choice, draft_of, make_admin, make_badge, make_questionnaire, make_user, publish,
)


class RoleBridgeTests(TestCase):
    """Le systeme reutilise le modele `Role` deja present dans mainapp."""

    def test_roles_come_from_mainapp_groups_and_flags(self):
        user = make_user("recruteur")
        Role.objects.create(user = user, role = "Recruiter")
        self.assertEqual(user_roles(user), {"recruiter"})

        admin = make_user("chef")
        Role.objects.create(user = admin, role = "Admin")
        self.assertIn("admin", user_roles(admin))
        self.assertTrue(is_questionnaire_admin(admin))

    def test_superuser_is_always_a_questionnaire_admin(self):
        self.assertTrue(is_questionnaire_admin(make_admin()))

    def test_plain_user_has_no_admin_permission(self):
        user = make_user("simple")
        self.assertFalse(is_questionnaire_admin(user))
        for perm in (c.PERM_CREATE, c.PERM_PUBLISH, c.PERM_INVALIDATE, c.PERM_VIEW_RESULTS):
            self.assertFalse(has_perm(user, perm), perm)

    def test_django_permission_grants_the_right(self):
        user = make_user("editeur")
        user.user_permissions.add(
            Permission.objects.get(codename = "publish_questionnaire"))
        user = User.objects.get(pk = user.pk)   # vide le cache de permissions

        self.assertTrue(has_perm(user, c.PERM_PUBLISH))
        self.assertFalse(has_perm(user, c.PERM_INVALIDATE))

    def test_anonymous_has_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(user_roles(AnonymousUser()), set())
        self.assertFalse(has_perm(AnonymousUser(), c.PERM_VIEW))


class AccessRuleTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.q     = make_questionnaire(self.admin)
        add_single_choice(draft_of(self.q), self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()

    def test_everyone_by_default(self):
        user = make_user("quelconque")
        self.assertTrue(evaluate_rules(self.q, user, c.RULE_KIND_ACCESS))
        self.assertTrue(can_see(self.q, user))

    def test_specific_user_rule(self):
        allowed = make_user("elu")
        other   = make_user("autre")
        set_access_rules(self.q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_USER, "user_id": allowed.id}]], actor = self.admin)

        self.assertTrue(evaluate_rules(self.q, allowed, c.RULE_KIND_ACCESS))
        self.assertFalse(evaluate_rules(self.q, other, c.RULE_KIND_ACCESS))

        with self.assertRaises(AccessDenied) as ctx:
            start_attempt(self.q, other)
        self.assertEqual(ctx.exception.code, "rules_denied")

    def test_role_rule(self):
        recruiter = make_user("recruteur")
        Role.objects.create(user = recruiter, role = "Recruiter")
        seeker = make_user("candidat")
        Role.objects.create(user = seeker, role = "JobSeeker")

        set_access_rules(self.q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_ROLE, "role": "Recruiter"}]], actor = self.admin)

        self.assertTrue(evaluate_rules(self.q, recruiter, c.RULE_KIND_ACCESS))
        self.assertFalse(evaluate_rules(self.q, seeker, c.RULE_KIND_ACCESS))

    def test_badge_rule(self):
        badge  = make_badge("BASIC_COMPLETED")
        holder = make_user("titulaire")
        UserBadge.objects.create(user = holder, badge = badge)
        other  = make_user("sans_badge")

        set_access_rules(self.q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_BADGE, "badge_code": badge.code}]], actor = self.admin)

        self.assertTrue(evaluate_rules(self.q, holder, c.RULE_KIND_ACCESS))
        self.assertFalse(evaluate_rules(self.q, other, c.RULE_KIND_ACCESS))

    def test_and_combination_within_a_group(self):
        badge = make_badge("BASIC_COMPLETED")

        full = make_user("premium_avec_badge")
        Role.objects.create(user = full, role = "Premium")
        UserBadge.objects.create(user = full, badge = badge)

        role_only = make_user("premium_sans_badge")
        Role.objects.create(user = role_only, role = "Premium")

        badge_only = make_user("badge_sans_role")
        UserBadge.objects.create(user = badge_only, badge = badge)

        set_access_rules(self.q, c.RULE_KIND_ACCESS, [[
            {"rule_type": c.RULE_ROLE,  "role": "Premium"},
            {"rule_type": c.RULE_BADGE, "badge_code": badge.code},
        ]], actor = self.admin)

        self.assertTrue(evaluate_rules(self.q, full, c.RULE_KIND_ACCESS))
        self.assertFalse(evaluate_rules(self.q, role_only, c.RULE_KIND_ACCESS))
        self.assertFalse(evaluate_rules(self.q, badge_only, c.RULE_KIND_ACCESS))

    def test_or_combination_between_groups(self):
        premium = make_user("premium")
        Role.objects.create(user = premium, role = "Premium")
        moderator = make_user("moderateur")
        Role.objects.create(user = moderator, role = "Moderator")
        nobody = make_user("personne")

        set_access_rules(self.q, c.RULE_KIND_ACCESS, [
            [{"rule_type": c.RULE_ROLE, "role": "Premium"}],
            [{"rule_type": c.RULE_ROLE, "role": "Moderator"}],
        ], actor = self.admin)

        self.assertTrue(evaluate_rules(self.q, premium, c.RULE_KIND_ACCESS))
        self.assertTrue(evaluate_rules(self.q, moderator, c.RULE_KIND_ACCESS))
        self.assertFalse(evaluate_rules(self.q, nobody, c.RULE_KIND_ACCESS))

    def test_negated_rule(self):
        banned = make_user("banni")
        other  = make_user("normal")
        set_access_rules(self.q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_USER, "user_id": banned.id, "negate": True}]],
                         actor = self.admin)

        self.assertFalse(evaluate_rules(self.q, banned, c.RULE_KIND_ACCESS))
        self.assertTrue(evaluate_rules(self.q, other, c.RULE_KIND_ACCESS))

    def test_visibility_is_independent_from_accessibility(self):
        seer = make_user("voit")
        Role.objects.create(user = seer, role = "Member")

        set_access_rules(self.q, c.RULE_KIND_VISIBILITY,
                         [[{"rule_type": c.RULE_ROLE, "role": "Member"}]], actor = self.admin)
        set_access_rules(self.q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_ROLE, "role": "Premium"}]], actor = self.admin)

        self.assertTrue(can_see(self.q, seer))
        with self.assertRaises(AccessDenied):
            start_attempt(self.q, seer)

    def test_visibility_falls_back_on_accessibility(self):
        premium = make_user("premium")
        Role.objects.create(user = premium, role = "Premium")
        other = make_user("autre")

        set_access_rules(self.q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_ROLE, "role": "Premium"}]], actor = self.admin)

        self.assertTrue(can_see(self.q, premium))
        self.assertFalse(can_see(self.q, other))

    def test_admin_sees_everything(self):
        set_access_rules(self.q, c.RULE_KIND_ACCESS,
                         [[{"rule_type": c.RULE_ROLE, "role": "Inexistant"}]], actor = self.admin)
        self.assertTrue(can_see(self.q, self.admin))

    def test_draft_is_hidden_from_regular_users(self):
        draft = make_questionnaire(self.admin, title = "Brouillon")
        self.assertFalse(can_see(draft, make_user("curieux")))


class StatusGateTests(TestCase):

    def setUp(self):
        self.admin = make_admin()
        self.user  = make_user("candidat")
        self.q     = make_questionnaire(self.admin)
        add_single_choice(draft_of(self.q), self.admin)
        publish(self.q, self.admin)
        self.q.refresh_from_db()

    def assert_denied(self, code):
        with self.assertRaises(AccessDenied) as ctx:
            start_attempt(self.q, self.user)
        self.assertEqual(ctx.exception.code, code)

    def test_disabled(self):
        self.q.status = c.STATUS_DISABLED
        self.q.save()
        self.assert_denied("questionnaire_disabled")

    def test_archived(self):
        self.q.status = c.STATUS_ARCHIVED
        self.q.save()
        self.assert_denied("questionnaire_archived")

    def test_invalidated(self):
        self.q.status = c.STATUS_INVALIDATED
        self.q.save()
        self.assert_denied("questionnaire_invalidated")

    def test_draft(self):
        self.q.status = c.STATUS_DRAFT
        self.q.save()
        self.assert_denied("questionnaire_not_published")
