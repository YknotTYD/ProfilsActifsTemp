
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0002_seed_languages'),
    ]

    operations = [
        migrations.AddField(
            model_name='professionalprofile',
            name='cover_color',
            field=models.CharField(blank=True, choices=[('navy', 'Marine'), ('ocre', 'Ocre'), ('teal', 'Sarcelle'), ('forest', 'Foret'), ('purple', 'Violet'), ('rose', 'Rose'), ('sky', 'Ciel'), ('sunset', 'Coucher de soleil'), ('slate', 'Ardoise'), ('indigo', 'Indigo')], default='navy', max_length=20),
        ),
    ]
