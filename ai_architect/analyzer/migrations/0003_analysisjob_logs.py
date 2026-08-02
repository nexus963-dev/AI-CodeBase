from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analyzer', '0002_analysisjob_progress'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysisjob',
            name='logs',
            field=models.TextField(blank=True, null=True),
        ),
    ]
