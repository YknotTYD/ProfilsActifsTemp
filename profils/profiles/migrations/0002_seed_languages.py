"""Charge le referentiel de langues.

Les langues sont une donnee de reference, pas une donnee utilisateur : elles
sont posees par migration pour que le selecteur de langues soit utilisable des
la premiere installation. La table reste ouverte a d'autres ajouts.
"""

from django.db import migrations

from profils.profiles.constants import SEED_LANGUAGES

def seed(apps, schema_editor):
    Language = apps.get_model("profiles", "Language")
    Language.objects.bulk_create(
        [Language(code = code, name = name) for code, name in SEED_LANGUAGES],
        ignore_conflicts = True,
    )

def unseed(apps, schema_editor):
    Language = apps.get_model("profiles", "Language")
    Language.objects.filter(
        code__in = [code for code, _ in SEED_LANGUAGES], speakers__isnull = True,
    ).delete()

class Migration(migrations.Migration):

    dependencies = (("profiles", "0001_initial"),)

    operations = (migrations.RunPython(seed, unseed),)
