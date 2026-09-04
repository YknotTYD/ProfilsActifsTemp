
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0004_videomoderationevent_profilevideo_file_blob_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProfileVideoReaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reaction', models.CharField(choices=[('like', "J'aime"), ('dislike', "Je n'aime pas")], max_length=8)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('video', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='profiles.profilevideo')),
            ],
            options={
                'indexes': [models.Index(fields=['video', 'reaction'], name='profiles_pr_video_i_25ffd3_idx')],
                'constraints': [models.UniqueConstraint(fields=('video', 'user'), name='one_reaction_per_video_per_user')],
            },
        ),
        migrations.CreateModel(
            name='ProfileVideoView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(blank=True, default='', max_length=40)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('video', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='views', to='profiles.profilevideo')),
            ],
            options={
                'indexes': [models.Index(fields=['video', '-created_at'], name='profiles_pr_video_i_eec84a_idx')],
                'constraints': [models.UniqueConstraint(condition=models.Q(('user__isnull', False)), fields=('video', 'user'), name='one_view_per_video_per_user'), models.UniqueConstraint(condition=models.Q(('user__isnull', True), models.Q(('session_key', ''), _negated=True)), fields=('video', 'session_key'), name='one_view_per_video_per_session')],
            },
        ),
    ]
