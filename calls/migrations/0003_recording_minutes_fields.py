from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('calls', '0002_recording'),
    ]

    operations = [
        migrations.AddField(
            model_name='recording',
            name='participants_json',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='recording',
            name='minutes_status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('processing', 'Processing'), ('done', 'Done'), ('failed', 'Failed')],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='recording',
            name='minutes_text',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='recording',
            name='minutes_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='recording',
            name='minutes_generated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
