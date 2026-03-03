from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('calls', '0003_recording_minutes_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoomRecordingState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=200, unique=True)),
                ('is_recording', models.BooleanField(default=False)),
                ('started_by', models.CharField(blank=True, default='', max_length=200)),
                ('process_pid', models.IntegerField(blank=True, null=True)),
                ('process_token', models.CharField(blank=True, default='', max_length=64)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
