
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mainapp', '0002_jobseeker'),
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('Recruiter', 'Recruiter'), ('JobSeeker', 'JobSeeker'), ('Admin', 'Admin')], max_length=9)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RemoveField(
            model_name='recruiter',
            name='user',
        ),
        migrations.DeleteModel(
            name='JobSeeker',
        ),
        migrations.DeleteModel(
            name='Recruiter',
        ),
    ]
