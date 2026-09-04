"""Archive les refus de moderation sortis de la fenetre vivante.

    python manage.py archive_moderation_history

A brancher sur une tache planifiee (cron, `crontab` du conteneur...). La
console de moderation archive aussi paresseusement a chaque lecture : cette
commande n'est donc pas indispensable au bon affichage, elle sert a garder la
table propre sans dependre d'un passage d'administrateur.

Fenetre : `settings.REJECTION_HISTORY_DAYS` (7 par defaut).
"""

from django.core.management.base import BaseCommand

from profils.profiles import constants as c
from profils.profiles.moderation import archive_stale_rejections

class Command(BaseCommand):
    help = "Archive les refus de moderation de plus de REJECTION_HISTORY_DAYS jours."

    def handle(self, *args, **options):
        moved = archive_stale_rejections()
        self.stdout.write(self.style.SUCCESS(
            f"{moved} refus archive(s) (fenetre : {c.rejection_history_days()} jours)."
        ))
