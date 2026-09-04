
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0003_professionalprofile_cover_color'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VideoModerationEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(choices=[('OWNER', 'Proprietaire'), ('ADMIN', 'Administrateur'), ('SYSTEM', 'Systeme')], max_length=8)),
                ('old_status', models.CharField(blank=True, choices=[('DRAFT', 'Brouillon'), ('PROCESSING', 'En traitement'), ('PENDING', 'En attente de moderation'), ('APPROVED', 'Validee'), ('PUBLISHED', 'Publiee'), ('REJECTED', 'Refusee'), ('HIDDEN', 'Masquee'), ('DELETED', 'Supprimee')], default='', max_length=16)),
                ('new_status', models.CharField(choices=[('DRAFT', 'Brouillon'), ('PROCESSING', 'En traitement'), ('PENDING', 'En attente de moderation'), ('APPROVED', 'Validee'), ('PUBLISHED', 'Publiee'), ('REJECTED', 'Refusee'), ('HIDDEN', 'Masquee'), ('DELETED', 'Supprimee')], max_length=16)),
                ('reason', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ('-created_at',),
            },
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='file_blob',
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='file_content_type',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='file_size',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='is_presentation',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='moderated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='moderated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='rejection_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='replaces',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='replaced_by', to='profiles.profilevideo'),
        ),
        migrations.AddField(
            model_name='profilevideo',
            name='source_type',
            field=models.CharField(choices=[('LINK', 'Lien externe'), ('FILE', 'Fichier televerse')], default='LINK', max_length=8),
        ),
        migrations.AlterField(
            model_name='profilevideo',
            name='status',
            field=models.CharField(choices=[('DRAFT', 'Brouillon'), ('PROCESSING', 'En traitement'), ('PENDING', 'En attente de moderation'), ('APPROVED', 'Validee'), ('PUBLISHED', 'Publiee'), ('REJECTED', 'Refusee'), ('HIDDEN', 'Masquee'), ('DELETED', 'Supprimee')], default='DRAFT', max_length=16),
        ),
        migrations.AddConstraint(
            model_name='profilevideo',
            constraint=models.UniqueConstraint(condition=models.Q(('is_presentation', True), ('status', 'PUBLISHED')), fields=('profile',), name='one_published_presentation_per_profile'),
        ),
        migrations.AddField(
            model_name='videomoderationevent',
            name='actor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='videomoderationevent',
            name='video',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='moderation_events', to='profiles.profilevideo'),
        ),
        migrations.AddIndex(
            model_name='videomoderationevent',
            index=models.Index(fields=['video', '-created_at'], name='profiles_vi_video_i_47ede8_idx'),
        ),
    ]
