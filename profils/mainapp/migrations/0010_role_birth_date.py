
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0009_videofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='role',
            name='birth_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
