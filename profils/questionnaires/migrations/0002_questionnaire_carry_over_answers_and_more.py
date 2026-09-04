
import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('questionnaires', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='questionnaire',
            name='carry_over_answers',
            field=models.BooleanField(default=True, help_text="reporter les reponses des participants lors d'une nouvelle version"),
        ),
        migrations.AddField(
            model_name='questionnaireattempt',
            name='carried_from',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='carried_to', to='questionnaires.questionnaireattempt'),
        ),
        migrations.AddField(
            model_name='useranswer',
            name='carried',
            field=models.BooleanField(default=False),
        ),
    ]
