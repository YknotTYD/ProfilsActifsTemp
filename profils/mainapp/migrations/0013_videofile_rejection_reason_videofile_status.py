
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0012_merge_20260903_1407'),
    ]

    operations = [
        migrations.AddField(
            model_name='videofile',
            name='rejection_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='videofile',
            name='status',
            field=models.CharField(choices=[('PENDING', 'PENDING'), ('APPROVED', 'APPROVED'), ('REJECTED', 'REJECTED')], default='PENDING', max_length=8),
        ),
    ]
