"""Fabriques partagees par les tests."""

from django.contrib.auth.models import User

from profils.questionnaires import constants as c
from profils.questionnaires.editing    import create_question
from profils.questionnaires.models     import Badge, Questionnaire
from profils.questionnaires.versioning import create_version, publish_version

def make_user(username = "user", **kwargs) -> User:
    return User.objects.create_user(username, None, "password123", **kwargs)

def make_admin(username = "admin") -> User:
    return User.objects.create_user(username, None, "password123", is_superuser = True, is_staff = True)

def make_questionnaire(actor = None, *, title = "Questionnaire", **kwargs) -> Questionnaire:
    questionnaire = Questionnaire.objects.create(title = title, created_by = actor, **kwargs)
    create_version(questionnaire, source = None, actor = actor, title = title)
    return questionnaire

def draft_of(questionnaire):
    return questionnaire.versions.order_by("-version_number").first()

def add_single_choice(version, actor = None, *, text = "Langage prefere ?",
                      options = ("Java", "Rust", "COBOL"), correct = ("Java",), **kwargs):
    return create_question(version, {
        "type": c.TYPE_SINGLE_CHOICE,
        "text": text,
        "options": [
            {"text": label, "is_correct": label in correct}
            for label in options
        ],
        **kwargs,
    }, actor = actor)

def add_multiple_choice(version, actor = None, *, text = "Langages compiles ?",
                        options = ("Java", "Rust", "Python"), correct = ("Java", "Rust"), **kwargs):
    return create_question(version, {
        "type": c.TYPE_MULTIPLE_CHOICE,
        "text": text,
        "options": [{"text": label, "is_correct": label in correct} for label in options],
        **kwargs,
    }, actor = actor)

def add_temperature(version, actor = None, *, low = 18, high = 22, **kwargs):
    return create_question(version, {
        "type": c.TYPE_TEMPERATURE,
        "text": "Temperature de confort ?",
        "config": {"unit": "C"},
        "expected_config": {"rules": [{"type": "range", "min": low, "max": high}]},
        **kwargs,
    }, actor = actor)

def publish(questionnaire, actor = None):
    version = draft_of(questionnaire)
    publish_version(version, actor = actor)
    return version

def make_badge(code = "BASIC_COMPLETED", **kwargs) -> Badge:
    return Badge.objects.create(
        code = code, name = kwargs.pop("name", code), **kwargs
    )
