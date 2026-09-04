
from django.conf import settings
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0007_rename_video_videobylink_alter_role_user'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name='VideoByLink',
            new_name='VideoLink',
        ),
    ]
